"""Sensor data log.

This file adapts the logging database (logdb module) to the Airthings Bridge:
It logs the sensor data of multiple devices, provides the logged data in CSV
format for the web graphs, and converts CSV files of the previous logging
database format (version 1, Wave Plus Bridge 1.x).

Copyright (C) 2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of
this file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import logging
import math
import re
import time
from pathlib import Path

from airthings_bridge.logdb import LogDb
from airthings_bridge.readings import Cycle

logger = logging.getLogger(__name__)

_NAN = float("nan")
_V1_INFO_LINE_PREFIX = "logdbcsv,"


class SensorLog:
    """Sensor data log, and consumer that logs the readings of each cycle.

    The labels of the logged data are composed by the device names and the
    sensor names, separated by ':' (e.g. "my_office:temperature").

    Args:
        file: CSV file
        label_specs: Dictionary of device names and their sensor name lists,
            e.g. {"my_office": ["temperature", "humidity"]}
        retention: Optional data retention time in seconds
    """

    def __init__(self, file: str | Path,
                 label_specs: dict[str, list[str]],
                 retention: float | None = None):
        file = Path(file)
        labels = [f"{device}:{sensor}"
                  for device, sensors in label_specs.items()
                  for sensor in sensors]
        if self._is_v1_file(file):
            self._convert_v1_file(file, labels)
        self._db = LogDb(file, labels, max_age=retention)
        self._label_set = set(self._db.labels)

    def close(self) -> None:
        """Close the CSV file."""
        self._db.close()

    def __len__(self) -> int:
        return len(self._db)

    async def start(self) -> None:
        """Nothing to start, the CSV file is opened by the constructor."""

    async def handle(self, cycle: Cycle) -> None:
        """Log the readings of a cycle."""
        self.log(int(cycle.timestamp), cycle.values())

    async def stop(self) -> None:
        """Close the CSV file."""
        self.close()

    @property
    def labels(self) -> list[str]:
        """List of all labels."""
        return self._db.labels

    def log(self, timestamp: float,
            data: dict[str, dict[str, float | str]]) -> None:
        """Log the sensor data of all devices.

        Only numeric values of known labels are logged, the other ones are
        logged as missing values.
        """
        values = {}
        for device, sensor_data in data.items():
            for sensor, value in sensor_data.items():
                label = f"{device}:{sensor}"
                if label in self._label_set and \
                        isinstance(value, int | float) and \
                        not isinstance(value, bool):
                    values[label] = value
        self._db.log(timestamp, values)

    def get_labels(self, label_patterns: str | list[str]) -> list[str]:
        """Get the labels that match one of the regular expression patterns.

        The labels are ordered by the patterns and then by the label order.
        Raises ValueError for an invalid regular expression.
        """
        if isinstance(label_patterns, str):
            label_patterns = [label_patterns]
        labels = []
        for pattern in label_patterns:
            try:
                regex = re.compile(pattern)
            except re.error as err:
                raise ValueError(
                        f"Invalid regular expression '{pattern}': {err}"
                ) from None
            for label in self._db.labels:
                if regex.fullmatch(label) and label not in labels:
                    labels.append(label)
        return labels

    def get_csv(self, label_patterns: str | list[str] = ".*",
                decimations: list[tuple[float, int]] | None = None) -> str:
        """Get the logged data in CSV format.

        Args:
            label_patterns: Regular expression(s) selecting the labels
            decimations: (data age in seconds, decimation factor) pairs, to
                reduce the resolution of older data

        The CSV data has a header line ("Time" followed by the labels),
        formats the time as "YYYY/MM/DD hh:mm" (local time), and leaves
        missing values empty.
        """
        labels = self.get_labels(label_patterns)
        rows = self._db.get_decimated(labels, decimations)
        csv_lines = [",".join(["Time", *labels])]
        for row in rows:
            csv_lines.append(",".join([
                    time.strftime("%Y/%m/%d %H:%M",
                                  time.localtime(row["time"])),
                    *(self._format_value(row[label]) for label in labels)]))
        return "\n".join(csv_lines)

    @staticmethod
    def _format_value(value: float) -> str:
        """Format a value with at most 2 decimals, or empty if missing."""
        if math.isnan(value):
            return ""
        return format(value, ".2f").rstrip("0").rstrip(".")

    @staticmethod
    def _is_v1_file(file: Path) -> bool:
        """Check if the file is a version 1 logging database CSV file."""
        if not file.is_file():
            return False
        with open(file, "rb") as f:
            return f.readline().startswith(_V1_INFO_LINE_PREFIX.encode())

    @staticmethod
    def _convert_v1_file(file: Path, labels: list[str]) -> None:
        """Convert a version 1 CSV file into the current format.

        The version 1 file is kept as backup (<file>.v1.bak).
        """
        backup = file.with_name(file.name + ".v1.bak")
        if backup.exists():
            backup = file.with_name(f"{file.name}.v1.{int(time.time())}.bak")
        new_file = file.with_name(file.name + ".tmp")
        new_file.unlink(missing_ok=True)
        logger.info("Convert the version 1 CSV file %s", file)

        with open(file, encoding="utf-8") as f:
            delta = "delta=1" in f.readline().strip().split(",")
            v1_labels = [label.strip() for label in f.readline().split(",")]
            db = LogDb(new_file, v1_labels[1:] + [
                    label for label in labels if label not in v1_labels],
                    max_records=1)
            values = [_NAN] * len(v1_labels)
            nbr_records = 0
            for line in f:
                cells = line.strip().split(",")
                if len(cells) < 2:
                    continue
                cells += [None] * (len(v1_labels) - len(cells))
                for index, cell in enumerate(cells[:len(v1_labels)]):
                    values[index] = SensorLog._parse_v1_cell(
                            cell, values[index], delta)
                if math.isnan(values[0]):
                    continue
                db.log(values[0], {
                        label: value
                        for label, value in zip(v1_labels[1:], values[1:],
                                                strict=True)
                        if not math.isnan(value)})
                nbr_records += 1
            db.close()

        file.rename(backup)
        new_file.rename(file)
        logger.info("  %d records converted, version 1 file backed up as %s",
                    nbr_records, backup)

    @staticmethod
    def _parse_v1_cell(cell: str | None, previous: float,
                       delta: bool) -> float:
        """Parse a version 1 CSV cell.

        A missing cell is NaN. An empty cell repeats the previous value in
        delta mode and is NaN otherwise. Invalid values (e.g. 'n') are NaN.
        """
        if cell is None:
            return _NAN
        cell = cell.strip()
        if cell == "":
            return previous if delta else _NAN
        try:
            return float(cell)
        except ValueError:
            return _NAN
