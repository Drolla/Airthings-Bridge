"""Tests for the logging configuration."""

import logging.config

import pytest

from airthings_bridge.logging_setup import configure_logging


def test_log_file_survives_restarts(monkeypatch):
    configs = []
    monkeypatch.setattr(logging.config, "dictConfig", configs.append)
    configure_logging("bridge.log")
    assert configs[0]["handlers"]["default"]["mode"] == "a"


@pytest.mark.parametrize(("log", "discovery", "shown"), [
    ("", True, True), (None, True, True), ("bridge.log", True, False), (None, False, False)])
def test_device_discovery_on_console(monkeypatch, log, discovery, shown):
    configs = []
    monkeypatch.setattr(logging.config, "dictConfig", configs.append)
    configure_logging(log, discovery=discovery)
    assert ("airthings_bridge.airthings.common" in configs[0]["loggers"]) is shown
