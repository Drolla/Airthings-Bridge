"""Airthings Wave Mini.

Copyright (C) 2026 Andreas Drollinger
Portions Copyright (C) 2024 Airthings ASA (airthings-ble, MIT)
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import struct

from bleak import BleakClient

from airthings_bridge.airthings.common import (
    UINT16_NO_VALUE,
    AirthingsDevice,
    NotificationReceiver,
    ResponseCache,
    Values,
    battery_three_cells,
    in_range,
    percent_of_255,
    request,
)
from airthings_bridge.errors import DeviceError


class WaveMini(AirthingsDevice):
    """Airthings Wave Mini. The battery voltage is part of a command response."""

    PRODUCT_NAME = "Wave Mini"
    SERIAL_PREFIXES = ("2920",)
    SENSOR_KEYS = ("humidity", "temperature", "pressure", "voc")
    STATUS_KEYS = ("illuminance", "battery")

    DATA_UUID = "b42e3b98-ade7-11e4-89d3-123b93f75cba"
    DATA_FORMAT = "<2B5HLL"
    COMMAND_UUID = "b42e3ef4-ade7-11e4-89d3-123b93f75cba"
    COMMAND = b"\x6d"
    COMMAND_RESPONSE_FORMAT = "<2L4B2HL4HL"  # After a 2 byte header

    _responses = ResponseCache(ttl=3600, max_reads=100)

    @classmethod
    def decode_data(cls, raw: bytes) -> Values:
        """Decode the sensor data characteristic."""
        if len(raw) != struct.calcsize(cls.DATA_FORMAT):
            raise DeviceError(f"Invalid sensor data: {raw.hex()}")
        v = struct.unpack(cls.DATA_FORMAT, raw)
        return {
            "illuminance": None if int.from_bytes(raw[0:2], "little") == UINT16_NO_VALUE
            else percent_of_255(v[0]),
            # Kelvin
            "temperature": in_range(round(v[2] / 100.0 - 273.15, 2), 100, -40),
            "pressure": None if v[3] == UINT16_NO_VALUE else v[3] / 50.0,
            "humidity": in_range(v[4] / 100.0, 100),
            "voc": in_range(float(v[5]), 65534),
        }

    @classmethod
    def decode_command_response(cls, raw: bytes) -> Values:
        """Decode the command response with the battery voltage."""
        if raw[0:1] != cls.COMMAND or \
                len(raw) != 2 + struct.calcsize(cls.COMMAND_RESPONSE_FORMAT):
            raise DeviceError(f"Invalid command response: {raw.hex()}")
        v = struct.unpack(cls.COMMAND_RESPONSE_FORMAT, raw[2:])
        return {"battery": battery_three_cells(v[11] / 1000)}

    async def _read(self, client: BleakClient) -> Values:
        values = self.decode_data(bytes(await client.read_gatt_char(self.DATA_UUID)))
        cached = self._responses.get(self.serial)
        response = cached or await request(
            client, self.COMMAND_UUID, self.COMMAND_UUID, self.COMMAND,
            NotificationReceiver(2 + struct.calcsize(self.COMMAND_RESPONSE_FORMAT)),
            self.COMMAND_TIMEOUT)
        values.update(self.decode_command_response(response))
        if cached is None:
            self._responses.put(self.serial, response)
        return values
