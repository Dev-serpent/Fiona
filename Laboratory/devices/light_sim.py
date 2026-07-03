"""Simulated IoT light — listens for MQTT commands and publishes state."""
from __future__ import annotations

import argparse
import json
import random
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None  # Standalone mode — just print state changes

TOPIC_PREFIX = "fiona"


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated IoT light")
    parser.add_argument("--name", default="light", help="Device name/ID")
    parser.add_argument("--mqtt-host", default="mqtt-broker", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    args = parser.parse_args()

    device_id = args.name.replace(" ", "-").lower()
    state = {"power": False, "brightness": 0, "color_temp": 4000, "color": "#ffffff"}

    print(f"[{device_id}] Simulated light starting (MQTT: {args.mqtt_host}:{args.mqtt_port})")

    if mqtt is not None:
        client = mqtt.Client(client_id=device_id)

        def on_connect(c, userdata, flags, rc) -> None:
            print(f"[{device_id}] Connected to MQTT broker (rc={rc})")
            topic = f"{TOPIC_PREFIX}/{device_id}/command"
            c.subscribe(topic)
            print(f"[{device_id}] Subscribed to {topic}")
            # Publish availability
            c.publish(f"{TOPIC_PREFIX}/{device_id}/available", "online", retain=True)

        def on_message(c, userdata, msg) -> None:
            nonlocal state
            try:
                payload = json.loads(msg.payload.decode())
                print(f"[{device_id}] Received command: {payload}")
                for key, value in payload.items():
                    if key in state:
                        state[key] = value
                # Publish state update
                c.publish(
                    f"{TOPIC_PREFIX}/{device_id}/state",
                    json.dumps(state),
                )
                # Publish event
                c.publish(
                    f"{TOPIC_PREFIX}/{device_id}/event",
                    json.dumps({"event": "state_changed", "data": payload}),
                )
                print(f"[{device_id}] New state: {state}")
            except json.JSONDecodeError:
                print(f"[{device_id}] Invalid JSON: {msg.payload}")

        client.on_connect = on_connect
        client.on_message = on_message
        client.will_set(
            f"{TOPIC_PREFIX}/{device_id}/available",
            "offline", retain=True,
        )

        try:
            client.connect(args.mqtt_host, args.mqtt_port, keepalive=60)
            client.loop_forever()
        except KeyboardInterrupt:
            print(f"[{device_id}] Shutting down")
            client.publish(f"{TOPIC_PREFIX}/{device_id}/available", "offline", retain=True)
            client.disconnect()
    else:
        # Standalone simulation (no MQTT)
        print(f"[{device_id}] Running in standalone mode (no paho-mqtt)")
        try:
            while True:
                print(f"[{device_id}] State: {state}")
                time.sleep(10)
        except KeyboardInterrupt:
            print(f"[{device_id}] Shutting down")


if __name__ == "__main__":
    main()
