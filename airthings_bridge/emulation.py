"""Emulation of the Airthings devices, for tests without BLE access.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import random

from airthings_bridge.airthings import AirthingsDevice

# Value range of each key
RANGES = {
    "humidity": (20, 100),
    "temperature": (10, 35),
    "pressure": (950, 1050),
    "co2": (400, 2000),
    "voc": (20, 1000),
    "noise": (30, 70),
    "lux": (0, 500),
    "illuminance": (0, 100),
    "battery": (80, 100),
}
RADON_RANGE = (20, 500)


class EmulatedSensor:
    """Random walk between a minimum and a maximum."""

    def __init__(self, min_value: float, max_value: float):
        self.min = min_value
        self.max = max_value
        self.value = (min_value + max_value) / 2

    def get(self) -> float:
        """Return the next value."""
        self.value = round(
            self.value
            + random.random() * (self.max - self.value) / 20
            - random.random() * (self.value - self.min) / 20, 1)
        self.value = max(self.min, min(self.max, self.value))
        return self.value


class EmulatedDevice:
    """Emulation of a device, providing the values of its model."""

    def __init__(self, model: type[AirthingsDevice], serial: str, name: str = ""):
        self.model = model
        self.serial = serial
        self.name = name or serial
        self._sensors = {key: EmulatedSensor(*RANGES.get(key, RADON_RANGE))
                         for key in model.value_keys()}

    async def read(self, retries: int = 3, retry_delay: float = 1.0) -> dict[str, float]:
        """Return the next emulated values."""
        return {key: sensor.get() for key, sensor in self._sensors.items()}
