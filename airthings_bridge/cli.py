"""Command line entry point.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import argparse
import asyncio
import contextlib
import logging
import sys
from collections.abc import Coroutine
from typing import Any

from airthings_bridge import __version__
from airthings_bridge.bridge import Bridge
from airthings_bridge.config import load_config
from airthings_bridge.errors import BridgeError, ConfigError
from airthings_bridge.logging_setup import configure_logging

logger = logging.getLogger(__name__)


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(
        prog="airthings-bridge",
        description="Airthings BLE sensors to Wifi/LAN Bridge")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--period", type=int, help="Time in seconds between reading the sensor values")
    parser.add_argument("--data_retention", type=int, help="Data retention time in seconds")
    parser.add_argument(
        "sn", metavar="sn", type=str, nargs="*",
        help="""10-digit serial number of a device (see under the magnetic backplate).
                This number can be combined with a device nickname, separated by a
                comma from the serial number ("2931234567, my_office")""")
    parser.add_argument("--port", type=int, help="Port of the HTTP web server")
    parser.add_argument("--csv", help="CSV file to store data")
    parser.add_argument("--log", help="Log file. If not specified the stdout is used")
    parser.add_argument("--config", help="YAML configuration file")
    parser.add_argument(
        "--emulation", action="store_true", default=None,
        help="""Emulates the devices. This allows testing all other features, like
                data logging, HTTP service, etc.""")
    parser.add_argument(
        "--developer", action="store_true", default=None,
        help="""Enables developer features, like the /eval HTTP request that evaluates
                Python expressions""")
    return parser.parse_args(argv)


def run(coro: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine in a new event loop. Ctrl+C ends it silently."""
    # aiomqtt (paho-mqtt) requires add_reader(), which the default Windows
    # event loop doesn't provide
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with contextlib.suppress(KeyboardInterrupt), \
            asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(coro)


def main(argv: list[str] | None = None) -> None:
    """Run the Airthings Bridge."""
    args = vars(parse_arguments(argv))
    try:
        config = load_config(args.pop("config"), args)
    except ConfigError as err:
        sys.exit(f"Error: {err}")

    configure_logging(config.log, verbose=config.port is None)
    try:
        run(Bridge(config).run())
    except (BridgeError, OSError) as err:
        logger.critical("%s", err)
        logger.debug("Stack trace:", exc_info=True)
        sys.exit(1)
