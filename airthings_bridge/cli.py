"""Command line interface.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import argparse
import asyncio
import contextlib
import logging
import sys
import time
from collections.abc import Coroutine
from typing import Any

import aiomqtt
import aiosmtplib

from airthings_bridge import __version__
from airthings_bridge.airthings import AirthingsDevice, create_device, model_for_serial, scan
from airthings_bridge.bridge import Bridge
from airthings_bridge.config import Config, load_config
from airthings_bridge.consumers.mqtt import create_client
from airthings_bridge.errors import BridgeError, ConfigError, DeviceError
from airthings_bridge.logging_setup import configure_logging
from airthings_bridge.mail import Mailer

logger = logging.getLogger(__name__)

COMMANDS = ("run", "scan", "read", "test-mail", "test-mqtt")


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    """Parse the command line arguments. Without command, 'run' is used."""
    if not argv or argv[0] not in (*COMMANDS, "-h", "--help", "--version"):
        argv = ["run", *argv]

    parser = argparse.ArgumentParser(
        prog="airthings-bridge",
        description="Bridge from Airthings BLE sensors to HTTP, CSV logging, mail alerts and "
                    "MQTT. Without command, the bridge is run.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", metavar="command")

    run = commands.add_parser("run", help="Run the bridge (default)",
                              description="Run the bridge.")
    run.add_argument(
        "sn", type=str, nargs="*",
        help="""10-digit serial number of a device (see under the magnetic backplate).
                This number can be combined with a device nickname, separated by a
                comma from the serial number ("2930123456, my_office")""")
    run.add_argument("--config", help="YAML configuration file")
    run.add_argument(
        "--period", type=int, help="Time in seconds between reading the sensor values")
    run.add_argument("--port", type=int, help="Port of the HTTP web server")
    run.add_argument("--csv", help="CSV file to store data")
    run.add_argument("--data_retention", type=int, help="Data retention time in seconds")
    run.add_argument("--log", help="Log file. If not specified the stdout is used")
    run.add_argument(
        "--emulation", action="store_true", default=None,
        help="""Emulates the devices. This allows testing all other features, like
                data logging, HTTP service, etc.""")
    run.add_argument(
        "--developer", action="store_true", default=None,
        help="""Enables developer features, like the /eval HTTP request that evaluates
                Python expressions""")

    scan_cmd = commands.add_parser(
        "scan", help="List the Airthings devices in range",
        description="List the Airthings devices in range.")
    scan_cmd.add_argument("--timeout", type=float, default=10, help="Scan time in seconds")

    read = commands.add_parser(
        "read", help="Read devices and print their values",
        description="Read devices and print their values, once or repeatedly.")
    read.add_argument("serials", metavar="sn", nargs="+", help="10-digit serial number")
    read.add_argument("--period", type=float,
                      help="Time in seconds between reading the devices. Default: read once")
    read.add_argument("--retries", type=int, default=3, help="Extra attempts per reading")

    mail = commands.add_parser(
        "test-mail", help="Send a test mail with the configured SMTP server",
        description="Send a test mail with the SMTP server of the configuration.")
    mail.add_argument("--config", required=True, help="YAML configuration file")
    mail.add_argument("--to", required=True, nargs="+", help="Destination address(es)")
    mail.add_argument("--from", dest="from_", help="Author address. Default: SMTP user")

    mqtt = commands.add_parser(
        "test-mqtt", help="Publish a test message with the configured MQTT broker",
        description="Publish a non retained test message to <topic>/test with the MQTT "
                    "broker of the configuration.")
    mqtt.add_argument("--config", required=True, help="YAML configuration file")

    for command in (scan_cmd, read, mail, mqtt):
        command.add_argument("-v", "--verbose", action="store_true",
                             help="Log debug information")
    return parser.parse_args(argv)


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine in a new event loop and return its result."""
    # aiomqtt (paho-mqtt) requires add_reader(), which the default Windows
    # event loop doesn't provide
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        return runner.run(coro)


def main(argv: list[str] | None = None) -> None:
    """Run the command line interface."""
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    if args.command == "run":
        options = vars(args)
        del options["command"]
        file = options.pop("config")
        try:
            config = load_config(file, options)
        except ConfigError as err:
            sys.exit(f"Error: {err}")
        configure_logging(config.log, verbose=config.port is None)
        try:
            with contextlib.suppress(KeyboardInterrupt):
                run(Bridge(config).run())
        except (BridgeError, OSError) as err:
            logger.critical("%s", err)
            logger.debug("Stack trace:", exc_info=True)
            sys.exit(1)
        return

    configure_logging(None)
    if args.verbose:
        for name in ("airthings_bridge", "aiosmtplib", "mqtt"):
            logging.getLogger(name).setLevel(logging.DEBUG)
    try:
        with contextlib.suppress(KeyboardInterrupt):
            if args.command == "scan":
                ok = run(_scan(args.timeout))
            elif args.command == "read":
                ok = run(_read(args.serials, args.period, args.retries))
            elif args.command == "test-mail":
                ok = run(_test_mail(load_config(args.config), args.to, args.from_))
            else:
                ok = run(_test_mqtt(load_config(args.config)))
            if not ok:
                sys.exit(1)
    except BridgeError as err:
        sys.exit(f"Error: {err}")


async def _scan(timeout: float) -> bool:
    print(f"Scanning during {timeout:g} s ...")
    results = await scan(timeout)
    print(f"{'Serial':<12}{'Model':<18}{'Address':<40}RSSI")
    for result in results:
        model = model_for_serial(result.serial)
        product = model.PRODUCT_NAME if model else "(not supported)"
        print(f"{result.serial:<12}{product:<18}{result.address:<40}{result.rssi}")
    print(f"{len(results)} Airthings device(s) found")
    return True


async def _read(serials: list[str], period: float | None, retries: int) -> bool:
    devices: list[AirthingsDevice] = []
    for serial in serials:
        if len(serial) != 10 or not serial.isdigit():
            raise ConfigError(f"Invalid serial number '{serial}', 10 digits expected")
        devices.append(create_device(serial))
    while True:
        ok = True
        for device in devices:
            try:
                values = await device.read(retries)
            except DeviceError as err:
                print(err, file=sys.stderr)
                ok = False
                continue
            print(f"{time.strftime('%H:%M:%S')} {device.serial} ({device.PRODUCT_NAME}): "
                  + ", ".join(f"{key}={value}" for key, value in values.items()))
        if period is None:
            return ok
        await asyncio.sleep(period)


async def _test_mail(config: Config, to: list[str], from_: str | None) -> bool:
    if config.smtp is None:
        raise ConfigError("No SMTP server configured ('smtp_server')")
    from_ = from_ or config.smtp.user
    if not from_:
        raise ConfigError("No author address: Use the --from option")
    try:
        await Mailer(config.smtp).send(from_, to, "Airthings Bridge test",
                                       "This is a test mail of the Airthings Bridge.")
    except (aiosmtplib.SMTPException, OSError) as err:
        print(f"Failed to send the mail: {err}", file=sys.stderr)
        return False
    print(f"Mail sent to {', '.join(to)}")
    return True


async def _test_mqtt(config: Config) -> bool:
    if config.mqtt is None:
        raise ConfigError("No MQTT broker configured ('mqtt')")
    topic = "/".join(filter(bool, [config.mqtt.topic, "test"]))
    try:
        async with create_client(config.mqtt) as client:
            await client.publish(topic, f"Airthings Bridge test {time.ctime()}", qos=1,
                                 timeout=10)
    except aiomqtt.MqttError as err:
        print(f"Failed to publish to {config.mqtt.host}:{config.mqtt.port}: {err}",
              file=sys.stderr)
        return False
    print(f"Test message published to {topic} ({config.mqtt.host}:{config.mqtt.port})")
    return True
