"""Tests for libs.sensorlog: the Wave Plus Bridge adapter of logdb."""

import fnmatch
import threading
import time

import pytest

from libs.sensorlog import SensorLog, parse_decimations

LABEL_SPECS = {"office": ["temperature", "humidity"],
               "living": ["temperature", "radon_st"]}


def _time_str(timestamp: float) -> str:
    return time.strftime("%Y/%m/%d %H:%M", time.localtime(timestamp))


@pytest.fixture
def sensor_log(tmp_path):
    log = SensorLog(tmp_path / "log.csv", LABEL_SPECS)
    yield log
    log.close()


# ---------- logging ----------

def test_labels_are_composed_from_device_and_sensor(sensor_log):
    assert sensor_log.labels == ["office:temperature", "office:humidity",
                                 "living:temperature", "living:radon_st"]


def test_log_keeps_only_numeric_values_of_known_labels(sensor_log):
    sensor_log.log(1000, {
        "office": {"temperature": 21.5, "humidity": 45, "battery": 80},
        "living": {"temperature": True, "radon_st": "N/A"},
        "cellar": {"temperature": 12.0}})
    assert len(sensor_log) == 1
    assert sensor_log.get_csv().splitlines() == [
        "Time,office:temperature,office:humidity,living:temperature,"
        "living:radon_st",
        f"{_time_str(1000)},21.5,45,,"]


def test_missing_device_data_is_logged_as_missing(sensor_log):
    sensor_log.log(1000, {"office": {}, "living": {"radon_st": 33}})
    assert sensor_log.get_csv().splitlines()[1] == f"{_time_str(1000)},,,,33"


def test_retention_limits_the_records(tmp_path):
    log = SensorLog(tmp_path / "log.csv", LABEL_SPECS, retention=100)
    for t in range(0, 1000, 10):
        log.log(t, {"office": {"temperature": t}})
    assert len(log) <= 11 * 1.1
    log.close()


def test_restore_after_reopen(tmp_path):
    log = SensorLog(tmp_path / "log.csv", LABEL_SPECS)
    log.log(1000, {"office": {"temperature": 21.5}})
    log.log(1060, {"office": {"temperature": 22.5}})
    log.close()
    log = SensorLog(tmp_path / "log.csv", LABEL_SPECS)
    assert len(log) == 2
    assert log.get_csv("office:temperature").splitlines()[1:] == [
        f"{_time_str(1000)},21.5", f"{_time_str(1060)},22.5"]
    log.close()


# ---------- CSV output ----------

def test_csv_values_have_at_most_2_decimals(sensor_log):
    sensor_log.log(1000, {"office": {"temperature": 21.256,
                                     "humidity": 40.0}})
    assert sensor_log.get_csv("office:.*").splitlines()[1] == \
        f"{_time_str(1000)},21.26,40"


def test_csv_label_selection_by_regular_expression(sensor_log):
    assert sensor_log.get_labels(".*:temperature") == [
        "office:temperature", "living:temperature"]


def test_csv_label_selection_by_patterns_keeps_order_without_duplicates(
        sensor_log):
    patterns = [fnmatch.translate(p) for p in ("living:*", "*:temp*")]
    assert sensor_log.get_labels(patterns) == [
        "living:temperature", "living:radon_st", "office:temperature"]


def test_csv_invalid_regular_expression_raises_value_error(sensor_log):
    with pytest.raises(ValueError):
        sensor_log.get_csv("office:(")


def test_csv_decimation_averages_older_data(sensor_log):
    now = time.time()
    for i in range(10):
        sensor_log.log(now - 1000 + i * 100, {"office": {"temperature": i}})
    lines = sensor_log.get_csv("office:temperature",
                               [(450.0, 2)]).splitlines()
    # Samples older than 450s (i=0..5) are averaged by pairs
    assert [line.split(",")[1] for line in lines[1:]] == \
        ["0.5", "2.5", "4.5", "6", "7", "8", "9"]


# ---------- decimation definitions ----------

def test_parse_decimations():
    assert parse_decimations(None) == []
    assert parse_decimations({691200: 8, 90000: 3}) == [
        (691200.0, 8), (90000.0, 3)]


@pytest.mark.parametrize("definitions", [
    {-1.0: 8, -5760: 3, -750: 1},  # Format of version 1.x
    {3600: 0},
    {3600: 2.5},
    {"1h": 2},
])
def test_parse_decimations_rejects_invalid_definitions(definitions):
    with pytest.raises(ValueError, match="2.0.0"):
        parse_decimations(definitions)


# ---------- thread safety ----------

def test_concurrent_csv_reads_while_logging_and_trimming(tmp_path):
    log = SensorLog(tmp_path / "log.csv", LABEL_SPECS, retention=50)
    errors = []

    def read():
        try:
            for _ in range(200):
                log.get_csv(".*", [(20.0, 3)])
        except Exception as err:
            errors.append(err)

    reader = threading.Thread(target=read)
    reader.start()
    for t in range(5000):
        log.log(t, {"office": {"temperature": t % 30}})
    reader.join()
    log.close()
    assert errors == []


# ---------- version 1 file conversion ----------

V1_CSV = (
    "logdbcsv,version=1.0,delta=0\n"
    "Time,sens0,sens1,sens2" + " " * 40 + "\n"
    "1590994497,9.8,9.0,6.5\n"
    "1590994498,,1.4,\n"
    "1590994498, ,1.4, \r\n"
    "1590994499,3.1,1.3,3.6\n"
    "1590994500,7.6,3.5,6.0\n"
    "1590994501,5.7,1.8,5.1\n")

V1_CSV_DELTA = (
    "logdbcsv,version=1.0,delta=1\n"
    "Time,sens0,sens1,sens2" + " " * 40 + "\n"
    "1590994497,9.8,9.0,6.5\n"
    "1590994498,,1.4,\n"
    "1590994498, ,1.4, \r\n"
    "1590994498,n,1.4, n \r\n"
    "1590994499,3.1,1.3,3.6\n"
    "1590994500,7.6,3.5,6.0\n"
    "1590994501,5.7,1.8\n")


@pytest.mark.parametrize("content, expected", [
    (V1_CSV, [
        (1590994497, "9.8,9,6.5"),
        (1590994498, ",1.4,"),
        (1590994498, ",1.4,"),
        (1590994499, "3.1,1.3,3.6"),
        (1590994500, "7.6,3.5,6"),
        (1590994501, "5.7,1.8,5.1")]),
    (V1_CSV_DELTA, [
        (1590994497, "9.8,9,6.5"),
        (1590994498, "9.8,1.4,6.5"),
        (1590994498, "9.8,1.4,6.5"),
        (1590994498, ",1.4,"),
        (1590994499, "3.1,1.3,3.6"),
        (1590994500, "7.6,3.5,6"),
        (1590994501, "5.7,1.8,")]),
], ids=["delta0", "delta1"])
def test_v1_file_is_converted(tmp_path, content, expected):
    file = tmp_path / "log.csv"
    file.write_bytes(content.encode())
    log = SensorLog(file, {"office": ["temperature"]})
    assert log.labels == ["sens0", "sens1", "sens2", "office:temperature"]
    assert log.get_csv("sens.").splitlines() == ["Time,sens0,sens1,sens2"] + [
        f"{_time_str(t)},{values}" for t, values in expected]
    log.close()

    assert (tmp_path / "log.csv.v1.bak").read_bytes() == content.encode()
    assert file.read_text().startswith("phc-logdb,")
    assert not (tmp_path / "log.csv.tmp").exists()

    # The converted file is restored as usual
    log = SensorLog(file, {"office": ["temperature"]})
    assert len(log) == len(expected)
    log.close()
