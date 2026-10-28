"""Airthings Wave Enhance."""

from airthings_bridge.airthings.atom import AtomDevice


class WaveEnhance(AtomDevice):
    """Airthings Wave Enhance (EU: 321..., US: 322...)."""

    PRODUCT_NAME = "Wave Enhance"
    SERIAL_PREFIXES = ("321", "322")
    SENSOR_KEYS = ("humidity", "temperature", "pressure", "co2", "voc", "noise")
    STATUS_KEYS = ("lux", "battery")
