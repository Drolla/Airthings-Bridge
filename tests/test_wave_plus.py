"""Tests for airthings.wave_plus, with an emulated bleak BLE library."""

import struct
from unittest import mock

import pytest

from airthings_bridge.airthings import wave_plus as waveplus

SN = "2931234567"
ADDRESS = "AA:BB:CC:DD:EE:FF"

# Sensor data: version 1, humidity 45%, radon 33/44, temperature 21.5°C,
# pressure 980hPa, CO2 600ppm, VOC 120ppb
SENSOR_DATA = struct.pack("<BBBBHHHHHHHH",
                          1, 90, 0, 0, 33, 44, 2150, 49000, 600, 120, 0, 0)
# Control data: command 0x6d, illuminance 12, battery 2.95V (75%)
CONTROL_DATA = struct.pack("<BBL12B6H", 0x6d, 0, 0, 0, 12, *[0] * 10,
                           0, 0, 0, 0, 2950, 0)


def _advertisement(sn: int, company_id: int = 0x0334):
    return mock.Mock(manufacturer_data={
        company_id: struct.pack("<LBB", sn, 0, 0)})


class _Scanner:
    """BleakScanner emulation that reports the defined advertisements."""

    advertisements = []

    def __init__(self, detection_callback):
        self._callback = detection_callback

    async def __aenter__(self):
        for address, adv in self.advertisements:
            self._callback(mock.Mock(address=address), adv)
        return self

    async def __aexit__(self, *args):
        pass


class _Client:
    """BleakClient emulation of a Wave Plus device."""

    chunks = [CONTROL_DATA[:20], CONTROL_DATA[20:]]
    instances = []

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
        assert uuid == waveplus._WavePlusSensors._UUID
        return bytearray(SENSOR_DATA)

    async def start_notify(self, uuid, callback):
        self._callback = callback

    async def stop_notify(self, uuid):
        self._callback = None

    async def write_gatt_char(self, uuid, data):
        self.writes.append((uuid, data))
        for chunk in self.chunks:
            self._callback(None, bytearray(chunk))


@pytest.fixture(autouse=True)
def emulated_bleak(monkeypatch):
    monkeypatch.setattr(waveplus, "BleakScanner", _Scanner)
    monkeypatch.setattr(waveplus, "BleakClient", _Client)
    monkeypatch.setattr(waveplus.WavePlus, "_SCAN_TIMEOUT", 0.1)
    monkeypatch.setattr(waveplus._WavePlusControl, "_INDICATION_TIMEOUT",
                        0.1)
    monkeypatch.setattr(waveplus.WavePlus, "_sn2addr", {})
    monkeypatch.setattr(waveplus._WavePlusControl, "cache",
                        waveplus.time_cache.TimeCache())
    monkeypatch.setattr(waveplus.time, "sleep", lambda _: None)
    _Scanner.advertisements = [
        ("11:22:33:44:55:66", _advertisement(2931111111)),
        ("00:00:00:00:00:00", _advertisement(2932222222, company_id=0x0001)),
        (ADDRESS, _advertisement(int(SN)))]
    _Client.instances = []


def test_parse_serial_number():
    parse = waveplus.WavePlus._parse_serial_number
    assert parse(struct.pack("<LBB", 2931234567, 9, 9)) == "2931234567"
    assert parse(None) is None
    assert parse(b"\x01\x02") is None


def test_get_reads_sensor_and_control_data():
    assert waveplus.WavePlus(SN, "office").get() == {
        "humidity": 45.0, "radon_st": 33, "radon_lt": 44,
        "temperature": 21.5, "pressure": 980.0, "co2": 600.0, "voc": 120.0,
        "illuminance": 12, "battery": 75}
    client = _Client.instances[0]
    assert client.address == ADDRESS
    assert client.writes == [(waveplus._WavePlusControl._UUID, b"\x6d")]


def test_discovery_caches_all_wave_plus_devices():
    waveplus.WavePlus(SN).get()
    assert waveplus.WavePlus._sn2addr == {
        "2931111111": "11:22:33:44:55:66", SN: ADDRESS}


def test_control_data_is_cached():
    waveplus.WavePlus(SN).get()
    waveplus.WavePlus(SN).get()
    assert len(_Client.instances[0].writes) == 1
    assert len(_Client.instances[1].writes) == 0


def test_invalid_radon_value():
    assert waveplus._WavePlusSensors._conv2radon(16383) == 16383
    assert waveplus._WavePlusSensors._conv2radon(65535) == "N/A"


@pytest.mark.parametrize("data, message", [
    (b"\x01" + CONTROL_DATA[1:], "wrong command"),
    (CONTROL_DATA[:-2], "Wrong length"),
])
def test_control_data_check(data, message):
    control = waveplus._WavePlusControl(None)
    with pytest.raises(ValueError, match=message):
        control._data_check(data)


def test_unknown_device_raises_after_retries():
    with pytest.raises(ConnectionError, match="Failed to communicate"):
        waveplus.WavePlus("2930000000").get(retries=2)


def test_incomplete_indication_raises_after_retries(monkeypatch):
    monkeypatch.setattr(_Client, "chunks", [CONTROL_DATA[:20]])
    with pytest.raises(ConnectionError):
        waveplus.WavePlus(SN).get(retries=1)
    assert len(_Client.instances) == 2
