"""Airthings Wave Plus sensor reader.

The two classes, WavePlus and Sensors, have been provided by Airthings under
the MIT licenses. The code has been slightly modified. The original code is
available here:
                https://github.com/Airthings/waveplus-reader

Copyright (C) 2020-2022 Andreas Drollinger
Portions Copyright (C) 2018 Airthings
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

# pylint: disable=broad-except

import contextlib
import logging
import struct
import time

# pylint: disable-next=E0401
from bluepy.btle import UUID, DefaultDelegate, Peripheral, Scanner

try:
    from libs import time_cache
except ImportError:
    import time_cache

logger = logging.getLogger(__name__)


class _Delegate(DefaultDelegate):
    """Bluetooth message receiver class.

    The handleNotification method will be called to receive notification or
    indication messages.
    With the WavePlus device it has been observed that an indication message
    is not received in one chunk, but that the handleNotification method is
    called multiple times. For this reason the received messages are
    concatenated.
    """

    def __init__(self):
        super().__init__()
        self._data = b""

    def handleNotification(self, handle: int, data: bytes) -> None:
        """Add a received notification message to the data buffer."""
        logger.debug("  Received notification (%s): %s", handle, data)
        self._data += data

    def get(self) -> bytes:
        """Get the received message."""
        return self._data


class _WavePlusSensors:
    """WavePlus sensor reading and parsing class.

    Args:
        peripheral: BluePy peripheral class instance
    """

    _UUID = UUID("b42e2a68-ade7-11e4-89d3-123b93f75cba")
    _FORMAT = "<BBBBHHHHHHHH"
    _KEYS = ("humidity", "radon_st", "radon_lt", "temperature", "pressure",
             "co2", "voc")

    def __init__(self, peripheral: Peripheral):
        self._periph = peripheral

    def get(self) -> dict[str, float | str]:
        """Read the sensor data and return it as dictionary."""
        raw_data = self._read_data()
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

    def _read_data(self) -> bytes:
        """Read the sensor data."""
        char = self._periph.getCharacteristics(uuid=self._UUID)[0]
        return char.read()

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

    Args:
        peripheral: BluePy peripheral class instance
    """

    _UUID = UUID("b42e2d06-ade7-11e4-89d3-123b93f75cba")
    _FORMAT = '<BBL12B6H'
    _KEYS = ("illuminance", "battery")  # Not implemented: measurement_periods
    _CMD = struct.pack('<B', 0x6d)
    _VBAT_MAX = 3.2
    _VBAT_MIN = 2.2
    _CACHE_TTL = 3600
    _CACHE_MAX_READS = 100

    cache = time_cache.TimeCache(ttl=_CACHE_TTL, max_read=_CACHE_MAX_READS)

    def __init__(self, peripheral: Peripheral):
        self._periph = peripheral

    def get(self) -> dict[str, int]:
        """Read the control data and return it as dictionary."""
        raw_data = self._read_data()
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

    def _read_data(self) -> bytes:
        """Read the control data (battery level and illuminance data)."""
        # Try to obtain the data from the cache
        periph_address = self._periph.addr
        try:
            raw_data = self.cache[periph_address]
        except KeyError:
            pass
        else:
            logger.debug("Control data: Address=%s, used cached data: %s",
                         periph_address, raw_data)
            return raw_data

        # Get the characteristic
        char = self._periph.getCharacteristics(uuid=self._UUID)[0]

        # Define the notification handle and turn notification on
        delegate = _Delegate()
        self._periph.setDelegate(delegate)

        logger.debug("Control characteristics: Handle=%s/%s",
                     char.valHandle,
                     char.getHandle())
        logger.debug("  CCCD value (indication disabled): %s",
                     self._periph.readCharacteristic(char.valHandle+2))
        self._periph.writeCharacteristic(char.valHandle+2, b"\x02\x00")
        logger.debug("  CCCD value (indication enabled): %s",
                     self._periph.readCharacteristic(char.valHandle+2))

        # Send command to the characteristic
        self._periph.writeCharacteristic(char.valHandle, self._CMD)

        # Wait on notification, get the data, and disable notification
        logger.debug("Waiting on notification")
        received = self._periph.waitForNotifications(10.0)
        while received and self._periph.waitForNotifications(0.5):
            pass
        self._periph.writeCharacteristic(char.valHandle+2, b"\x00\x00")
        if not received:
            raise ConnectionError("No control data notification received")
        raw_data = delegate.get()
        logger.debug("Received data: %s", raw_data)

        # Store the data in the cache, and return it
        self.cache[periph_address] = raw_data
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

    def __init__(self, serial_number: int | str, name: str = ""):
        # The constructor does nothing else than registering the serial number
        # and the nick name. If no nickname is provided, it is defaulted to the
        # serial number.
        self._periph: Peripheral | None = None
        self._sensor: _WavePlusSensors | None = None
        self._control: _WavePlusControl | None = None
        self._mac: str | None = None
        self._sn = str(serial_number)
        self._name = name if name != "" else str(serial_number)

    def stop(self) -> None:
        """Stop the BLE connection to the device.

        Call preferably this function to stop the connection instead of
        deleting the object instance to ensure a controlled disconnection.
        """
        with contextlib.suppress(Exception):
            self.disconnect()

    def __del__(self) -> None:
        self.stop()

    def discover(self) -> None:
        """Discover the device defined via the serial number.

        This method launches the BLE scanner 50 times to find the specified
        device. All discovered devices are cached. If a device that has to
        be discovered is already cached, no scanning is performed.
        """
        # Device is known, there is nothing to discover
        if self._mac is not None:
            return

        # Check if device is already known (from scanning another device)
        if self._sn in WavePlus._sn2addr:
            self._mac = WavePlus._sn2addr[self._sn]
            logger.info("  Device %s previously found, MAC address=%s",
                        self._sn, self._mac)
            return

        # Scan for the device
        logger.debug("Initialize scanning/discovery")
        scanner = Scanner().withDelegate(DefaultDelegate())
        for _ in range(50):
            logger.debug("  Run scan")
            devices = scanner.scan(0.1)  # 0.1 seconds scan period
            for dev in devices:
                manu_data = dev.getValueText(255)
                sn = self._parse_serial_number(manu_data)
                logger.debug("  Found device %s", sn)

                # A serial number has been found. Register it
                if sn is not None and sn not in WavePlus._sn2addr:
                    WavePlus._sn2addr[sn] = dev.addr

                # The device with the defined serial number has been found
                if sn == self._sn:
                    self._mac = dev.addr
                    logger.info("  Device %s found, MAC address=%s",
                                self._sn, self._mac)
                    return

    def connect(self) -> None:
        """Establish a BLE connection to the device.

        The BLE connection happens via the MAC address of the device. If the
        address is not known, the device is scanned. The addresses of each
        detected device is cached to limit the number of required device
        scanning.
        """
        logger.debug("Connect to %s", self._sn)

        # Ensure that the device (MAC) is known. Scan for the device otherwise
        self.discover()
        if self._mac is None:
            raise ConnectionError("Could not find device " + self._sn)

        # Connect to device
        if self._periph is None:
            self._periph = Peripheral(self._mac)
        if self._sensor is None:
            self._sensor = _WavePlusSensors(self._periph)
        if self._control is None:
            self._control = _WavePlusControl(self._periph)

    def disconnect(self) -> None:
        """Disconnect the connected device."""
        if self._periph is not None:
            with contextlib.suppress(Exception):
                self._periph.disconnect()
            self._periph = None
            self._sensor = None
            self._control = None

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
                self.connect()
                sensor_data = self._sensor.get()
                control_data = self._control.get()
                self.disconnect()
                logger.debug("  -> s=%s, c=%s", sensor_data, control_data)
                return {**sensor_data, **control_data}
            except Exception as error:
                self.disconnect()
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
    def _parse_serial_number(hex_string: str | None) -> str | None:
        """Parse the manufacturing data and return the serial number.

        Returns None if the provided data is invalid.
        """
        if hex_string is None:
            return None
        try:
            manu_data = struct.unpack("<HLBB", bytearray.fromhex(hex_string))
        except (ValueError, struct.error):
            return None
        if manu_data[0] != 0x0334:
            return None
        return str(manu_data[1])

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

    for wp_device in wp_devices:
        wp_device.stop()
    logger.warning("waveplus ended")
