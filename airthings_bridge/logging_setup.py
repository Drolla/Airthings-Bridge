"""Logging configuration."""

import logging.config
from typing import Any

FORMAT = "%(asctime)s - %(name)13s[%(levelname)7s] - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(log: str | dict[str, Any] | None, verbose: bool = False,
                      discovery: bool = False) -> None:
    """Configure the logging.

    Args:
        log: logging.config dictionary, or log file. The console is used if
            no or an empty log file is provided.
        verbose: The bridge logs debug messages instead of info messages.
        discovery: The console also shows the device discovery.
    """
    if isinstance(log, dict):
        logging.config.dictConfig(log)
        return
    if log:
        handler = {"class": "logging.FileHandler", "filename": log,
                   "encoding": "utf8", "mode": "a"}
    else:
        handler = {"class": "logging.StreamHandler", "stream": "ext://sys.stdout"}
    loggers = {
        "airthings_bridge": {"level": "WARNING"},
        "airthings_bridge.bridge": {"level": "DEBUG" if verbose else "INFO"},
        # Print alerts
        "airthings_bridge.consumers.alerts": {"level": "INFO"}}
    if discovery and not log:
        loggers["airthings_bridge.airthings.common"] = {"level": "INFO"}
    logging.config.dictConfig({
        "version": 1,
        "formatters": {"default": {"format": FORMAT, "datefmt": DATE_FORMAT}},
        "handlers": {"default": {"level": "DEBUG", "formatter": "default", **handler}},
        "root": {"level": "WARNING", "handlers": ["default"]},
        "loggers": loggers,
    })
