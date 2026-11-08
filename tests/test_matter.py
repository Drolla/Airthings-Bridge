"""Tests for the Matter consumer, with an emulated matter.js bridge process."""

import asyncio
import hashlib
import json
import logging
import sys
from pathlib import Path
from unittest import mock

import pytest

from airthings_bridge.airthings import CorentiumHome2, WaveEnhance, WaveGen1, WaveMini, WavePlus
from airthings_bridge.bridge import Bridge
from airthings_bridge.config import MatterConfig, build_config
from airthings_bridge.consumers import matter
from airthings_bridge.errors import BridgeError
from airthings_bridge.readings import Cycle, Reading

CONFIG = MatterConfig(storage=Path("matter"))
DEVICES = [("2930123456", "office", WavePlus), ("2920123456", "cellar", WaveMini)]
VALUES = {"humidity": 59.0, "radon_st": 34, "radon_lt": 160, "temperature": 22.475,
          "pressure": 1012.36, "co2": 850.0, "voc": 50.0, "illuminance": 10, "battery": 85}
CYCLE = Cycle(1000, (Reading("office", VALUES, 990), Reading("cellar", {})))


ALL = ("pressure", "co2", "voc")


@pytest.mark.parametrize("model, radon_key, optional, expected", [
    (WavePlus, "radon_st", (), ["airQuality", "temperatureMeasurement",
                                "relativeHumidityMeasurement", "radonConcentrationMeasurement",
                                "powerSource"]),
    (WavePlus, "radon_st", ALL, ["airQuality", "temperatureMeasurement",
                                 "relativeHumidityMeasurement", "pressureMeasurement",
                                 "radonConcentrationMeasurement",
                                 "carbonDioxideConcentrationMeasurement",
                                 "totalVolatileOrganicCompoundsConcentrationMeasurement",
                                 "powerSource"]),
    (WavePlus, "radon_st", ("co2",), ["airQuality", "temperatureMeasurement",
                                      "relativeHumidityMeasurement",
                                      "radonConcentrationMeasurement",
                                      "carbonDioxideConcentrationMeasurement", "powerSource"]),
    (WaveGen1, "radon_st", ALL, ["airQuality", "temperatureMeasurement",
                                 "relativeHumidityMeasurement",
                                 "radonConcentrationMeasurement"]),
    (WaveGen1, "radon_year", (), ["airQuality", "temperatureMeasurement",
                                  "relativeHumidityMeasurement"]),
    (CorentiumHome2, "radon_year", (), ["airQuality", "temperatureMeasurement",
                                        "relativeHumidityMeasurement",
                                        "radonConcentrationMeasurement", "powerSource"]),
    (WaveMini, "radon_st", (), ["airQuality", "temperatureMeasurement",
                                "relativeHumidityMeasurement", "powerSource"]),
    (WaveMini, "radon_st", ALL, ["airQuality", "temperatureMeasurement",
                                 "relativeHumidityMeasurement", "pressureMeasurement",
                                 "totalVolatileOrganicCompoundsConcentrationMeasurement",
                                 "powerSource"]),
    (WaveEnhance, "radon_st", ALL, ["airQuality", "temperatureMeasurement",
                                    "relativeHumidityMeasurement", "pressureMeasurement",
                                    "carbonDioxideConcentrationMeasurement",
                                    "totalVolatileOrganicCompoundsConcentrationMeasurement",
                                    "powerSource"]),
])
def test_clusters(model, radon_key, optional, expected):
    assert matter.clusters(model, radon_key, optional) == expected


def test_endpoint():
    spec = matter.endpoint("2930123456", "a" * 40, WavePlus, "radon_st", ALL)
    assert spec["id"] == "airthings-2930123456"
    assert spec["clusters"] == matter.clusters(WavePlus, "radon_st", ALL)
    state = spec["state"]
    assert state["bridgedDeviceBasicInformation"] == {
        "vendorName": "Airthings", "productName": "Wave Plus", "nodeLabel": "a" * 32,
        "serialNumber": "2930123456",
        "uniqueId": hashlib.sha256(b"2930123456").hexdigest()[:32], "reachable": False}
    assert state["airQuality"] == {"airQuality": 0}
    assert state["radonConcentrationMeasurement"] == {"measurementUnit": 7,
                                                      "measurementMedium": 0}
    assert state["carbonDioxideConcentrationMeasurement"]["measurementUnit"] == 0
    assert state["totalVolatileOrganicCompoundsConcentrationMeasurement"]["measurementUnit"] == 0
    assert state["powerSource"]["batReplaceability"] == 2
    assert state["powerSource"]["batPercentRemaining"] is None
    assert "powerSource" not in matter.endpoint("2900123456", "g", WaveGen1, "radon_st")["state"]


@pytest.mark.parametrize("values, expected", [
    ({}, 0),
    ({"temperature": 20}, 0),
    ({"radon_st": 99, "co2": 799, "voc": 249}, 1),
    ({"radon_st": 100}, 2),
    ({"co2": 999}, 2),
    ({"voc": 250}, 2),
    ({"radon_st": 150, "co2": 400}, 4),
    ({"co2": 1000}, 4),
    ({"voc": 2000, "radon_st": 10}, 4),
])
def test_air_quality(values, expected):
    assert matter.air_quality(values, "radon_st") == expected


def test_cluster_state():
    assert matter.cluster_state(VALUES, "radon_st", ALL) == {
        "bridgedDeviceBasicInformation": {"reachable": True},
        "airQuality": {"airQuality": 2},
        "temperatureMeasurement": {"measuredValue": 2248},
        "relativeHumidityMeasurement": {"measuredValue": 5900},
        "pressureMeasurement": {"measuredValue": 1012},
        "radonConcentrationMeasurement": {"measuredValue": 34.0},
        "carbonDioxideConcentrationMeasurement": {"measuredValue": 850.0},
        "totalVolatileOrganicCompoundsConcentrationMeasurement": {"measuredValue": 0.05},
        "powerSource": {"batPercentRemaining": 170, "batChargeLevel": 0,
                        "batReplacementNeeded": False},
    }


def test_cluster_state_without_optional_values():
    state = matter.cluster_state(VALUES, "radon_st")
    assert not {"pressureMeasurement", "carbonDioxideConcentrationMeasurement",
                "totalVolatileOrganicCompoundsConcentrationMeasurement"} & set(state)
    # CO2 (850 ppm) still lowers the air quality
    assert state["airQuality"] == {"airQuality": 2}


def test_cluster_state_radon_option():
    state = matter.cluster_state(VALUES, "radon_lt")
    assert state["radonConcentrationMeasurement"] == {"measuredValue": 160.0}
    assert state["airQuality"] == {"airQuality": 4}


def test_cluster_state_missing_values():
    assert matter.cluster_state({}, "radon_st") == {
        "bridgedDeviceBasicInformation": {"reachable": False}}
    assert matter.cluster_state({"temperature": -1.234}, "radon_st") == {
        "bridgedDeviceBasicInformation": {"reachable": True},
        "temperatureMeasurement": {"measuredValue": -123}}


@pytest.mark.parametrize("battery, level, replace", [(20, 0, False), (19, 1, False),
                                                      (9, 2, True)])
def test_cluster_state_battery(battery, level, replace):
    assert matter.cluster_state({"battery": battery}, "radon_st")["powerSource"] == {
        "batPercentRemaining": battery * 2, "batChargeLevel": level,
        "batReplacementNeeded": replace}


# Emulated bridge.mjs. It logs the received messages to FAKE_LOG, and behaves
# according to FAKE_MODE: fail (end at the start), noready, crash (at the first
# update of the test) or hang (ignore stop).
FAKE_NODE = """
import json, os, sys
mode = os.environ.get("FAKE_MODE", "")
if mode == "fail":
    print("2026-11-07 10:00:00.000 ERROR    ServerNode  Port in use", file=sys.stderr)
    print("    at listen", file=sys.stderr, flush=True)
    sys.exit(3)
for line in sys.stdin:
    with open(os.environ["FAKE_LOG"], "a") as log:
        log.write(line)
    message = json.loads(line)
    if message["type"] == "init":
        print("Console output", flush=True)
        print("2026-11-07 10:00:00.000 NOTICE   ServerNode  Started", file=sys.stderr, flush=True)
        if mode != "noready":
            print(json.dumps({"type": "ready"}), flush=True)
    elif message["type"] == "update":
        crashed = os.environ["FAKE_LOG"] + ".crashed"
        if mode == "crash" and not os.path.exists(crashed):
            open(crashed, "w").close()
            sys.exit(1)
        print(json.dumps({"type": "online", "fabrics": 0}), flush=True)
        print(json.dumps({"type": "pairing", "manual": "1234-567-8901", "qr": "MT:Y.K9"}),
              flush=True)
    elif message["type"] == "stop" and mode != "hang":
        sys.exit(0)
"""


@pytest.fixture
def fake_node(tmp_path, monkeypatch, caplog):
    """Emulate the bridge process, and return a function returning its messages."""
    script = tmp_path / "fake_node.py"
    script.write_text(FAKE_NODE, encoding="utf-8")
    log = tmp_path / "messages.jsonl"
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setattr(matter.MatterBridge, "_command",
                        lambda self: [sys.executable, str(script)])
    monkeypatch.setattr(matter.MatterBridge, "RESTART_DELAY", 0.01)
    monkeypatch.setattr(matter.MatterBridge, "STOP_TIMEOUT", 1)
    caplog.set_level(logging.INFO, logger=matter.logger.name)

    def messages():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return messages


def test_lifecycle(fake_node, caplog):
    async def run():
        bridge = matter.MatterBridge(CONFIG, DEVICES)
        await bridge.start()
        await bridge.handle(CYCLE)
        await bridge.stop()

    asyncio.run(run())
    init, update, stop = fake_node()
    assert init["type"] == "init" and init["storage"] == "matter" and init["port"] == 5540
    assert [e["id"] for e in init["endpoints"]] == ["airthings-2930123456",
                                                    "airthings-2920123456"]
    assert update["type"] == "update"
    assert update["states"]["airthings-2930123456"]["temperatureMeasurement"] == {
        "measuredValue": 2248}
    assert update["states"]["airthings-2920123456"] == {
        "bridgedDeviceBasicInformation": {"reachable": False}}
    assert stop == {"type": "stop"}
    assert "Matter bridge online, 0 paired controller(s)" in caplog.text
    assert "Manual pairing code: 1234-567-8901" in caplog.text
    assert "qrcode.html?data=MT%3AY.K9" in caplog.text
    assert "ServerNode  Started" in caplog.text and "Console output" in caplog.text


def test_exposed_devices(fake_node):
    async def run():
        bridge = matter.MatterBridge(MatterConfig(Path("m"), devices=("cellar",)), DEVICES)
        await bridge.start()
        await bridge.handle(CYCLE)
        await bridge.stop()

    asyncio.run(run())
    init, update, _ = fake_node()
    assert [e["id"] for e in init["endpoints"]] == ["airthings-2920123456"]
    assert list(update["states"]) == ["airthings-2920123456"]


def test_start_failure(fake_node, monkeypatch, caplog):
    monkeypatch.setenv("FAKE_MODE", "fail")
    with pytest.raises(BridgeError, match="exit code 3"):
        asyncio.run(matter.MatterBridge(CONFIG, DEVICES).start())
    assert [(r.levelname, r.getMessage()) for r in caplog.records[:2]] == [
        ("ERROR", "ServerNode  Port in use"), ("ERROR", "    at listen")]


def test_not_ready(fake_node, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "noready")
    monkeypatch.setattr(matter.MatterBridge, "START_TIMEOUT", 0.5)
    with pytest.raises(BridgeError, match="not ready"):
        asyncio.run(matter.MatterBridge(CONFIG, DEVICES).start())
    assert [m["type"] for m in fake_node()] == ["init", "stop"]


def test_node_not_found(fake_node, monkeypatch):
    monkeypatch.setattr(matter.MatterBridge, "_command",
                        lambda self: [self._config.node, "bridge.mjs"])
    config = MatterConfig(Path("m"), node="no-such-node-executable")
    with pytest.raises(BridgeError, match="Node.js not found: 'no-such-node-executable'"):
        asyncio.run(matter.MatterBridge(config, DEVICES).start())


def test_matter_js_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(matter, "JS_DIR", tmp_path)
    with pytest.raises(BridgeError, match="npm ci"):
        asyncio.run(matter.MatterBridge(CONFIG, DEVICES).start())


def test_restart_after_crash(fake_node, monkeypatch, caplog):
    monkeypatch.setenv("FAKE_MODE", "crash")

    async def run():
        bridge = matter.MatterBridge(CONFIG, DEVICES)
        await bridge.start()
        await bridge.handle(CYCLE)
        for _ in range(200):
            await asyncio.sleep(0.02)
            if len(fake_node()) == 4 and bridge._ready.is_set():
                break
        await bridge.stop()

    asyncio.run(run())
    messages = fake_node()
    assert [m["type"] for m in messages] == ["init", "update", "init", "update", "stop"]
    # The restarted process gets the last states
    assert messages[3]["states"] == messages[1]["states"]
    assert "ended with exit code 1. Restart" in caplog.text


def test_last_states():
    async def run():
        bridge = matter.MatterBridge(CONFIG, DEVICES)
        bridge._process = mock.Mock()
        bridge._ready.set()
        with mock.patch.object(bridge, "_send", mock.AsyncMock()):
            await bridge.handle(CYCLE)
            await bridge.handle(Cycle(2000, (Reading("office", {"temperature": 20.0}, 1990),
                                             Reading("cellar", {}))))
        return bridge._states

    states = asyncio.run(run())
    office = states["airthings-2930123456"]
    assert office["temperatureMeasurement"] == {"measuredValue": 2000}
    assert office["radonConcentrationMeasurement"] == {"measuredValue": 34}
    assert office["airQuality"] == {"airQuality": 2}
    assert states["airthings-2920123456"] == {
        "bridgedDeviceBasicInformation": {"reachable": False}}


def test_kill_at_stop(fake_node, monkeypatch, caplog):
    monkeypatch.setenv("FAKE_MODE", "hang")

    async def run():
        bridge = matter.MatterBridge(CONFIG, DEVICES)
        await bridge.start()
        await bridge.stop()

    asyncio.run(run())
    assert "didn't stop, killed" in caplog.text


def test_handle_while_not_ready(caplog):
    asyncio.run(matter.MatterBridge(CONFIG, DEVICES).handle(CYCLE))
    assert "not ready, sensor data not passed" in caplog.text


def test_bridge_with_matter(fake_node, tmp_path):
    async def run():
        bridge = Bridge(build_config({"sn": ["2930123456, office"], "emulation": True,
                                      "matter": {"storage": str(tmp_path)}}))
        asyncio.get_running_loop().call_later(1, bridge.stop)
        await bridge.run()

    asyncio.run(run())
    assert [m["type"] for m in fake_node()] == ["init", "update", "stop"]
