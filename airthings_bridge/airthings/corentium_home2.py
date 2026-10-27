"""Airthings Corentium Home 2."""

from airthings_bridge.airthings.atom import AtomDevice


class CorentiumHome2(AtomDevice):
    """Airthings Corentium Home 2.

    The radon averages cover 1 day (radon_st), 7 days, 30 days and 1 year.
    The 1 year average is also provided as long term average (radon_lt), and
    logged only under this key.
    """

    PRODUCT_NAME = "Corentium Home 2"
    SERIAL_PREFIXES = ("325",)
    SENSOR_KEYS = ("radon_st", "radon_week", "radon_month", "radon_lt", "temperature",
                   "humidity")
    STATUS_KEYS = ("radon_year", "battery")
