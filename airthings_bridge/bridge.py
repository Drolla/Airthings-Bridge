"""Bridge: polls the devices and passes the readings to the consumers.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import asyncio
import contextlib
import dataclasses
import logging
import signal
import time
from typing import Any

from airthings_bridge.airthings import AirthingsDevice, create_device
from airthings_bridge.config import Config
from airthings_bridge.consumers import Consumer
from airthings_bridge.consumers.alerts import Alerts
from airthings_bridge.consumers.mqtt import MqttPublisher
from airthings_bridge.consumers.sensorlog import SensorLog
from airthings_bridge.emulation import EmulatedDevice
from airthings_bridge.errors import DeviceError
from airthings_bridge.measurements import MEASUREMENTS
from airthings_bridge.readings import Cycle, LiveState, Reading
from airthings_bridge.web.server import WebServer

logger = logging.getLogger(__name__)


class Bridge:
    """Airthings Bridge: devices, consumers and web server of a configuration."""

    def __init__(self, config: Config):
        self.config = config
        self.live = LiveState()
        self.sensor_log: SensorLog | None = None
        self.web_server: WebServer | None = None
        self._consumers: list[Consumer] = []
        self._stopping = asyncio.Event()

        self.devices: list[AirthingsDevice | EmulatedDevice] = []
        for device_config in config.devices:
            device = create_device(device_config.serial, device_config.name)
            if config.emulation:
                device = EmulatedDevice(type(device), device.serial, device.name)
            self.devices.append(device)

    @staticmethod
    def model(device: AirthingsDevice | EmulatedDevice) -> type[AirthingsDevice]:
        """Return the model (device class) of a device."""
        return device.model if isinstance(device, EmulatedDevice) else type(device)

    def meta(self) -> dict[str, Any]:
        """Return the measurements and the devices (/meta format).

        'logged' lists the keys logged into the CSV file, if there is one.
        """
        logging_enabled = self.sensor_log is not None
        return {
            "measurements": [dataclasses.asdict(m) for m in MEASUREMENTS],
            "devices": [{"name": d.name, "serial": d.serial,
                         "model": self.model(d).PRODUCT_NAME,
                         "values": list(self.model(d).value_keys()),
                         "logged": list(self.model(d).SENSOR_KEYS) if logging_enabled else []}
                        for d in self.devices],
        }

    def stop(self) -> None:
        """Request the bridge to stop."""
        self._stopping.set()

    async def run(self) -> None:
        """Run the bridge until stop() is called or SIGINT/SIGTERM is received.

        Raises BridgeError or OSError if a consumer or the web server can't be
        started.
        """
        self._handle_signals()
        poll = stopping = None
        try:
            await self._start()
            logger.info("Start polling the devices")
            poll = asyncio.create_task(self._poll())
            stopping = asyncio.create_task(self._stopping.wait())
            await asyncio.wait({poll, stopping}, return_when=asyncio.FIRST_COMPLETED)
            if poll.done():
                poll.result()  # Raise the exception that ended the polling
        finally:
            for task in (poll, stopping):
                if task is not None and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            await self._stop()
        logger.info("Airthings Bridge ended")

    def _handle_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Not supported on Windows, where Ctrl+C cancels the main task
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.stop)

    async def _start(self) -> None:
        config = self.config
        if config.file is not None:
            logger.info("Configuration file: %s", config.file)
        if config.emulation:
            logger.warning("Emulated devices")

        if config.csv is not None:
            logger.info("Open the CSV data log file '%s'", config.csv)
            start = time.perf_counter()
            self.sensor_log = SensorLog(
                config.csv, {d.name: list(self.model(d).SENSOR_KEYS) for d in self.devices},
                retention=config.data_retention)
            logger.info("  %d records read in %.1f s", len(self.sensor_log),
                        time.perf_counter() - start)
            self._consumers.append(self.sensor_log)
        if config.alerts:
            self._consumers.append(Alerts(config.alerts, config.smtp))
        if config.mqtt is not None:
            self._consumers.append(MqttPublisher(config.mqtt))

        started = []
        try:
            for consumer in self._consumers:
                await consumer.start()
                started.append(consumer)
        finally:
            self._consumers = started

        if config.port is not None:
            if config.developer:
                logger.warning("Developer mode is enabled: The /eval HTTP request "
                               "evaluates any provided Python expression!")
            self.web_server = WebServer(
                config.port, self.live, self.meta(), self.sensor_log,
                list(config.graph_decimations), config.developer, {"bridge": self})
            await self.web_server.start()
            logger.info("HTTP/Web server listening on port %s", self.web_server.port)

    async def _stop(self) -> None:
        if self.web_server is not None:
            await self.web_server.stop()
        for consumer in reversed(self._consumers):
            try:
                await consumer.stop()
            except Exception as err:
                logger.error("Failed to stop %s: %s", type(consumer).__name__, err)
        self._consumers = []

    async def _poll(self) -> None:
        config = self.config
        cycle_time = time.time()
        if config.emulation and self.sensor_log is not None and len(self.sensor_log) == 0:
            # Pre-fill the empty log by starting in the past (the logged data
            # has to be in chronological order)
            cycle_time -= config.data_retention
        while True:
            cycle = Cycle(cycle_time, tuple([await self._read(device)
                                             for device in self.devices]))
            self.live.update(cycle)
            for consumer in self._consumers:
                try:
                    await consumer.handle(cycle)
                except Exception as err:
                    logger.error("%s failed: %s", type(consumer).__name__, err)
                    logger.debug("Stack trace:", exc_info=True)
            cycle_time += config.period
            await asyncio.sleep(max(0.0, cycle_time - time.time()))

    async def _read(self, device: AirthingsDevice | EmulatedDevice) -> Reading:
        # Devices are read one after the other, BLE adapters handle a single
        # connection best
        logger.debug("Reading sensor data for device %s", device.name)
        try:
            values = await device.read(self.config.retries, self.config.retry_delay)
        except DeviceError as err:
            logger.error("%s", err)
            return Reading(device.name, {})
        logger.debug("  -> %s", values)
        return Reading(device.name, values, time.time())
