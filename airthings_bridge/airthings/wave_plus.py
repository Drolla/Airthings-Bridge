"""Airthings Wave Plus sensor reader.

The two classes, WavePlus and Sensors, have been provided by Airthings under
the MIT licenses. The code has been slightly modified, and ported from the
bluepy to the bleak BLE library. The original code is available here:
                https://github.com/Airthings/waveplus-reader

Copyright (C) 2020-2026 Andreas Drollinger
Portions Copyright (C) 2018 Airthings
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

# pylint: disable=broad-except

import asyncio
import logging
import struct
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from airthings_bridge.airthings import time_cache

logger = logging.getLogger(__name__)

# Bluetooth manufacturer ID of Airthings
_AIRTHINGS_ID = 0x0334


class _WavePlusSensors:
    """WavePlus sensor reading and parsing class.

    Args:
        client: Connected bleak client
    """

    _UUID = "b42e2a68-ade7-11e4-89d3-123b93f75cba"
    _FORMAT = "<BBBBHHHHHHHH"
    _KEYS = ("humidity", "radon_st", "radon_lt", "temperature", "pressure",
             "co2", "voc")

    def __init__(self, client: BleakClient):
        self._client = client

    async def get(self) -> dict[str, float | str]:
        """Read the sensor data and return it as dictionary."""
        raw_data = bytes(await self._client.read_gatt_char(self._UUID))
        try:
            self._data_check(raw_data)
        except ValueError as error:
            logger.error(error)
            return {}
        value_array = struct.unpack(self._FORMAT, raw_data)
        return self._decode(value_array)

    def _data_check(self, raw_data: bytes) -> None:
        """Check the received data and raise an error if it is not valid."""
        sensor_version = raw_data[0]
        if sensor_version != 1:
            raise ValueError(f"Unknown sensor version {sensor_version}")

    def _decode(self, value_array: tuple[int, ...]) -> dict[str, float | str]:
        """Parse the obtained data and format it in a dictionary."""
        return {
            "humidity": value_array[1]/2.0,
            "radon_st": self._conv2radon(value_array[4]),
            "radon_lt": self._conv2radon(value_array[5]),
            "temperature": value_array[6]/100.0,
            "pressure": value_array[7]/50.0,
            "co2": value_array[8]*1.0,
            "voc": value_array[9]*1.0
        }

    @classmethod
    def get_keys(cls) -> tuple[str, ...]:
        """Get the keys provided by this class."""
        return cls._KEYS

    @staticmethod
    def _conv2radon(radon_raw: int) -> int | str:
        """Validate or invalidate the radon value."""
        if 0 <= radon_raw <= 16383:
            return radon_raw
        return "N/A"


class _WavePlusControl:
    """WavePlus control data reading and parsing class.

    The control data is requested by a command, and received by one or
    multiple indication messages.

    Args:
        client: Connected bleak client
    """

    _UUID = "b42e2d06-ade7-11e4-89d3-123b93f75cba"
    _FORMAT = '<BBL12B6H'
    _KEYS = ("illuminance", "battery")  # Not implemented: measurement_periods
    _CMD = struct.pack('<B', 0x6d)
    _VBAT_MAX = 3.2
    _VBAT_MIN = 2.2
    _CACHE_TTL = 3600
    _CACHE_MAX_READS = 100
    _INDICATION_TIMEOUT = 10.0

    cache = time_cache.TimeCache(ttl=_CACHE_TTL, max_read=_CACHE_MAX_READS)

    def __init__(self, client: BleakClient):
        self._client = client

    async def get(self) -> dict[str, int]:
        """Read the control data and return it as dictionary."""
        raw_data = await self._read_data()
        try:
            self._data_check(raw_data)
        except ValueError as error:
            logger.error(error)
            return {}
        value_array = struct.unpack(self._FORMAT, raw_data)
        return self._decode(value_array)

    def _data_check(self, raw_data: bytes) -> None:
        """Check the received data and raise an error if it is not valid."""
        cmd = raw_data[0:1]
        if cmd != self._CMD:
            raise ValueError(f"Got data for wrong command: Expected "
                             f"{self._CMD.hex()}, got {cmd.hex()}")

        req_length = struct.calcsize(self._FORMAT)
        if len(raw_data) != req_length:
            raise ValueError(f"Wrong length data: Expected {req_length}, "
                             f"received {len(raw_data)}")

    def _decode(self, value_array: tuple[int, ...]) -> dict[str, int]:
        """Parse the obtained data and format it in a dictionary."""
        illuminance = value_array[4]

        vbat = value_array[19] / 1000.0
        vbat_pct = (vbat - self._VBAT_MIN) / (self._VBAT_MAX - self._VBAT_MIN)
        vbat_pct = round(100 * max(0.0, min(1.0, vbat_pct)))

        return {"illuminance": illuminance, "battery": vbat_pct}

    async def _read_data(self) -> bytes:
        """Read the control data (battery level and illuminance data)."""
        # Try to obtain the data from the cache
        address = self._client.address
        try:
            raw_data = self.cache[address]
        except KeyError:
            pass
        else:
            logger.debug("Control data: Address=%s, used cached data: %s",
                         address, raw_data)
            return raw_data

        # An indication message may be received in multiple chunks. Collect
        # them until the expected data length is reached.
        data = bytearray()
        complete = asyncio.Event()
        req_length = struct.calcsize(self._FORMAT)

        def handle_indication(_: BleakGATTCharacteristic,
                              chunk: bytearray) -> None:
            logger.debug("  Received indication: %s", chunk)
            data.extend(chunk)
            if len(data) >= req_length:
                complete.set()

        # Enable the indications, send the command and wait on the data
        await self._client.start_notify(self._UUID, handle_indication)
        try:
            logger.debug("Send command and wait on indication")
            await self._client.write_gatt_char(self._UUID, self._CMD)
            await asyncio.wait_for(complete.wait(), self._INDICATION_TIMEOUT)
        except TimeoutError:
            raise ConnectionError(
                    "No control data indication received") from None
        finally:
            await self._client.stop_notify(self._UUID)
        raw_data = bytes(data)
        logger.debug("Received data: %s", raw_data)

        # Store the data in the cache, and return it
        self.cache[address] = raw_data
        return raw_data

    @classmethod
    def get_keys(cls) -> tuple[str, ...]:
        """Get the keys provided by this class."""
        return cls._KEYS


class WavePlus:
    """Airthings Wave Plus sensor reader class.

    This class provides all the functionalities to access a Wave Plus sensor
    and read its sensor values. The class instance is assigned to a specific
    sensor defined by its serial number:

        wp_device = waveplus.WavePlus(serial_number, my_sensor_name)

    The sensor data is provided by the get() method that handles
    also the connection to the device:

        wp_device.get()

    The returned sensor data is returned in form of a dictionary.

    Args:
        serial_number: Serial number of the device
        [name]: Optional nick name of the device
    """

    # Serial number & device address cache that allows avoiding new scan phases
    # if multiple WavePlus devices are used (class variable)
    _sn2addr: dict[str, str] = {}

    _SCAN_TIMEOUT = 5.0
    _CONNECT_TIMEOUT = 20.0

    def __init__(self, serial_number: int | str, name: str = ""):
        # The constructor does nothing else than registering the serial number
        # and the nick name. If no nickname is provided, it is defaulted to the
        # serial number.
        self._sn = str(serial_number)
        self._name = name if name != "" else str(serial_number)

    def stop(self) -> None:
        """Stop the BLE connection to the device.

        The connection is only open while the data is read, so there is
        nothing to do. The method is kept for compatibility reasons.
        """

    async def _discover(self) -> str:
        """Discover the device defined via the serial number.

        This method scans the BLE devices until the specified device is found.
        All discovered Wave Plus devices are cached. If a device that has to
        be discovered is already cached, no scanning is performed. Returns the
        device address.
        """
        # Check if device is already known (e.g. from scanning another device)
        if self._sn in WavePlus._sn2addr:
            return WavePlus._sn2addr[self._sn]

        found = asyncio.Event()

        def detected(device: BLEDevice, adv: AdvertisementData) -> None:
            sn = self._parse_serial_number(
                    adv.manufacturer_data.get(_AIRTHINGS_ID))
            if sn is None:
                return
            if sn not in WavePlus._sn2addr:
                logger.info("  Device %s found, address=%s", sn,
                            device.address)
                WavePlus._sn2addr[sn] = device.address
            if sn == self._sn:
                found.set()

        logger.debug("Scan for device %s", self._sn)
        async with BleakScanner(detection_callback=detected):
            try:
                await asyncio.wait_for(found.wait(), self._SCAN_TIMEOUT)
            except TimeoutError:
                raise ConnectionError(
                        "Could not find device " + self._sn) from None
        return WavePlus._sn2addr[self._sn]

    async def _read(self) -> dict[str, float | str]:
        """Connect to the device and read the sensor and control data."""
        address = await self._discover()
        logger.debug("Connect to %s (%s)", self._sn, address)
        async with BleakClient(address, timeout=self._CONNECT_TIMEOUT) \
                as client:
            sensor_data = await _WavePlusSensors(client).get()
            control_data = await _WavePlusControl(client).get()
        logger.debug("  -> s=%s, c=%s", sensor_data, control_data)
        return {**sensor_data, **control_data}

    def get(self, retries: int = 3,
            retry_delay: float = 1.0) -> dict[str, float | str]:
        """Return the sensor data, the battery level and the illuminance.

        This method connects to the device, reads the raw sensor data and
        translates it into a sensor data dictionary, and disconnect from the
        device again. If this sequence fails, additional retries can be
        optionally performed.

        Args:
            [retries]: Number of extra attempts to read from the device.
                       Default=3.
            [retry_delay]: Amount of time in seconds to wait before attempting
                           reconnection.
        """
        logger.debug("Reading sensor data for device %s", self._name)

        for attempt in range(1, retries + 2):
            try:
                return asyncio.run(self._read())
            except Exception as error:
                logger.warning("Failed to communicate with device "
                               "%s (attempt %s of %s): %s",
                               self._name, attempt, retries + 1, error)
                logger.debug("  Stack trace:", exc_info=True)
            if attempt <= retries:
                logger.debug("Retrying in %s seconds", retry_delay)
                time.sleep(retry_delay)

        raise ConnectionError(
            f"Failed to communicate with device {self._sn}/{self._name}")

    @classmethod
    def get_keys(cls) -> tuple[str, ...]:
        """Get the keys provided by this class."""
        return _WavePlusSensors.get_keys() + _WavePlusControl.get_keys()

    @staticmethod
    def _parse_serial_number(manu_data: bytes | None) -> str | None:
        """Parse the Airthings manufacturer data and return the serial number.

        Returns None if the provided data is invalid.
        """
        if manu_data is None:
            return None
        try:
            serial_number, _, _ = struct.unpack("<LBB", manu_data)
        except struct.error:
            return None
        return str(serial_number)

    @property
    def name(self) -> str:
        """Nick name of the device."""
        return self._name


#############################################
# Main
#############################################

if __name__ == "__main__":
    import sys

    def help_and_exit() -> None:
        print("Usage: waveplus.py <period> "
              "<serial_number_1> [serial_number_2] ..")
        sys.exit(1)

    # Configure the logger
    logger.setLevel(logging.DEBUG)
    log_handler = logging.StreamHandler()
    log_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_handler)

    # Handle the arguments (1: sensor read period, 2..: serial numbers)
    if len(sys.argv) < 3 or not sys.argv[1].isdigit():
        help_and_exit()
    period = int(sys.argv[1])
    serial_numbers = []
    for serial_n in sys.argv[2:]:
        if not serial_n.isdigit() or len(serial_n) != 10:
            help_and_exit()
        serial_numbers.append(serial_n)

    # Setup the devices
    wp_devices = []
    for serial_n in serial_numbers:
        logger.info("Setup device %s", serial_n)
        wp_devices.append(WavePlus(serial_n))

    logger.info("Entering into sensor read loop. Exit with Ctrl+C")

    # Print the table header that includes all sensor names
    keys = WavePlus.get_keys()
    log_separator = "+" + ((("-" * 12) + "+") * (len(keys)+1))
    log_format = log_separator + "\n|" + \
        ("{:>12}|" * (len(keys)+1)) + "\n" + log_separator
    logger.info(log_format.format("Device", *keys))

    # Infinite loop where all sensors are repeatedly read
    try:
        while True:
            for wp_device in wp_devices:
                try:
                    device_data = wp_device.get()
                    device_values = [device_data.get(key, "") for key in keys]
                    logger.info(
                            log_format.format(wp_device.name, *device_values))
                except ConnectionError as err:
                    logger.error("Failed to communicate with device %s: %s",
                                 wp_device.name, err)
            time.sleep(period)
    except KeyboardInterrupt:
        pass

    logger.warning("waveplus ended")
