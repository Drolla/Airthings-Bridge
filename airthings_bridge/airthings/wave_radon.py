"""Airthings Wave Radon (Wave 2).

Copyright (C) 2026 Andreas Drollinger
Portions Copyright (C) 2024 Airthings ASA (airthings-ble, MIT)
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

from airthings_bridge.airthings.wave_plus import WavePlus


class WaveRadon(WavePlus):
    """Airthings Wave Radon, with the data formats of the Wave Plus."""

    PRODUCT_NAME = "Wave Radon"
    SERIAL_PREFIXES = ("2950",)
    SENSOR_KEYS = ("humidity", "radon_st", "radon_lt", "temperature")

    DATA_UUID = "b42e4dcc-ade7-11e4-89d3-123b93f75cba"
    COMMAND_UUID = "b42e50d8-ade7-11e4-89d3-123b93f75cba"
