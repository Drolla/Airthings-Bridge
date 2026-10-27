"""Command line entry point.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging.config
import signal
import sys
from types import FrameType

from airthings_bridge import bridge
from airthings_bridge.config import ReadConfiguration


def configure_logging(config: ReadConfiguration) -> None:
    """Apply the YAML logging configuration, or the default one.

    The default configuration logs into the log file if one is defined, and
    to stdout otherwise. Without HTTP server, the bridge logs debug messages.
    """
    if isinstance(config.log, dict):
        logging.config.dictConfig(config.log)
        return
    log_level = "DEBUG" if config.port is None else "INFO"
    logging_config = {
        'version': 1,
        'formatters': {'default': {
            'format':
                '%(asctime)s - %(name)13s[%(levelname)7s] - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'}},
        'loggers': {
            'airthings_bridge': {'level': 'WARNING'},
            'airthings_bridge.bridge': {'level': log_level}}
    }
    if isinstance(config.log, str) and config.log != "":
        logging_config.update({
            'root': {'level': 'WARNING', 'handlers': ['file']},
            'handlers': {'file': {
                'level': 'DEBUG', 'formatter': 'default',
                'class': 'logging.FileHandler', 'filename': config.log,
                'encoding': 'utf8', 'mode': 'w'}}
        })
    else:
        logging_config.update({
            'root': {'level': 'WARNING', 'handlers': ['console']},
            'handlers': {'console': {
                'level': 'DEBUG', 'formatter': 'default',
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout'}}
        })
    logging.config.dictConfig(logging_config)


def main() -> None:
    """Run the Airthings Bridge."""
    def handle_exit(sig: int, frame: FrameType | None) -> None:
        raise SystemExit()

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        config = ReadConfiguration()
    except ValueError as err:
        print("Error:", err)
        sys.exit(1)

    configure_logging(config)
    bridge.run(config)
