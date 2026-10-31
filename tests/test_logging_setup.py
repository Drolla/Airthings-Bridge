"""Tests for the logging configuration."""

import logging.config

from airthings_bridge.logging_setup import configure_logging


def test_log_file_survives_restarts(monkeypatch):
    configs = []
    monkeypatch.setattr(logging.config, "dictConfig", configs.append)
    configure_logging("bridge.log")
    assert configs[0]["handlers"]["default"]["mode"] == "a"
