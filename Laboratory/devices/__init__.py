"""Simulated IoT device scripts for GNS3 nodes."""
from __future__ import annotations

from Laboratory.devices.light_sim import main as light_sim_main
from Laboratory.devices.sensor_sim import main as sensor_sim_main
from Laboratory.devices.switch_sim import main as switch_sim_main

__all__ = [
    "light_sim_main",
    "sensor_sim_main",
    "switch_sim_main",
]
