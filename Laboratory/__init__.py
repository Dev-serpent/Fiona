"""Fiona Built-in GNS3 Laboratory.

Provides everything needed to spin up a complete IoT simulation lab
inside GNS3 — topology definitions, simulated device scripts, example
automation rules, and a one-command launcher.
"""
from __future__ import annotations

from Laboratory.topology import (
    FIONA_LAB_NAME,
    SAMPLE_TOPOLOGY,
    build_lab_topology,
)

__all__ = [
    "FIONA_LAB_NAME",
    "SAMPLE_TOPOLOGY",
    "build_lab_topology",
]
