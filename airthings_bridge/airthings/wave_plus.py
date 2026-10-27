"""Airthings Wave Plus.

Copyright (C) 2020-2026 Andreas Drollinger
Portions Copyright (C) 2018 Airthings, (C) 2024 Airthings ASA (airthings-ble, MIT)
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import struct

from bleak import BleakClient

from airthings_bridge.airthings.common import (
    AirthingsDevice,
    NotificationReceiver,
    ResponseCache,
    Values,
    battery_two_cells,
    in_range,
    request,
)
from airthings_bridge.errors import DeviceError

RADON_MAX = 16383
CO2_VOC_MAX = 65534


class WavePlus(AirthingsDevice):
    """Airthings Wave Plus.

    The sensor data is read from a characteristic. Illuminance and battery
    voltage are part of the response to a command.
    """

    PRODUCT_NAME = "Wave Plus"
    SERIAL_PREFIXES = ("2930",)
    SENSOR_KEYS = ("humidity", "radon_st", "radon_lt", "temperature", "pressure", "co2", "voc")
    STATUS_KEYS = ("illuminance", "battery")

    DATA_UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"
    DATA_FORMAT = "<4B2Hh5H"
    COMMAND_UUID = "b42e2d06-ade7-11e4-89d3-123b93f75cba"
    COMMAND = b"\x6d"
    COMMAND_RESPONSE_LENGTH = 30

    # Illuminance and battery level change slowly, which allows reusing the
    # command response and saving battery
    _responses = ResponseCache(ttl=3600, max_reads=100)

    @classmethod
    def decode_data(cls, raw: bytes) -> Values:
        """Decode the sensor data characteristic."""
        if len(raw) != struct.calcsize(cls.DATA_FORMAT) or raw[0] != 1:
            raise DeviceError(f"Invalid sensor data: {raw.hex()}")
        v = struct.unpack(cls.DATA_FORMAT, raw)
        humidity = in_range(v[1] / 2.0, 100)
        values = {
            "humidity": humidity,
            "radon_st": in_range(v[4], RADON_MAX),
            "radon_lt": in_range(v[5], RADON_MAX),
            # The firmware reports an invalid temperature while the humidity is missing
            "temperature": None if humidity is None or v[6] == -1
            else in_range(v[6] / 100.0, 100, -40),
            "pressure": in_range(v[7] / 50.0, 1310),
            "co2": in_range(float(v[8]), CO2_VOC_MAX),
            "voc": in_range(float(v[9]), CO2_VOC_MAX),
        }
        return {key: values[key] for key in cls.SENSOR_KEYS}

    @classmethod
    def decode_command_response(cls, raw: bytes) -> Values:
        """Decode the command response with the illuminance and the battery voltage."""
        if raw[0:1] != cls.COMMAND or len(raw) != cls.COMMAND_RESPONSE_LENGTH:
            raise DeviceError(f"Invalid command response: {raw.hex()}")
        return {"illuminance": raw[7],
                "battery": battery_two_cells(int.from_bytes(raw[26:28], "little") / 1000)}

    async def _read(self, client: BleakClient) -> Values:
        values = self.decode_data(bytes(await client.read_gatt_char(self.DATA_UUID)))
        cached = self._responses.get(self.serial)
        response = cached or await request(
            client, self.COMMAND_UUID, self.COMMAND_UUID, self.COMMAND,
            NotificationReceiver(self.COMMAND_RESPONSE_LENGTH), self.COMMAND_TIMEOUT)
        values.update(self.decode_command_response(response))
        if cached is None:
            self._responses.put(self.serial, response)
        return values
