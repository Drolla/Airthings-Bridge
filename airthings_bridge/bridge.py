"""Bridge main loop: reads the devices and passes the data to the consumers.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import sys
import time

from airthings_bridge import emulation
from airthings_bridge.airthings import wave_plus
from airthings_bridge.config import ReadConfiguration
from airthings_bridge.consumers import sensorlog
from airthings_bridge.consumers.alerts import Actions
from airthings_bridge.consumers.mqtt import MqttPublisher
from airthings_bridge.performancecheck import PerformanceCheck
from airthings_bridge.readings import SensorData
from airthings_bridge.web.server import create_http_request_handler
from airthings_bridge.web.threadedhttpserver import ThreadedHTTPServer

logger = logging.getLogger(__name__)


def run(config: ReadConfiguration) -> None:
    """Run the bridge until an interrupt or termination request."""
    if config.developer:
        logger.warning("Developer mode is enabled: The /eval HTTP request "
                       "evaluates any provided Python expression!")

    logger.debug("Available logger:")
    for logger_name in logging.root.manager.loggerDict:
        logger.debug("   %s", logging.getLogger(logger_name))

    # Most recent data of all devices, including the update times
    all_sensor_data_ts: SensorData = {}

    ldb = None
    if config.csv is not None:
        logger.info("Opening CSV data log file '%s'", config.csv)
        log_labels = ["humidity", "radon_st", "radon_lt",
                      "temperature", "pressure", "co2", "voc"]
        try:
            with PerformanceCheck("LogDB/CSV file loading"):
                ldb = sensorlog.SensorLog(
                        config.csv,
                        {config.name[sn]: log_labels for sn in config.sn},
                        retention=config.data_retention)
            logger.info("  %d records read", len(ldb))
        except PermissionError:
            logger.error("  No permission to open file %s!", config.csv)
        except Exception as err:
            logger.critical("  Error accessing file %s : %s", config.csv, err)
            sys.exit(1)

    if config.port is not None:
        logger.info("Start HTTP/Web server on port %s", config.port)
        try:
            graph_decimations = sensorlog.parse_decimations(
                    config.graph_decimations)
        except ValueError as err:
            logger.critical("  %s", err)
            sys.exit(1)
        try:
            handler_class = create_http_request_handler(
                    all_sensor_data_ts, ldb, graph_decimations,
                    bool(config.developer))
            ThreadedHTTPServer(("", int(config.port)), handler_class)
            logger.info("  Done")
        except Exception:
            logger.critical("  Unable to open HTTP port %s!", config.port)
            logger.debug("    Stack trace:", exc_info=True)
            sys.exit(1)

    actions = None
    if "alerts" in config:
        logger.info("Setup email alerts")
        if "smtp_server" not in config:
            logger.critical("  No SMTP server is configured!")
            sys.exit(1)
        try:
            actions = Actions(config.smtp_server, config.alerts)
            logger.info("  Done")
        except Exception as err:
            logger.critical("  Unable to setup the alerts: %s", err)
            logger.debug("    Stack trace:", exc_info=True)
            sys.exit(1)

    mqtt_publisher = None
    if "mqtt" in config:
        logger.info("Setup MQTT publishing")
        try:
            mqtt_publisher = MqttPublisher(config.mqtt)
            logger.info("  Done")
        except Exception as err:
            logger.critical("  Unable to setup MQTT publishing: %s", err)
            logger.debug("    Stack trace:", exc_info=True)
            sys.exit(1)

    logger.info("Setup WavePlus device access")
    wp_module = wave_plus
    if config.emulation:
        wp_module = emulation
        logger.warning("Use WavePlus emulation module")
    wp_devices = [wp_module.WavePlus(sn, config.name[sn]) for sn in config.sn]
    logger.info("  Done")

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
            for wp_device in wp_devices:
                logger.debug(
                        "Reading sensor data for device %s", wp_device.name)
                sdata_ts = sdata_no_ts = {}
                try:
                    sdata_no_ts = wp_device.get(
                            retries=config.retries,
                            retry_delay=config.retry_delay)
                    logger.debug("  -> %s", sdata_no_ts)
                    sdata_ts = sdata_no_ts.copy()
                    sdata_ts["update_time"] = int(time.time())
                except Exception as err:
                    logger.error("Failed to communicate with device %s: %s",
                                 wp_device.name, err)
                sensor_data_no_ts[wp_device.name] = sdata_no_ts
                sensor_data_ts[wp_device.name] = sdata_ts
                all_sensor_data_ts[wp_device.name] = sdata_ts

            if ldb is not None:
                try:
                    ldb.log(int(iteration_start_time), sensor_data_no_ts)
                except Exception as err:
                    logger.error("Failed to log the data: %s", err)
                    logger.debug("  Stack trace:", exc_info=True)

            if actions is not None:
                try:
                    actions.check_levels(sensor_data_no_ts)
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
        except Exception as err:
            logger.error("Error: %s", err)
            logger.debug("  Stack trace:", exc_info=True)

    for wp_device in wp_devices:
        wp_device.stop()
    if mqtt_publisher is not None:
        mqtt_publisher.stop()
    if ldb is not None:
        ldb.close()

    logger.info("Airthings Bridge ended")
