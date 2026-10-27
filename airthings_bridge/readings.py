"""Sensor readings."""

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Reading:
    """Values read from a device. Empty values mean the device couldn't be read."""

    device: str
    values: dict[str, Any]
    update_time: float | None = None

    def values_with_time(self) -> dict[str, Any]:
        """Values completed by the integer update time, if available."""
        if self.update_time is None:
            return {}
        return {**self.values, "update_time": int(self.update_time)}


@dataclass(frozen=True)
class Cycle:
    """Readings of all devices of one polling cycle, with the scheduled cycle time."""

    timestamp: float
    readings: tuple[Reading, ...]

    def values(self) -> dict[str, dict[str, Any]]:
        """Values by device name."""
        return {reading.device: reading.values for reading in self.readings}


class LiveState:
    """Latest reading of each device."""

    def __init__(self) -> None:
        self._readings: dict[str, Reading] = {}

    def update(self, cycle: Cycle) -> None:
        """Take over the readings of a cycle."""
        for reading in cycle.readings:
            self._readings[reading.device] = reading

    def as_json(self) -> dict[str, Any]:
        """Return the current time and the latest device values (/data format)."""
        return {"current_time": int(time.time()),
                "devices": {name: reading.values_with_time()
                            for name, reading in self._readings.items()}}
