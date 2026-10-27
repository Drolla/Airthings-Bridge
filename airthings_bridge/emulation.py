"""Airthings Wave Plus sensor reader emulation.

Emulates the WavePlus class of airthings.wave_plus without BLE access, for
tests. It is used with the '--emulation' flag or the 'emulation: True'
configuration.

Copyright (C) 2020-2022 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import random

logger = logging.getLogger(__name__)


class EmulatedSensor:
    """Sensor emulation with a random walk between a minimum and maximum."""

    def __init__(self, min_value: float, max_value: float):
        self.min = min_value
        self.max = max_value
        self.value = (min_value+max_value)/2

    def get(self) -> float:
        """Get the next emulated sensor value."""
        self.value = round(
                self.value +
                random.random() * (self.max-self.value)/20 -
                random.random() * (self.value-self.min)/20, 1)
        self.value = max(self.min, min(self.max, self.value))
        return self.value


class WavePlus:
    """Emulation of the WavePlus class of the waveplus module."""

    def __init__(self, sn: int | str, name: str = ""):
        self.sn = sn
        self.name = name if name != "" else sn
        self._sensors = {
            "humidity": EmulatedSensor(20, 100),
            "radon_st": EmulatedSensor(20, 500),
            "radon_lt": EmulatedSensor(20, 500),
            "temperature": EmulatedSensor(10, 35),
            "pressure": EmulatedSensor(20, 500),
            "co2": EmulatedSensor(20, 500),
            "voc": EmulatedSensor(20, 1000),
        }

    def stop(self) -> None:
        pass

    def get(self, retries: int = 3,
            retry_delay: float = 1.0) -> dict[str, float]:
        """Get the emulated sensor data."""
        logger.debug("Reading sensor data for device %s", self.name)
        return {key: sensor.get() for key, sensor in self._sensors.items()}

