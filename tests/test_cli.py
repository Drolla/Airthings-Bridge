"""Tests for the command line interface."""

from unittest import mock

import aiomqtt
import pytest

from airthings_bridge import cli
from airthings_bridge.airthings import ScanResult
from airthings_bridge.errors import DeviceError

CONFIG = """
sn: 2930123456 office
smtp_server: {server: mail.home, user: bridge@home}
mqtt: {host: broker.home, topic: home, publish: {office: '*'}}
"""


@pytest.fixture
def config_file(tmp_path):
    file = tmp_path / "config.yaml"
    file.write_text(CONFIG, encoding="utf-8")
    return str(file)


@pytest.mark.parametrize("argv, command", [
    ([], "run"),
    (["2930123456"], "run"),
    (["--config", "x.yaml"], "run"),
    (["run", "--port", "80"], "run"),
    (["scan"], "scan"),
    (["read", "2930123456"], "read"),
])
def test_default_command_is_run(argv, command):
    assert cli.parse_arguments(argv).command == command


def test_run_options():
    args = cli.parse_arguments(["2930123456 office", "--port", "8080", "--emulation"])
    assert (args.sn, args.port, args.emulation, args.developer) == (
        ["2930123456 office"], 8080, True, None)


def test_run_with_invalid_configuration():
    with pytest.raises(SystemExit, match="Invalid serial number"):
        cli.main(["123"])


def test_scan(capsys):
    results = [ScanResult("2930123456", "AA", -50), ScanResult("2960123456", "BB", -70)]
    with mock.patch.object(cli, "scan", mock.AsyncMock(return_value=results)):
        cli.main(["scan", "--timeout", "1"])
    out = capsys.readouterr().out
    assert "2930123456  Wave Plus" in out
    assert "2960123456  (not supported)" in out
    assert "2 Airthings device(s) found" in out


def test_read(capsys):
    device = mock.Mock(serial="2930123456", PRODUCT_NAME="Wave Plus",
                       read=mock.AsyncMock(return_value={"co2": 600.0, "voc": 50.0}))
    with mock.patch.object(cli, "create_device", return_value=device):
        cli.main(["read", "2930123456"])
    assert "2930123456 (Wave Plus): co2=600.0, voc=50.0" in capsys.readouterr().out


def test_read_failure(capsys):
    device = mock.Mock(read=mock.AsyncMock(side_effect=DeviceError("No device")))
    with mock.patch.object(cli, "create_device", return_value=device), \
            pytest.raises(SystemExit) as exit_info:
        cli.main(["read", "2930123456"])
    assert exit_info.value.code == 1
    assert "No device" in capsys.readouterr().err


def test_read_invalid_serial():
    with pytest.raises(SystemExit, match="Invalid serial number"):
        cli.main(["read", "123"])


def test_test_mail(config_file, capsys):
    with mock.patch.object(cli.Mailer, "send", mock.AsyncMock()) as send:
        cli.main(["test-mail", "--config", config_file, "--to", "a@home"])
    assert send.call_args.args[0:2] == ("bridge@home", ["a@home"])
    assert "Mail sent to a@home" in capsys.readouterr().out


def test_test_mail_failure(config_file):
    with mock.patch.object(cli.Mailer, "send", mock.AsyncMock(side_effect=OSError("down"))), \
            pytest.raises(SystemExit):
        cli.main(["test-mail", "--config", config_file, "--to", "a@home"])


def test_test_mqtt(config_file, capsys):
    client = mock.AsyncMock()
    client.__aenter__.return_value = client
    with mock.patch.object(cli, "create_client", return_value=client):
        cli.main(["test-mqtt", "--config", config_file])
    assert client.publish.call_args.args[0] == "home/test"
    assert "published to home/test" in capsys.readouterr().out


def test_test_mqtt_failure(config_file, capsys):
    client = mock.AsyncMock()
    client.__aenter__.side_effect = aiomqtt.MqttError("refused")
    with mock.patch.object(cli, "create_client", return_value=client), \
            pytest.raises(SystemExit):
        cli.main(["test-mqtt", "--config", config_file])
    assert "refused" in capsys.readouterr().err
