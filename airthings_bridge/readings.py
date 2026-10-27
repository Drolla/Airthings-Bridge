"""Sensor readings."""

from typing import Any

# {device name: {sensor: value}}
SensorData = dict[str, dict[str, Any]]
