"""Bridge main loop: reads the devices and passes the data to the consumers.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import time

from airthings_bridge import emulation
from airthings_bridge.airthings import wave_plus
from airthings_bridge.config import Config
from airthings_bridge.consumers.alerts import Alerts
from airthings_bridge.consumers.mqtt import MqttPublisher
from airthings_bridge.consumers.sensorlog import SensorLog
from airthings_bridge.errors import DeviceError
from airthings_bridge.performancecheck import PerformanceCheck
from airthings_bridge.readings import SensorData
from airthings_bridge.web.server import create_http_request_handler
from airthings_bridge.web.threadedhttpserver import ThreadedHTTPServer

logger = logging.getLogger(__name__)

LOG_LABELS = ["humidity", "radon_st", "radon_lt", "temperature", "pressure", "co2", "voc"]


def run(config: Config) -> None:
    """Run the bridge until an interrupt or termination request.

    Raises BridgeError or OSError if a consumer or the HTTP server can't be
    started.
    """
    if config.file is not None:
        logger.info("Configuration file: %s", config.file)
    if config.developer:
        logger.warning("Developer mode is enabled: The /eval HTTP request "
                       "evaluates any provided Python expression!")

    # Most recent data of all devices, including the update times
    all_sensor_data_ts: SensorData = {}

    ldb = None
    if config.csv is not None:
        logger.info("Opening CSV data log file '%s'", config.csv)
        with PerformanceCheck("LogDB/CSV file loading"):
            ldb = SensorLog(config.csv, {d.name: LOG_LABELS for d in config.devices},
                            retention=config.data_retention)
        logger.info("  %d records read", len(ldb))

    if config.port is not None:
        logger.info("Start HTTP/Web server on port %s", config.port)
        handler_class = create_http_request_handler(
            all_sensor_data_ts, ldb, list(config.graph_decimations), config.developer)
        ThreadedHTTPServer(("", config.port), handler_class)

    alerts = None
    if config.alerts:
        logger.info("Setup alerts")
        alerts = Alerts(config.alerts, config.smtp)

    mqtt_publisher = None
    if config.mqtt is not None:
        logger.info("Setup MQTT publishing")
        mqtt_publisher = MqttPublisher(config.mqtt)

    device_module = emulation if config.emulation else wave_plus
    if config.emulation:
        logger.warning("Use WavePlus emulation module")
    devices = [device_module.WavePlus(d.serial, d.name) for d in config.devices]

    logger.info("Start main loop. Press ctrl+C to exit program!")
    iteration_start_time = time.time()
    if config.emulation and ldb is not None and len(ldb) == 0:
        # Pre-fill the empty log by starting in the past (the logged data
        # has to be in chronological order)
        iteration_start_time -= config.data_retention
    while True:
        # Data of the devices read in this iteration, with and without the
        # update times
        sensor_data_no_ts: SensorData = {}
        sensor_data_ts: SensorData = {}

        try:
            for device in devices:
                logger.debug("Reading sensor data for device %s", device.name)
                sdata_ts = sdata_no_ts = {}
                try:
                    sdata_no_ts = device.get(
                        retries=config.retries, retry_delay=config.retry_delay)
                    logger.debug("  -> %s", sdata_no_ts)
                    sdata_ts = sdata_no_ts.copy()
                    sdata_ts["update_time"] = int(time.time())
                except DeviceError as err:
                    logger.error("%s", err)
                sensor_data_no_ts[device.name] = sdata_no_ts
                sensor_data_ts[device.name] = sdata_ts
                all_sensor_data_ts[device.name] = sdata_ts

            if ldb is not None:
                try:
                    ldb.log(int(iteration_start_time), sensor_data_no_ts)
                except Exception as err:
                    logger.error("Failed to log the data: %s", err)
                    logger.debug("  Stack trace:", exc_info=True)

            if alerts is not None:
                try:
                    alerts.check_levels(sensor_data_no_ts)
                except UserWarning as err:
                    logger.warning("Failed to trigger alerts: %s", err)
                except Exception as err:
                    logger.error("Failed to trigger alerts: %s", err)
                    logger.debug("  Stack trace:", exc_info=True)

            if mqtt_publisher is not None:
                try:
                    mqtt_publisher.publish(sensor_data_ts)
                except Exception as err:
                    logger.error("Failed to publish to MQTT broker: %s", err)
                    logger.debug("  Stack trace:", exc_info=True)

            iteration_start_time += config.period
            time.sleep(max(0, iteration_start_time - time.time()))
        except (KeyboardInterrupt, SystemExit):
            logger.warning("Interrupt/termination request detected")
            break

    if mqtt_publisher is not None:
        mqtt_publisher.stop()
    if ldb is not None:
        ldb.close()

    logger.info("Airthings Bridge ended")
