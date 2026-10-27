"""Airthings Wave (first generation).

Copyright (C) 2026 Andreas Drollinger
Portions Copyright (C) 2024 Airthings ASA (airthings-ble, MIT)
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

from bleak import BleakClient

from airthings_bridge.airthings.common import AirthingsDevice, Values, in_range, percent_of_255
from airthings_bridge.airthings.wave_plus import RADON_MAX
from airthings_bridge.errors import DeviceError


class WaveGen1(AirthingsDevice):
    """Airthings Wave Gen 1, with one characteristic per value."""

    PRODUCT_NAME = "Wave Gen 1"
    SERIAL_PREFIXES = ("2900",)
    SENSOR_KEYS = ("humidity", "radon_st", "radon_lt", "temperature")
    STATUS_KEYS = ("illuminance",)

    TEMPERATURE_UUID = "00002a6e-0000-1000-8000-00805f9b34fb"
    HUMIDITY_UUID = "00002a6f-0000-1000-8000-00805f9b34fb"
    RADON_ST_UUID = "b42e01aa-ade7-11e4-89d3-123b93f75cba"
    RADON_LT_UUID = "b42e0a4c-ade7-11e4-89d3-123b93f75cba"
    ILLUMINANCE_UUID = "b42e1348-ade7-11e4-89d3-123b93f75cba"  # Also accelerometer

    @staticmethod
    def decode(raw: dict[str, bytes]) -> Values:
        """Decode the characteristics, provided by their UUID."""
        try:
            def number(uuid: str, signed: bool = False) -> int:
                return int.from_bytes(raw[uuid][0:2], "little", signed=signed)

            return {
                "humidity": in_range(number(WaveGen1.HUMIDITY_UUID) / 100.0, 100),
                "radon_st": in_range(number(WaveGen1.RADON_ST_UUID), RADON_MAX),
                "radon_lt": in_range(number(WaveGen1.RADON_LT_UUID), RADON_MAX),
                "temperature": in_range(
                    number(WaveGen1.TEMPERATURE_UUID, signed=True) / 100.0, 100, -40),
                "illuminance": percent_of_255(raw[WaveGen1.ILLUMINANCE_UUID][0]),
            }
        except (KeyError, IndexError):
            raise DeviceError(f"Invalid sensor data: {raw}") from None

    async def _read(self, client: BleakClient) -> Values:
        uuids = (self.TEMPERATURE_UUID, self.HUMIDITY_UUID, self.RADON_ST_UUID,
                 self.RADON_LT_UUID, self.ILLUMINANCE_UUID)
        return self.decode({uuid: bytes(await client.read_gatt_char(uuid)) for uuid in uuids})
