"""Measurement metadata, used by the web UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Measurement:
    """Measured value: key of the device values, label and unit."""

    key: str
    label: str
    unit: str


# The web UI shows the graphs in this order
MEASUREMENTS = (
    Measurement("radon_st", "Radon, 1 day average", "Bq/m³"),
    Measurement("radon_week", "Radon, 7 days average", "Bq/m³"),
    Measurement("radon_month", "Radon, 30 days average", "Bq/m³"),
    Measurement("radon_lt", "Radon, long term average", "Bq/m³"),
    Measurement("radon_year", "Radon, 1 year average", "Bq/m³"),
    Measurement("temperature", "Temperature", "°C"),
    Measurement("humidity", "Humidity", "%rH"),
    Measurement("co2", "CO2", "ppm"),
    Measurement("voc", "VOC", "ppb"),
    Measurement("pressure", "Pressure", "hPa"),
    Measurement("noise", "Noise", "dBA"),
    Measurement("lux", "Light", "lx"),
    # Wave Plus and Wave Radon: raw sensor value, other devices: %
    Measurement("illuminance", "Illuminance", ""),
    Measurement("battery", "Battery", "%"),
)
