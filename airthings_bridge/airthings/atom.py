"""Airthings Atom protocol, used by the Wave Enhance and the Corentium Home 2.

A CBOR encoded request is written to a characteristic, and the CBOR encoded
response is received in fragments by notifications.

Copyright (C) 2026 Andreas Drollinger
Portions Copyright (C) 2024 Airthings ASA (airthings-ble, MIT)
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import os
from typing import Any

import cbor2
from bleak import BleakClient

from airthings_bridge.airthings.common import (
    AirthingsDevice,
    NotificationReceiver,
    Values,
    battery_two_cells,
    in_range,
    request,
)
from airthings_bridge.errors import DeviceError

REQUEST_UUID = "b42eb73a-ade7-11e4-89d3-123b93f75cba"
RESPONSE_UUID = "b42ebc9e-ade7-11e4-89d3-123b93f75cba"
LATEST_VALUES_PATH = "29999/0/31012"
RESPONSE_HEADER = bytes.fromhex("0345")


def build_request(random_bytes: bytes, path: str = LATEST_VALUES_PATH) -> bytes:
    """Build a request. The response echoes the random bytes."""
    return bytes.fromhex("0301") + random_bytes + bytes.fromhex("81a100") + cbor2.dumps(path)


class FragmentReceiver(NotificationReceiver):
    """Reassembles a response from its fragments.

    Each fragment starts with a 3 byte header. In the control byte, the low
    nibble is the fragmentation version (0), bit 4 marks the first fragment,
    and the top 3 bits identify the response. The next 2 bytes (little
    endian) are the number of fragments in the first fragment, and the
    fragment position (counting from 1) in the others.
    """

    def __init__(self) -> None:
        super().__init__(length=0)
        self._fragments: dict[int, dict[int, bytes]] = {}
        self._count = 0
        self._response_id: int | None = None

    def __call__(self, _: Any, data: bytearray) -> None:
        if self.complete.is_set() or len(data) < 3 or data[0] & 0x0F:
            return
        response_id = data[0] & 0xE0
        if self._response_id is not None and response_id != self._response_id:
            return
        number = int.from_bytes(data[1:3], "little")
        fragments = self._fragments.setdefault(response_id, {})
        if data[0] & 0x10:
            self._response_id = response_id
            self._count = number
            fragments[1] = bytes(data[3:])
        elif number > 1:
            fragments[number] = bytes(data[3:])
        if self._response_id is None:
            return
        fragments = self._fragments[self._response_id]
        positions = range(1, self._count + 1)
        if positions and all(position in fragments for position in positions):
            self.message = bytearray(b"".join(fragments[position] for position in positions))
            self.complete.set()


def parse_response(response: bytes, random_bytes: bytes,
                   path: str = LATEST_VALUES_PATH) -> dict[str, Any]:
    """Return the values of a response. Raises DeviceError."""
    if response[0:2] != RESPONSE_HEADER or response[2:4] != random_bytes or \
            response[4:6] != b"\x81\xa2":
        raise DeviceError(f"Invalid response: {response.hex()}")
    try:
        content = cbor2.loads(response[4:])[0]
        data = content.get(2)
        # The latest values are CBOR encoded a second time
        if isinstance(data, bytes):
            data = cbor2.loads(data)
    except (cbor2.CBORError, TypeError, IndexError, AttributeError) as err:
        raise DeviceError(f"Invalid response data: {err}") from None
    if content.get(0) != path or not isinstance(data, dict):
        raise DeviceError(f"Invalid response content: {content}")
    return data


def decode_values(data: dict[str, Any]) -> Values:
    """Convert the response values."""
    def get(key: str, scale: float = 1.0) -> float | None:
        value = data.get(key)
        return None if not isinstance(value, int | float) else value * scale

    humidity = get("HUM", 0.01)
    temperature = get("TMP", 0.01)  # Kelvin
    pressure = get("PRS", 1 / 6400)
    battery = get("BAT", 0.001)
    radon_year = get("R1Y")
    return {
        "humidity": None if humidity is None else in_range(humidity, 100),
        "temperature": None if temperature is None
        else in_range(round(temperature - 273.15, 2), 100, -40),
        "pressure": None if pressure is None else in_range(pressure, 1310),
        "co2": get("CO2"),
        "voc": get("VOC"),
        "noise": get("NOI"),
        "lux": get("LUX"),
        "radon_st": get("R24"),
        "radon_week": get("R7D"),
        "radon_month": get("R30"),
        "radon_year": radon_year,
        "radon_lt": radon_year,
        "battery": None if battery is None else battery_two_cells(battery),
    }


class AtomDevice(AirthingsDevice):
    """Device using the Atom protocol."""

    async def _read(self, client: BleakClient) -> Values:
        random_bytes = os.urandom(2)
        response = await request(client, REQUEST_UUID, RESPONSE_UUID,
                                 build_request(random_bytes), FragmentReceiver(),
                                 self.COMMAND_TIMEOUT)
        values = decode_values(parse_response(response, random_bytes))
        return {key: values[key] for key in self.value_keys()}
