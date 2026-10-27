"""Tests for the configuration loading and validation."""

from pathlib import Path

import pytest

from airthings_bridge.config import (
    DEFAULT_PERIOD,
    DeviceConfig,
    MailActionConfig,
    PrintActionConfig,
    build_config,
    load_config,
)
from airthings_bridge.errors import ConfigError

EXAMPLE_FILES = [Path(__file__).parent / "test_configuration.yaml",
                 Path(__file__).parent.parent / "airthings_bridge.yaml"]
SN = ["2931234567, office", "2931234569 living"]


@pytest.mark.parametrize("file", EXAMPLE_FILES, ids=lambda f: f.name)
def test_example_files_are_valid(file):
    config = load_config(file)
    assert config.devices == (DeviceConfig("2931234567", "my_office"),
                              DeviceConfig("2931234569", "my_living"))
    assert config.graph_decimations == ((691200.0, 8), (90000.0, 3))
    assert len(config.alerts) == 2
    assert config.alerts[1].sources == (("my_office", "radon_st"), ("my_living", "radon_st"))
    assert isinstance(config.alerts[1].actions[0], MailActionConfig)
    assert isinstance(config.alerts[1].actions[1], PrintActionConfig)
    assert config.smtp.security == "SSL"
    assert config.mqtt.publish == {"my_office": ["radon_st", "radon_lt"], "my_living": "*"}


def test_defaults():
    config = build_config({"sn": "2931234567"})
    assert config.devices == (DeviceConfig("2931234567", "2931234567"),)
    assert config.period == DEFAULT_PERIOD
    assert (config.port, config.csv, config.smtp, config.mqtt) == (None, None, None, None)
    assert config.alerts == ()
    assert not config.emulation and not config.developer


def test_overrides_have_precedence(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text("sn: [2931234567]\nport: 80\nlog: bridge.log\n", encoding="utf-8")
    config = load_config(file, {"port": 8080, "log": "", "sn": [], "csv": None})
    assert config.port == 8080
    assert config.log == ""
    assert config.devices[0].serial == "2931234567"
    assert config.file == file


def test_device_names():
    devices = build_config({"sn": SN + ["2931234560;cellar"]}).devices
    assert [d.name for d in devices] == ["office", "living", "cellar"]


@pytest.mark.parametrize("data, message", [
    ({}, "No serial number"),
    ({"sn": "123"}, "Invalid serial number"),
    ({"sn": ["2931234567 a", "2931234569 a"]}, "Duplicate device"),
    ({"sn": SN, "sensor": 1}, "Unknown configuration key"),
    ({"sn": SN, "period": 0}, "period"),
    ({"sn": SN, "retries": 1.5}, "retries"),
    ({"sn": SN, "port": "http"}, "port"),
    ({"sn": SN, "port": 70000}, "port"),
    ({"sn": SN, "log": 3}, "log"),
    ({"sn": SN, "smtp_server": {"port": 25}}, "smtp_server"),
    ({"sn": SN, "smtp_server": {"server": "s", "security": "x"}}, "security"),
    ({"sn": SN, "mqtt": {"host": "h"}}, "mqtt.publish"),
    ({"sn": SN, "mqtt": {"host": "h", "publish": {"cellar": "*"}}}, "Unknown device"),
    ({"sn": SN, "mqtt": {"host": "h", "publish": {"*": "*"}, "auth": {}}}, "username"),
])
def test_invalid_configurations(data, message):
    with pytest.raises(ConfigError, match=message):
        build_config(data)


def _alert(**changes):
    alert = {"sources": "office:radon_st", "trigger": {"above": 100},
             "actions": {"print": {"message": "%d"}}}
    alert.update(changes)
    return {"sn": SN, "alerts": [alert]}


def test_alert():
    alert = build_config(_alert()).alerts[0]
    assert alert.sources == (("office", "radon_st"),)
    assert alert.trigger == {"above": 100}
    assert alert.actions == (PrintActionConfig("%d"),)


@pytest.mark.parametrize("changes, message", [
    ({"sources": "office"}, r"alerts\[0\].sources: Invalid source"),
    ({"sources": "cellar:radon_st"}, "Unknown device 'cellar'"),
    ({"trigger": {"for": 10}}, r"alerts\[0\].trigger: .*'above' or 'below'"),
    ({"trigger": {"above": 1, "for": "1h"}}, "time span"),
    ({"actions": {"beep": {}}}, "'mail' or 'print'"),
    ({"actions": {"mail": {"from": "a@b.c", "to": "d@e.f"}}}, "smtp_server"),
    ({"actions": {"mail": {"to": "d@e.f"}}}, "'from' and 'to'"),
])
def test_invalid_alerts(changes, message):
    with pytest.raises(ConfigError, match=message):
        build_config(_alert(**changes))


def test_decimations():
    config = build_config({"sn": SN, "graph_decimations": {691200: 8, 90000: 3}})
    assert config.graph_decimations == ((691200.0, 8), (90000.0, 3))


@pytest.mark.parametrize("definitions", [
    {-1.0: 8, -5760: 3, -750: 1},  # Format of version 1.x
    {3600: 0},
    {3600: 2.5},
    {"1h": 2},
])
def test_invalid_decimations(definitions):
    with pytest.raises(ConfigError, match="2.0.0"):
        build_config({"sn": SN, "graph_decimations": definitions})


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="Unable to read"):
        load_config(tmp_path / "missing.yaml")
