"""Airthings BLE devices."""

from airthings_bridge.airthings.common import AirthingsDevice, ScanResult, scan
from airthings_bridge.airthings.corentium_home2 import CorentiumHome2
from airthings_bridge.airthings.wave_enhance import WaveEnhance
from airthings_bridge.airthings.wave_gen1 import WaveGen1
from airthings_bridge.airthings.wave_mini import WaveMini
from airthings_bridge.airthings.wave_plus import WavePlus
from airthings_bridge.airthings.wave_radon import WaveRadon
from airthings_bridge.errors import ConfigError

MODELS: tuple[type[AirthingsDevice], ...] = (
    WaveGen1, WaveMini, WavePlus, WaveRadon, WaveEnhance, CorentiumHome2)

__all__ = ["MODELS", "AirthingsDevice", "ScanResult", "create_device", "model_for_serial",
           "scan"]


def model_for_serial(serial: str) -> type[AirthingsDevice] | None:
    """Return the device class of a serial number, or None if it is not supported."""
    for model in MODELS:
        if serial.startswith(model.SERIAL_PREFIXES):
            return model
    return None


def create_device(serial: str, name: str = "") -> AirthingsDevice:
    """Create the device of a serial number. Raises ConfigError if it is not supported."""
    model = model_for_serial(serial)
    if model is None:
        raise ConfigError(f"Unsupported device {serial}: unknown serial number prefix")
    return model(serial, name)
