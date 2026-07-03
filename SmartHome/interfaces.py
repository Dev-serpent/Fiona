"""Abstract base classes / interfaces for the Smart Home / IoT platform.

These ABCs define the contracts that every driver, registry, and automation
engine must satisfy.  Concrete implementations live in subpackages such as
``SmartHome.devices``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional

from SmartHome.errors import DeviceNotFoundError, DeviceOfflineError, RuleNotFoundError
from SmartHome.models import (
    DeviceEvent,
    DeviceInfo,
    DeviceProperties,
    DeviceState,
    DeviceType,
)


# ── Type Aliases ─────────────────────────────────────────────────────────────

EventHandler = Callable[..., Awaitable[None]]
"""Signature for an asynchronous event handler / callback."""


# ── Device Driver ────────────────────────────────────────────────────────────

class IDeviceDriver(ABC):
    """Abstract device driver that communicates with a physical or virtual IoT device."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish the connection to the device (e.g. via MQTT, HTTP, BLE).

        Returns ``True`` when the connection succeeds.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Tear down the connection to the device."""

    @abstractmethod
    async def get_state(self) -> DeviceState:
        """Read the full current state from the device.

        Raises :exc:`DeviceOfflineError` if the device is unreachable.
        """

    @abstractmethod
    async def set_state(self, state: dict[str, Any]) -> bool:
        """Send a command / state update to the device.

        Returns ``True`` when the device acknowledges the change.
        """

    @abstractmethod
    async def ping(self) -> bool:
        """Health-check the device connection.

        Returns ``True`` if the device responds.
        """

    @property
    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """Return the :class:`DeviceInfo` descriptor for this driver."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """``True`` when the driver currently holds an active connection."""


# ── Device Registry ──────────────────────────────────────────────────────────

class IDeviceRegistry(ABC):
    """Registry for device discovery, CRUD, and lifecycle tracking."""

    @abstractmethod
    async def register(self, device_info: DeviceInfo) -> str:
        """Register a device in the registry.

        Returns the ``device_id`` assigned to the device.
        """

    @abstractmethod
    async def unregister(self, device_id: str) -> bool:
        """Remove a device from the registry.

        Returns ``True`` if the device was found and removed.
        """

    @abstractmethod
    async def get(self, device_id: str) -> Optional[DeviceInfo]:
        """Look up a device by its *device_id*.

        Returns ``None`` when the device is not found.
        """

    @abstractmethod
    async def list(
        self,
        device_type: Optional[DeviceType] = None,
        room: Optional[str] = None,
    ) -> list[DeviceInfo]:
        """List registered devices, optionally filtered by type and/or room."""

    @abstractmethod
    async def update(
        self,
        device_id: str,
        properties: DeviceProperties,
    ) -> Optional[DeviceInfo]:
        """Update the configurable properties of a registered device.

        Returns the updated :class:`DeviceInfo` or ``None`` if the device
        does not exist.
        """

    # ── Events ────────────────────────────────────────────────────────────
    # Subclasses expose these as mutable lists of callbacks.

    @property
    @abstractmethod
    def on_device_registered(self) -> list[EventHandler]:
        """List of callbacks invoked when a new device is registered.

        Each handler receives the :class:`DeviceInfo` of the newly-registered
        device as its sole positional argument.
        """

    @property
    @abstractmethod
    def on_device_removed(self) -> list[EventHandler]:
        """List of callbacks invoked when a device is removed.

        Each handler receives the ``device_id`` string of the removed device
        as its sole positional argument.
        """


# ── Automation Rule ──────────────────────────────────────────────────────────

class AutomationRule(ABC):
    """A single automation rule consisting of a trigger and an action.

    Concrete subclasses define specific triggering logic and execute arbitrary
    actions when the trigger fires.
    """

    rule_id: str
    enabled: bool = True

    @abstractmethod
    async def evaluate(self, event: DeviceEvent) -> None:
        """Evaluate the rule against the given device event.

        Implementations should check whether the event matches the rule's
        trigger condition and, if so, execute the associated action(s).
        """


# ── Automation Engine ────────────────────────────────────────────────────────

class IAutomationEngine(ABC):
    """Event-driven and time-based automation engine."""

    @abstractmethod
    async def evaluate(self, event: DeviceEvent) -> None:
        """Called when a device event occurs.

        The engine should dispatch the event to all matching rules.
        """

    @abstractmethod
    async def add_rule(self, rule: AutomationRule) -> str:
        """Register a new automation rule.

        Returns the ``rule_id`` assigned to the rule.
        """

    @abstractmethod
    async def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by its *rule_id*.

        Returns ``True`` if the rule was found and removed.
        """

    @abstractmethod
    async def list_rules(self) -> list[AutomationRule]:
        """Return all registered automation rules."""

    @abstractmethod
    async def enable_rule(self, rule_id: str) -> bool:
        """Enable a previously-disabled rule.

        Returns ``True`` if the rule was found and enabled.
        """

    @abstractmethod
    async def disable_rule(self, rule_id: str) -> bool:
        """Disable an enabled rule without removing it.

        Returns ``True`` if the rule was found and disabled.
        """

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """``True`` when the automation engine is actively processing events."""

    @abstractmethod
    async def start(self) -> None:
        """Start the automation engine (begin processing events)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the automation engine (cease processing events)."""
