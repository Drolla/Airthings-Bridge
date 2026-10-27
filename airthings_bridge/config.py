"""Configuration from the command line and a YAML file.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import argparse
import logging
import os
import re
from collections.abc import Iterator
from typing import Any

import yaml

from airthings_bridge import __version__

logger = logging.getLogger(__name__)


class ReadConfiguration:
    """Airthings Bridge configuration.

    Command line arguments have precedence over the YAML file definitions.
    Raises ValueError for an invalid configuration.
    """

    def __init__(self):
        config = vars(self.parse_arguments())
        config["graph_decimations"] = None

        if config['config'] is not None:
            for key, value in \
                    self.read_yaml_config_file(config['config']).items():
                if key not in config or \
                        config[key] is None or \
                        (type(config[key]) is list and len(config[key]) == 0):
                    config[key] = value

        for key, value in {
                "period": 120,
                "retries": 3,
                "retry_delay": 1,
                "data_retention": 31*24*3600,  # 31 days
        }.items():
            if config.get(key) is None:
                config[key] = value

        # "2931234567, cellar" -> sn=2931234567, name=cellar
        sn_defs = config['sn']
        config['sn'] = []
        config['name'] = {}
        for sn_def in sn_defs if isinstance(sn_defs, list) else [sn_defs]:
            m = re.match(r'\s*(\w*)[\s,:;]*(.*)', str(sn_def))
            sn = m.group(1)
            config['sn'].append(sn)
            config['name'][sn] = m.group(2).strip() or sn

        if len(config['sn']) == 0:
            raise ValueError("No serial number provided")
        for sn in config['sn']:
            if len(sn) != 10 or not sn.isdigit():
                raise ValueError("Invalid SN format: " + sn)

        self.__dict__ = config

    def read_yaml_config_file(self, file: str) -> dict[str, Any]:
        """Read a YAML configuration file.

        Raises ValueError if the configuration file does not exist.
        """
        file = os.path.expanduser(file)
        if not os.path.exists(file):
            raise ValueError("Configuration file not existing: " + file)

        logger.info("Read configuration file '%s'", file)
        with open(file, encoding="utf-8") as yamlfile:
            return yaml.load(yamlfile, Loader=yaml.SafeLoader) or {}

    def parse_arguments(self) -> argparse.Namespace:
        """Parse the command line arguments."""
        parser = argparse.ArgumentParser(
                prog="airthings-bridge",
                description="Airthings BLE sensors to Wifi/LAN Bridge")
        parser.add_argument(
                "--version", action="version", version=__version__)
        parser.add_argument(
                "--period", type=int,
                help="Time in seconds between reading the sensor values")
        parser.add_argument(
                "--data_retention", type=int,
                help="Data retention time in seconds")
        parser.add_argument(
                "sn", metavar="sn", type=str, nargs="*",
                help="""10-digit serial number of a Wave Plus device (see under
                        the magnetic backplate. This number can be combined
                        with a device nickname, separated by a column from the
                        serial number ("2931234567, my_office")""")
        parser.add_argument(
                "--port", help="Port of the HTTP web server")
        parser.add_argument(
                "--csv", help="CSV file to store data")
        parser.add_argument(
                "--log", help="Log file. If not specified the stdout is used")
        parser.add_argument(
                "--config", help="YAML configuration file")
        parser.add_argument(
                "--emulation", action='store_true', default=None,
                help="""Emulates the connection with a WavePlus device. This
                        allows testing all other features, like data logging,
                        HTTP service, etc.""")
        parser.add_argument(
                "--developer", action='store_true', default=None,
                help="""Enables developer features, like the /eval HTTP
                        request that evaluates Python expressions""")

        return parser.parse_args()

    def __getitem__(self, key: str) -> Any:
        return self.__dict__[key]

    def __contains__(self, key: str) -> bool:
        return key in self.__dict__

    def __repr__(self) -> str:
        return repr(self.__dict__)

    def __iter__(self) -> Iterator[str]:
        yield from self.__dict__
