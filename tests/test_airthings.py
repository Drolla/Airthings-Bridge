"""Tests for the Airthings devices, with an emulated bleak BLE library.

The byte vectors are taken from the airthings-ble tests.
"""

import asyncio
import struct
from unittest import mock

import cbor2
import pytest

from airthings_bridge import airthings
from airthings_bridge.airthings import atom, common
from airthings_bridge.airthings.common import battery_three_cells, battery_two_cells
from airthings_bridge.airthings.corentium_home2 import CorentiumHome2
from airthings_bridge.airthings.wave_enhance import WaveEnhance
from airthings_bridge.airthings.wave_gen1 import WaveGen1
from airthings_bridge.airthings.wave_mini import WaveMini
from airthings_bridge.airthings.wave_plus import WavePlus
from airthings_bridge.airthings.wave_radon import WaveRadon
from airthings_bridge.errors import ConfigError, DeviceError

SN = "2930123456"
ADDRESS = "AA:BB:CC:DD:EE:FF"

WAVE_PLUS_DATA = bytes.fromhex("01380d800b002200bd094cc31d036c0000007d05")
WAVE_PLUS_RESPONSE = bytes.fromhex("6d00600c04000100008211ff00000000c04c20001f3560007006b80b0900")
WAVE_RADON_DATA = bytes.fromhex("013860f009001100a709ffffffffffff0000ffff")
WAVE_MINI_DATA = bytes.fromhex("1800327431c168102e000000ff940700ffffffff")
WAVE_MINI_RESPONSE = bytes.fromhex(
    "6d0064000000c800000001020304f4015802bc02000020038403b80b4c04b0040000")
WAVE_ENHANCE_RESPONSE = bytes.fromhex(
    "0345a1b281a2006d32393939392f302f333130313202583ea9634e4f49182763544d501972f06348554d"
    "190d2f63434f321902dc63564f43190115634c555801635052531a005f364663424154190b346354494d"
    "1876")
CORENTIUM_HOME_2_RESPONSE = bytes.fromhex(
    "0345cca481a2006d32393939392f302f3331303132025831a8635232340363523744076352333007635231"
    "591263544d501973d76348554d190d8c63424154190b816354494d19061d")


def _advertisement(serial: int, company_id: int = 0x0334, rssi: int = -60) -> mock.Mock:
    return mock.Mock(manufacturer_data={company_id: struct.pack("<LBB", serial, 0, 0)},
                     rssi=rssi)


class _Scanner:
    """BleakScanner emulation that reports the defined advertisements."""

    advertisements: list = []

    def __init__(self, detection_callback):
        self._callback = detection_callback

    async def __aenter__(self):
        for address, adv in self.advertisements:
            self._callback(mock.Mock(address=address), adv)
        return self

    async def __aexit__(self, *args):
        pass


class _Client:
    """BleakClient emulation, with characteristic values and command responses."""

    characteristics: dict[str, bytes] = {}
    notifications: list[bytes] = []
    instances: list["_Client"] = []

    def __init__(self, address, timeout):
        self.address = address
        self.writes = []
        self._callback = None
        _Client.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def read_gatt_char(self, uuid):
        return bytearray(self.characteristics[uuid])

    async def start_notify(self, uuid, callback):
        self._callback = callback

    async def stop_notify(self, uuid):
        self._callback = None

    async def write_gatt_char(self, uuid, data):
        self.writes.append((uuid, bytes(data)))
        for notification in self.notifications:
            self._callback(None, bytearray(notification))


@pytest.fixture(autouse=True)
def emulated_bleak(monkeypatch):
    monkeypatch.setattr(common, "BleakScanner", _Scanner)
    monkeypatch.setattr(common, "BleakClient", _Client)
    monkeypatch.setattr(common.AirthingsDevice, "SCAN_TIMEOUT", 0.1)
    monkeypatch.setattr(common.AirthingsDevice, "COMMAND_TIMEOUT", 0.1)
    monkeypatch.setattr(common.AirthingsDevice, "_addresses", {})
    monkeypatch.setattr(WavePlus, "_responses", common.ResponseCache(3600, 100))
    monkeypatch.setattr(WaveMini, "_responses", common.ResponseCache(3600, 100))
    _Scanner.advertisements = [
        ("11:22:33:44:55:66", _advertisement(2930111111)),
        ("00:00:00:00:00:00", _advertisement(2930222222, company_id=0x0001)),
        (ADDRESS, _advertisement(int(SN)))]
    _Client.characteristics = {WavePlus.DATA_UUID: WAVE_PLUS_DATA}
    _Client.notifications = [WAVE_PLUS_RESPONSE[:20], WAVE_PLUS_RESPONSE[20:]]
    _Client.instances = []


def _read(device, retries=3):
    return asyncio.run(device.read(retries=retries, retry_delay=0))


# ---------- device independent ----------

def test_parse_serial_number():
    parse = common.parse_serial_number
    assert parse(struct.pack("<LBB", 2930123456, 9, 9)) == "2930123456"
    assert parse(struct.pack("<L", 12345)) is None
    assert parse(None) is None
    assert parse(b"\x01\x02") is None


@pytest.mark.parametrize("serial, model", [
    ("2900123456", WaveGen1), ("2920123456", WaveMini), ("2930123456", WavePlus),
    ("2950123456", WaveRadon), ("3210123456", WaveEnhance), ("3220123456", WaveEnhance),
    ("3250123456", CorentiumHome2), ("2960123456", None), ("1234567890", None),
])
def test_model_for_serial(serial, model):
    assert airthings.model_for_serial(serial) is model


def test_create_device():
    device = airthings.create_device("2950123456", "cellar")
    assert isinstance(device, WaveRadon)
    assert (device.serial, device.name) == ("2950123456", "cellar")
    assert airthings.create_device("2950123456").name == "2950123456"
    with pytest.raises(ConfigError, match="Unsupported"):
        airthings.create_device("1234567890")


@pytest.mark.parametrize("voltage, level", [
    (3.1, 100), (3.0, 100), (2.9, 90.5), (2.7, 67), (2.55, 40.5), (2.35, 16.5),
    (2.15, 2.5), (2.1, 0), (2.0, 0)])
def test_battery_two_cells(voltage, level):
    assert battery_two_cells(voltage) == round(level)


@pytest.mark.parametrize("voltage, level", [
    (4.6, 100), (4.35, 92.5), (4.0, 69.67), (3.8, 48.67), (3.5, 31.44), (3.0, 15.33),
    (2.3, 0)])
def test_battery_three_cells(voltage, level):
    assert battery_three_cells(voltage) == round(level)


def test_response_cache(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(common.time, "monotonic", lambda: now[0])
    cache = common.ResponseCache(ttl=10, max_reads=2)
    assert cache.get("a") is None
    cache.put("a", b"x")
    assert [cache.get("a"), cache.get("a"), cache.get("a")] == [b"x", b"x", None]
    cache.put("a", b"y")
    now[0] += 11
    assert cache.get("a") is None


def test_read():
    assert _read(WavePlus(SN, "office")) == {
        "humidity": 28.0, "radon_st": 11, "radon_lt": 34, "temperature": 24.93,
        "pressure": 999.92, "co2": 797.0, "voc": 108.0, "illuminance": 0, "battery": 100}
    client = _Client.instances[0]
    assert client.address == ADDRESS
    assert client.writes == [(WavePlus.COMMAND_UUID, b"\x6d")]


def test_discovery_registers_all_airthings_devices():
    _read(WavePlus(SN))
    assert common.AirthingsDevice._addresses == {
        "2930111111": "11:22:33:44:55:66", SN: ADDRESS}


def test_command_response_is_cached():
    _read(WavePlus(SN))
    _read(WavePlus(SN))
    assert len(_Client.instances[0].writes) == 1
    assert len(_Client.instances[1].writes) == 0


def test_unknown_device_raises_after_retries():
    with pytest.raises(DeviceError, match="Failed to communicate"):
        _read(WavePlus("2930000000"), retries=2)


def test_incomplete_response_raises_after_retries():
    _Client.notifications = [WAVE_PLUS_RESPONSE[:20]]
    with pytest.raises(DeviceError):
        _read(WavePlus(SN), retries=1)
    assert len(_Client.instances) == 2


def test_failed_attempt_forgets_the_address():
    _Client.characteristics = {}
    with pytest.raises(DeviceError):
        _read(WavePlus(SN), retries=0)
    assert SN not in common.AirthingsDevice._addresses


def test_scan(monkeypatch):
    monkeypatch.setattr(common.asyncio, "sleep", mock.AsyncMock())
    assert asyncio.run(common.scan(10)) == [
        common.ScanResult("2930111111", "11:22:33:44:55:66", -60),
        common.ScanResult(SN, ADDRESS, -60)]


# ---------- Wave Plus, Wave Radon ----------

def test_wave_plus_data():
    assert WavePlus.decode_data(bytes.fromhex("01380d800b0022000cfe4cc31d036c0000007d05")
                                )["temperature"] == -5.0


@pytest.mark.parametrize("data, missing", [
    ("01ff3a0025000000ffffffff5a02ffff0000ffff", {"humidity", "temperature", "pressure", "voc"}),
    ("01380d800b002200ffff4cc31d036c0000007d05", {"temperature"}),
    ("01380d8000400040bd094cc31d036c0000007d05", {"radon_st", "radon_lt"}),
])
def test_wave_plus_invalid_values(data, missing):
    values = WavePlus.decode_data(bytes.fromhex(data))
    assert {key for key, value in values.items() if value is None} == missing


@pytest.mark.parametrize("data", [b"\x02" + WAVE_PLUS_DATA[1:], WAVE_PLUS_DATA[:-2]])
def test_wave_plus_invalid_data(data):
    with pytest.raises(DeviceError, match="Invalid sensor data"):
        WavePlus.decode_data(data)


@pytest.mark.parametrize("response", [b"\x01" + WAVE_PLUS_RESPONSE[1:], WAVE_PLUS_RESPONSE[:-2]])
def test_wave_plus_invalid_command_response(response):
    with pytest.raises(DeviceError, match="Invalid command response"):
        WavePlus.decode_command_response(response)


def test_wave_plus_illuminance_and_battery():
    response = struct.pack("<BBL12B6H", 0x6d, 0, 0, 0, 12, *[0] * 10, 0, 0, 0, 0, 2700, 0)
    assert WavePlus.decode_command_response(response) == {"illuminance": 12, "battery": 67}


def test_wave_radon():
    _Client.characteristics = {WaveRadon.DATA_UUID: WAVE_RADON_DATA}
    assert _read(WaveRadon(SN)) == {
        "humidity": 28.0, "radon_st": 9, "radon_lt": 17, "temperature": 24.71,
        "illuminance": 0, "battery": 100}
    assert _Client.instances[0].writes == [(WaveRadon.COMMAND_UUID, b"\x6d")]


# ---------- Wave Mini ----------

def test_wave_mini():
    _Client.characteristics = {WaveMini.DATA_UUID: WAVE_MINI_DATA}
    _Client.notifications = [WAVE_MINI_RESPONSE]
    assert _read(WaveMini(SN)) == {
        "illuminance": 9, "temperature": 24.31, "pressure": 989.14, "humidity": 42.0,
        "voc": 46.0, "battery": 15}


def test_wave_mini_values_before_first_measurement():
    values = WaveMini.decode_data(bytes.fromhex("ff" * 20))
    assert {key for key, value in values.items() if value is not None} == set()


@pytest.mark.parametrize("raw_temperature, temperature", [
    ("135b", -40.0), ("125b", None), ("c391", 100.0), ("c491", None)])
def test_wave_mini_temperature_bounds(raw_temperature, temperature):
    data = bytes.fromhex(f"1800{raw_temperature}31c168102e000000ff940700ffffffff")
    assert WaveMini.decode_data(data)["temperature"] == temperature


# ---------- Wave Gen 1 ----------

def test_wave_gen1():
    _Client.characteristics = {
        WaveGen1.TEMPERATURE_UUID: bytes.fromhex("0cfe"),
        WaveGen1.HUMIDITY_UUID: bytes.fromhex("8c0d"),
        WaveGen1.RADON_ST_UUID: bytes.fromhex("ffff"),
        WaveGen1.RADON_LT_UUID: bytes.fromhex("6400"),
        WaveGen1.ILLUMINANCE_UUID: bytes.fromhex("b20c")}
    assert _read(WaveGen1(SN)) == {
        "temperature": -5.0, "humidity": 34.68, "radon_lt": 100, "illuminance": 69}


# ---------- Atom: Wave Enhance, Corentium Home 2 ----------

def _fragments(response: bytes, size: int) -> list[bytes]:
    step = size - 3
    parts = [response[start:start + step] for start in range(0, len(response), step)]
    return [b"\x10" + len(parts).to_bytes(2, "little") + parts[0]] + [
        b"\x00" + position.to_bytes(2, "little") + part
        for position, part in enumerate(parts[1:], start=2)]


def test_atom_request():
    assert atom.build_request(bytes.fromhex("a1b2")) == bytes.fromhex(
        "0301a1b281a100") + cbor2.dumps("29999/0/31012")


@pytest.mark.parametrize("fragments, expected", [
    (["100100aabbcc"], "aabbcc"),
    (["100300aa", "000200bb", "000300cc"], "aabbcc"),
    (["100300aa", "000300cc", "000200bb"], "aabbcc"),
    (["000300cc", "100300aa", "000200bb"], "aabbcc"),
    (["300200aa", "200200bb"], "aabb"),
    (["400200dd", "100200aa", "000200bb"], "aabb"),
    (["100200aa", "000100dd", "000200bb"], "aabb"),
    (["100200aa", "300100dd", "000200bb"], "aabb"),
])
def test_atom_fragments_are_reassembled(fragments, expected):
    receiver = atom.FragmentReceiver()
    for fragment in fragments:
        receiver(None, bytearray.fromhex(fragment))
    assert receiver.complete.is_set()
    assert receiver.message == bytes.fromhex(expected)


@pytest.mark.parametrize("fragments", [
    ["100300aa", "000200bb"], ["000200bb", "000300cc"], ["100000aa"], [""], ["10"],
    ["110100aa"], ["100200aa", "200200bb"], ["100200aa", "000100bb"],
])
def test_atom_incomplete_fragments(fragments):
    receiver = atom.FragmentReceiver()
    for fragment in fragments:
        receiver(None, bytearray.fromhex(fragment))
    assert not receiver.complete.is_set()


def test_atom_response():
    assert atom.parse_response(CORENTIUM_HOME_2_RESPONSE, bytes.fromhex("cca4")) == {
        "R24": 3, "R7D": 7, "R30": 7, "R1Y": 18, "TMP": 29655, "HUM": 3468, "BAT": 2945,
        "TIM": 1565}


@pytest.mark.parametrize("response", [
    "03845f9381a2006a31372f302f33313130300204",
    "0345123482a2006a31372f302f33313130300204",
    "03451234",
    "0345123481a2006a31372f302f333131",
    "0345123481a2006a31372f302f33313130300204",  # Other path
])
def test_atom_invalid_responses(response):
    with pytest.raises(DeviceError):
        atom.parse_response(bytes.fromhex(response), bytes.fromhex("1234"))


def test_atom_wrong_random_bytes():
    with pytest.raises(DeviceError):
        atom.parse_response(CORENTIUM_HOME_2_RESPONSE, bytes.fromhex("0000"))


def _read_atom(device_class, response):
    random_bytes = response[2:4]
    _Scanner.advertisements.append((ADDRESS, _advertisement(3250123456)))
    _Client.notifications = _fragments(response, 20)
    with mock.patch.object(atom.os, "urandom", return_value=random_bytes):
        values = _read(device_class("3250123456"))
    assert _Client.instances[0].writes == [(atom.REQUEST_UUID, atom.build_request(random_bytes))]
    return values


def test_wave_enhance():
    assert _read_atom(WaveEnhance, WAVE_ENHANCE_RESPONSE) == {
        "humidity": 33.75, "temperature": 21.09, "pressure": pytest.approx(974.97, abs=0.01),
        "co2": 732, "voc": 277, "noise": 39, "lux": 1, "battery": 87}


def test_corentium_home2():
    assert _read_atom(CorentiumHome2, CORENTIUM_HOME_2_RESPONSE) == {
        "radon_st": 3, "radon_week": 7, "radon_month": 7, "radon_lt": 18, "radon_year": 18,
        "temperature": 23.4, "humidity": 34.68, "battery": 95}
