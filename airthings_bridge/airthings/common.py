"""Device independent access to Airthings BLE devices.

Copyright (C) 2020-2026 Andreas Drollinger
Portions Copyright (C) 2018 Airthings, (C) 2024 Airthings ASA (airthings-ble, MIT)
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from airthings_bridge.errors import DeviceError

logger = logging.getLogger(__name__)

AIRTHINGS_ID = 0x0334  # Bluetooth manufacturer ID
UINT16_NO_VALUE = 0xFFFF

Values = dict[str, Any]


def parse_serial_number(manufacturer_data: bytes | None) -> str | None:
    """Return the serial number of the Airthings manufacturer data, or None."""
    if manufacturer_data is None or len(manufacturer_data) < 4:
        return None
    serial = str(int.from_bytes(manufacturer_data[0:4], "little"))
    return serial if len(serial) == 10 else None


def in_range(value: float, max_value: float, min_value: float = 0) -> float | None:
    """Return the value if it is within [min_value, max_value], None otherwise."""
    return value if min_value <= value <= max_value else None


def percent_of_255(value: int) -> int | None:
    """Convert an 8-bit value into a percentage."""
    return None if value > 255 else int(value / 255 * 100)


def _interpolate(voltage: float, curve: tuple[tuple[float, float], ...]) -> int:
    """Interpolate the battery level of a (voltage, %) curve, highest voltage first."""
    if voltage >= curve[0][0]:
        return round(curve[0][1])
    for (v_high, p_high), (v_low, p_low) in zip(curve, curve[1:], strict=False):
        if voltage >= v_low:
            return round(p_low + (voltage - v_low) / (v_high - v_low) * (p_high - p_low))
    return 0


def battery_two_cells(voltage: float) -> int:
    """Battery level in % of devices with two AA cells."""
    return _interpolate(voltage, ((3.00, 100), (2.80, 81), (2.60, 53), (2.50, 28),
                                  (2.20, 5), (2.10, 0)))


def battery_three_cells(voltage: float) -> int:
    """Battery level in % of devices with three AAA cells."""
    return _interpolate(voltage, ((4.50, 100), (4.20, 85), (3.90, 62), (3.75, 42),
                                  (3.30, 23), (2.40, 0)))


class ResponseCache:
    """Command responses, reused during ttl seconds and for at most max_reads reads."""

    def __init__(self, ttl: float, max_reads: int):
        self._ttl = ttl
        self._max_reads = max_reads
        self._entries: dict[str, list[Any]] = {}  # key: [response, time, reads]

    def get(self, key: str) -> bytes | None:
        """Return the cached response, or None if it is missing or obsolete."""
        entry = self._entries.get(key)
        if entry is None or time.monotonic() > entry[1] + self._ttl or \
                entry[2] >= self._max_reads:
            return None
        entry[2] += 1
        return entry[0]

    def put(self, key: str, response: bytes) -> None:
        """Store a response."""
        self._entries[key] = [response, time.monotonic(), 0]


class NotificationReceiver:
    """Collects the notifications of a command response until it is complete.

    A response larger than the MTU is sent in multiple notifications.
    """

    def __init__(self, length: int):
        self._length = length
        self.message = bytearray()
        self.complete = asyncio.Event()

    def __call__(self, _: Any, data: bytearray) -> None:
        if not self.complete.is_set():
            self.message += data
            if len(self.message) >= self._length:
                self.complete.set()


async def request(client: BleakClient, write_uuid: str, notify_uuid: str, command: bytes,
                  receiver: NotificationReceiver, timeout: float) -> bytes:
    """Write a command and return the response received by notifications."""
    await client.start_notify(notify_uuid, receiver)
    try:
        await client.write_gatt_char(write_uuid, command)
        await asyncio.wait_for(receiver.complete.wait(), timeout)
    except TimeoutError:
        raise DeviceError("No complete command response received") from None
    finally:
        try:
            await asyncio.wait_for(client.stop_notify(notify_uuid), 2)
        except (BleakError, TimeoutError) as err:
            # The connection is closed anyway after the read
            logger.debug("Failed to stop the notifications: %s", err)
    return bytes(receiver.message)


@dataclass(frozen=True)
class ScanResult:
    """Airthings device found by a scan."""

    serial: str
    address: str
    rssi: int


class AirthingsDevice(ABC):
    """Airthings device, accessed by its serial number.

    Subclasses define the model and implement _read(). Values that a device
    reports as invalid are omitted.
    """

    PRODUCT_NAME: ClassVar[str]
    SERIAL_PREFIXES: ClassVar[tuple[str, ...]]
    SENSOR_KEYS: ClassVar[tuple[str, ...]]  # Measurements, logged into the CSV file
    STATUS_KEYS: ClassVar[tuple[str, ...]] = ()  # Device status, e.g. battery

    SCAN_TIMEOUT = 5.0
    CONNECT_TIMEOUT = 20.0
    COMMAND_TIMEOUT = 10.0

    # Addresses of all discovered devices by serial number. Scanning for one
    # device registers the others, which avoids scanning for them.
    _addresses: ClassVar[dict[str, str]] = {}

    def __init__(self, serial: str, name: str = ""):
        self.serial = serial
        self.name = name or serial

    @classmethod
    def value_keys(cls) -> tuple[str, ...]:
        """Return the keys of all values the device provides."""
        return cls.SENSOR_KEYS + cls.STATUS_KEYS

    async def read(self, retries: int = 3, retry_delay: float = 1.0) -> Values:
        """Connect to the device and read its values.

        Raises DeviceError if all attempts failed.
        """
        for attempt in range(1, retries + 2):
            try:
                return await self._read_once()
            except Exception as err:  # The BLE backends raise various exception types
                logger.warning("Failed to communicate with device %s (attempt %s of %s): %s",
                               self.name, attempt, retries + 1, err)
                logger.debug("Stack trace:", exc_info=True)
                # The address may have changed or not be known by the OS anymore
                AirthingsDevice._addresses.pop(self.serial, None)
            if attempt <= retries:
                await asyncio.sleep(retry_delay)
        raise DeviceError(f"Failed to communicate with device {self.serial}/{self.name}")

    async def _read_once(self) -> Values:
        address = await self._discover()
        logger.debug("Connect to %s (%s)", self.serial, address)
        async with BleakClient(address, timeout=self.CONNECT_TIMEOUT) as client:
            values = await self._read(client)
        return {key: value for key, value in values.items() if value is not None}

    @abstractmethod
    async def _read(self, client: BleakClient) -> dict[str, Any]:
        """Read the values from the connected device. None values are omitted."""

    async def _discover(self) -> str:
        if self.serial not in AirthingsDevice._addresses:
            logger.debug("Scan for device %s", self.serial)
            found = asyncio.Event()

            def detected(serial: str, address: str, rssi: int) -> None:
                if serial == self.serial:
                    found.set()

            async with _scanner(detected):
                try:
                    await asyncio.wait_for(found.wait(), self.SCAN_TIMEOUT)
                except TimeoutError:
                    raise DeviceError(f"Could not find device {self.serial}") from None
        return AirthingsDevice._addresses[self.serial]


def _scanner(callback: Callable[[str, str, int], None]) -> BleakScanner:
    """Create a scanner that registers the addresses of the Airthings devices."""
    def detected(device: BLEDevice, adv: AdvertisementData) -> None:
        serial = parse_serial_number(adv.manufacturer_data.get(AIRTHINGS_ID))
        if serial is None:
            return
        if AirthingsDevice._addresses.get(serial) != device.address:
            logger.info("Device %s found, address=%s", serial, device.address)
            AirthingsDevice._addresses[serial] = device.address
        callback(serial, device.address, adv.rssi)

    return BleakScanner(detection_callback=detected)


async def scan(timeout: float) -> list[ScanResult]:
    """Scan during timeout seconds and return the found Airthings devices."""
    found: dict[str, ScanResult] = {}

    def detected(serial: str, address: str, rssi: int) -> None:
        found[serial] = ScanResult(serial, address, rssi)

    async with _scanner(detected):
        await asyncio.sleep(timeout)
    return sorted(found.values(), key=lambda result: result.serial)
