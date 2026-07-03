"""Async MQTT client wrapper with auto-reconnect, LWT, and retained messages.

Usage::

    client = MqttClient(config, will_topic="fiona/gateway/available")
    await client.connect()
    await client.publish("fiona/sensor-01/state", {"temperature": 22.5})
    await client.subscribe("fiona/+/command", callback=on_command)
    # ...
    await client.disconnect()
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
import logging
from typing import Any, Callable, Coroutine, Optional

from SmartHome.config import MqttConfig
from SmartHome.constants import MQTT_RECONNECT_DELAY_MAX, MQTT_RECONNECT_DELAY_MIN
from SmartHome.errors import MqttConnectionError, MqttPublishError

logger = logging.getLogger(__name__)

# Type alias for async message callbacks: receives topic (str) and payload (str).
MessageCallback = Callable[[str, str], Coroutine[Any, Any, None]]


class MqttClient:
    """Asynchronous MQTT client with automatic reconnection.

    Wraps the synchronous ``paho-mqtt`` library with an ``asyncio``-friendly
    interface.  The network loop runs in a background thread managed by
    ``paho``; callbacks are dispatched into the asyncio event loop via
    :func:`asyncio.create_task`.

    Features:

    * Automatic reconnection with exponential backoff (1 s → 120 s)
    * Last Will and Testament (LWT) for device availability
    * Retained message support
    * Per-topic async callback dispatch
    """

    def __init__(
        self,
        config: Optional[MqttConfig] = None,
        will_topic: Optional[str] = None,
        will_payload: str = "offline",
        will_qos: Optional[int] = None,
    ) -> None:
        """Initialise the client.

        Args:
            config:           MQTT broker connection parameters.  When ``None``
                              a default :class:`~SmartHome.config.MqttConfig` is
                              used (localhost:1883, no auth).
            will_topic:       Topic for the Last Will message.  When set, the
                              broker will publish *will_payload* on this topic
                              if the client disconnects unexpectedly.
            will_payload:     Payload for the LWT message (default ``"offline"``).
            will_qos:         QoS for the LWT message (default: *config.qos*).
        """
        self.config = config or MqttConfig()
        self._client: Any = None  # paho.mqtt.client.Client  (lazy import)
        self._connected = asyncio.Event()
        self._running = False
        self._message_callbacks: dict[str, list[MessageCallback]] = {}
        self._connect_lock = asyncio.Lock()

        # Will configuration
        self._will_topic = will_topic
        self._will_payload = will_payload
        self._will_qos = will_qos if will_qos is not None else self.config.qos

    # ── Public API ───────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to the MQTT broker with exponential-backoff retry.

        Retries indefinitely with delays: 1 s, 2 s, 4 s, … up to 120 s.
        Raises :class:`~SmartHome.errors.MqttConnectionError` only when
        :meth:`disconnect` is called during a retry pause.
        """
        async with self._connect_lock:
            if self._connected.is_set():
                return

            import paho.mqtt.client as mqtt  # optional dependency

            self._running = True

            self._client = mqtt.Client(
                client_id=self.config.client_id,
                clean_session=True,
            )

            # Set up LWT
            if self._will_topic:
                self._client.will_set(
                    self._will_topic,
                    payload=self._will_payload,
                    qos=self._will_qos,
                    retain=True,
                )

            # Wire paho callbacks
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            # Authentication
            if self.config.username:
                self._client.username_pw_set(
                    self.config.username,
                    self.config.password,
                )

            # TLS
            if self.config.tls_enabled:
                self._client.tls_set(self.config.ca_cert or None)

            # Enable automatic reconnection in paho's background thread
            self._client.reconnect_delay_set(
                min_delay=MQTT_RECONNECT_DELAY_MIN,
                max_delay=MQTT_RECONNECT_DELAY_MAX,
            )

            # Connect with exponential backoff
            delay = MQTT_RECONNECT_DELAY_MIN
            while self._running:
                try:
                    logger.info(
                        "Connecting to MQTT broker at %s:%d",
                        self.config.host,
                        self.config.port,
                    )
                    self._client.connect(self.config.host, self.config.port)
                    self._client.loop_start()
                    await asyncio.wait_for(
                        self._connected.wait(),
                        timeout=10.0,
                    )
                    logger.info("Connected to MQTT broker")
                    return
                except (ConnectionRefusedError, OSError, asyncio.TimeoutError) as exc:
                    logger.warning(
                        "MQTT connection failed: %s. Retrying in %ds ...",
                        exc,
                        delay,
                    )
                    # Clean up partial connect for next attempt
                    try:
                        self._client.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                    self._connected.clear()
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, MQTT_RECONNECT_DELAY_MAX)

            raise MqttConnectionError("Client was stopped during connection attempt")

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker and stop the network loop."""
        self._running = False
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                logger.exception("Error during MQTT disconnect")
            finally:
                self._client = None
        self._connected.clear()

    async def publish(
        self,
        topic: str,
        payload: Any,
        qos: Optional[int] = None,
        retain: bool = False,
    ) -> None:
        """Publish a message to an MQTT topic.

        The *payload* is JSON-encoded unless it is already a :class:`str`.

        Args:
            topic:   MQTT topic string.
            payload: JSON-serialisable value (or raw string).
            qos:     QoS level (default: *config.qos*).
            retain:  Whether the broker should retain the message.

        Raises:
            MqttConnectionError: If the client is not connected.
            MqttPublishError:    If the publish operation fails.
        """
        if not self._connected.is_set() or self._client is None:
            raise MqttConnectionError("Not connected to MQTT broker")

        qos = qos if qos is not None else self.config.qos
        payload_str = (
            json.dumps(payload) if not isinstance(payload, str) else payload
        )

        result = self._client.publish(topic, payload_str, qos=qos, retain=retain)
        if result.rc != 0:  # MQTT_ERR_SUCCESS
            raise MqttPublishError(
                f"Publish failed with code {result.rc} (topic={topic})"
            )

    async def subscribe(
        self,
        topic: str,
        qos: Optional[int] = None,
        callback: Optional[MessageCallback] = None,
    ) -> None:
        """Subscribe to an MQTT topic filter.

        The *callback*, if provided, is invoked for every message whose topic
        matches the filter.  Wildcards (``+``, ``#``) are supported by the
        broker-level subscription; the client dispatches all incoming messages
        that match.

        Args:
            topic:    MQTT topic filter (can include wildcards).
            qos:      QoS level (default: *config.qos*).
            callback: Optional async callable to receive matching messages.

        Raises:
            MqttConnectionError: If the client is not connected.
        """
        if not self._connected.is_set() or self._client is None:
            raise MqttConnectionError("Not connected to MQTT broker")

        qos = qos if qos is not None else self.config.qos
        self._client.subscribe(topic, qos=qos)

        if callback is not None:
            self._message_callbacks.setdefault(topic, []).append(callback)

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """``True`` when the client holds an active MQTT connection."""
        return self._connected.is_set()

    # ── paho-mqtt callbacks ──────────────────────────────────────────────────

    def _on_connect(  # type: ignore[misc]  # noqa: PLR0913
        self,
        client: Any,
        userdata: Any,
        flags: dict[str, int],
        rc: int,
    ) -> None:
        """paho ``on_connect`` — signals connection success/failure."""
        if rc == 0:
            self._connected.set()
            logger.info("MQTT connected (rc=0)")
        else:
            logger.error("MQTT connection failed (rc=%d)", rc)

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        """paho ``on_disconnect`` — clears the connected flag.

        When *rc* is non-zero the disconnection was unexpected; paho's internal
        reconnect mechanism (configured via :meth:`reconnect_delay_set`) will
        attempt to restore the connection automatically.
        """
        self._connected.clear()
        if rc != 0:
            logger.warning("MQTT unexpected disconnect (rc=%d)", rc)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """paho ``on_message`` — dispatches to registered asyncio callbacks.

        The message is delivered to every callback whose topic filter matches
        the incoming topic.  Matches are performed with :func:`fnmatch.fnmatch`
        (``+`` and ``#`` both become ``*``).
        """
        topic: str = msg.topic
        payload: str = msg.payload.decode("utf-8", errors="replace")

        for topic_filter, callbacks in self._message_callbacks.items():
            if self._topic_matches(topic_filter, topic):
                for callback in callbacks:
                    asyncio.create_task(callback(topic, payload))

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _topic_matches(topic_filter: str, topic: str) -> bool:
        """Check whether *topic* matches *topic_filter* (MQTT wildcards).

        .. note::
            This is a simplified check that treats both MQTT wildcards
            (``+`` and ``#``) as ``*``.  It does *not* enforce the
            single-level-only semantics of ``+``.
        """
        pattern = topic_filter.replace("#", "*").replace("+", "*")
        return fnmatch.fnmatch(topic, pattern)
