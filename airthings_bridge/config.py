"""Typed configuration, loaded from a YAML file and command line overrides.

Copyright (C) 2020-2026 Andreas Drollinger
See the file "LICENSE" for information on usage and redistribution of this
file, and for a DISCLAIMER OF ALL WARRANTIES.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from airthings_bridge.airthings import model_for_serial
from airthings_bridge.errors import ConfigError
from airthings_bridge.trigger import Trigger

DEFAULT_PERIOD = 120
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_DATA_RETENTION = 31 * 24 * 3600


@dataclass(frozen=True)
class DeviceConfig:
    """Device, defined by its serial number and its name."""

    serial: str
    name: str


@dataclass(frozen=True)
class SmtpConfig:
    """SMTP server used by the mail alerts."""

    server: str
    port: int = 587
    security: str | None = None  # "SSL", "TLS" or None
    user: str | None = None
    password: str | None = None


@dataclass(frozen=True)
class MailActionConfig:
    """Mail alert. The message placeholders are %v (value), %d (device) and %s (sensor)."""

    from_: str
    to: tuple[str, ...]
    subject: str = "Sensor alert"
    message: str = "Sensor: %d.%s, Level: %v"


@dataclass(frozen=True)
class PrintActionConfig:
    """Alert logged as message, with the placeholders of MailActionConfig."""

    message: str = "Sensor alert: Sensor: %d.%s, Level: %v"


@dataclass(frozen=True)
class AlertConfig:
    """Alert: sources as (device, sensor), trigger conditions and actions."""

    sources: tuple[tuple[str, str], ...]
    trigger: dict[str, Any]
    actions: tuple[MailActionConfig | PrintActionConfig, ...]


@dataclass(frozen=True)
class MqttConfig:
    """MQTT broker and the published data ({device: sensors}, '*' selects all)."""

    host: str
    publish: dict[str, list[str] | str]
    port: int = 1883
    client_id: str | None = None
    auth: dict[str, str] | None = None
    tls: dict[str, Any] | None = None
    will: dict[str, Any] | None = None
    topic: str = ""


@dataclass(frozen=True)
class Config:
    """Airthings Bridge configuration."""

    devices: tuple[DeviceConfig, ...]
    period: float = DEFAULT_PERIOD
    retries: int = DEFAULT_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    port: int | None = None
    csv: Path | None = None
    data_retention: float = DEFAULT_DATA_RETENTION
    graph_decimations: tuple[tuple[float, int], ...] = ()
    log: str | dict[str, Any] | None = None  # Log file or logging.config dictionary
    smtp: SmtpConfig | None = None
    alerts: tuple[AlertConfig, ...] = ()
    mqtt: MqttConfig | None = None
    emulation: bool = False
    developer: bool = False
    file: Path | None = field(default=None, compare=False)


_KEYS = {"sn", "period", "retries", "retry_delay", "port", "csv", "data_retention",
         "graph_decimations", "log", "smtp_server", "alerts", "mqtt", "emulation", "developer"}


def load_config(file: str | Path | None = None,
                overrides: dict[str, Any] | None = None) -> Config:
    """Load the YAML file and apply the overrides (command line arguments).

    Overrides that are None or empty lists are ignored. Raises ConfigError.
    """
    data: dict[str, Any] = {}
    if file is not None:
        file = Path(file).expanduser()
        try:
            with open(file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except OSError as err:
            raise ConfigError(f"Unable to read the configuration file: {err}") from None
        except yaml.YAMLError as err:
            raise ConfigError(f"Invalid YAML configuration file {file}: {err}") from None
        if not isinstance(data, dict):
            raise ConfigError(f"Invalid configuration file {file}: mapping expected")
    for key, value in (overrides or {}).items():
        if value is not None and value != []:
            data[key] = value
    return build_config(data, file)


def build_config(data: dict[str, Any], file: Path | None = None) -> Config:
    """Validate the configuration data and build the Config. Raises ConfigError."""
    unknown = sorted(set(data) - _KEYS)
    if unknown:
        raise ConfigError(f"Unknown configuration key(s): {', '.join(unknown)}")

    devices = _devices(data.get("sn"))
    smtp = _smtp(data["smtp_server"]) if data.get("smtp_server") is not None else None
    alerts = _alerts(data.get("alerts"), {d.name for d in devices}, smtp)
    decimations = _decimations(data.get("graph_decimations"))
    log = data.get("log")
    if log is not None and not isinstance(log, str | dict):
        raise ConfigError("log: file name or logging configuration dictionary expected")

    return Config(
        devices=devices,
        period=_number(data, "period", DEFAULT_PERIOD, minimum=1),
        retries=int(_number(data, "retries", DEFAULT_RETRIES, minimum=0, integer=True)),
        retry_delay=_number(data, "retry_delay", DEFAULT_RETRY_DELAY, minimum=0),
        port=_port(data.get("port"), "port"),
        csv=Path(data["csv"]).expanduser() if data.get("csv") else None,
        data_retention=_number(data, "data_retention", DEFAULT_DATA_RETENTION, minimum=1),
        graph_decimations=decimations,
        log=log,
        smtp=smtp,
        alerts=alerts,
        mqtt=_mqtt(data["mqtt"], {d.name for d in devices}) if data.get("mqtt") else None,
        emulation=bool(data.get("emulation", False)),
        developer=bool(data.get("developer", False)),
        file=file,
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _number(data: dict[str, Any], key: str, default: float, minimum: float,
            integer: bool = False) -> float:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            raise ConfigError(f"{key}: number expected, got '{value}'") from None
    if isinstance(value, bool) or not isinstance(value, int | float) or value < minimum or \
            (integer and value != int(value)):
        raise ConfigError(f"{key}: {'integer' if integer else 'number'} >= {minimum} "
                          f"expected, got '{value}'")
    return value


def _decimations(definitions: Any) -> tuple[tuple[float, int], ...]:
    """Parse the graph decimations {data age in seconds: decimation factor}."""
    if not definitions:
        return ()
    if not isinstance(definitions, dict):
        raise ConfigError("graph_decimations: mapping expected")
    decimations = []
    for age, factor in definitions.items():
        if isinstance(age, bool) or not isinstance(age, int | float) or age <= 0 or \
                isinstance(factor, bool) or not isinstance(factor, int) or factor < 1:
            raise ConfigError(
                f"graph_decimations: Invalid definition '{age}: {factor}'. Use "
                "'<data age in seconds>: <decimation factor>', e.g. '691200: 8' (format "
                "changed with version 2.0.0)")
        decimations.append((float(age), factor))
    return tuple(decimations)


def _port(value: Any, key: str) -> int | None:
    if value is None:
        return None
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = -1
    if not 0 <= port <= 65535 or isinstance(value, bool):
        raise ConfigError(f"{key}: port number expected, got '{value}'")
    return port


def _devices(sn_defs: Any) -> tuple[DeviceConfig, ...]:
    """Parse the device definitions, e.g. "2930123456, cellar"."""
    if not sn_defs:
        raise ConfigError("sn: No serial number provided")
    devices = []
    for sn_def in _as_list(sn_defs):
        m = re.fullmatch(r"\s*(\w*)[\s,:;]*(.*?)\s*", str(sn_def))
        serial = m.group(1) if m else ""
        if len(serial) != 10 or not serial.isdigit():
            raise ConfigError(f"sn: Invalid serial number '{sn_def}', 10 digits expected")
        if model_for_serial(serial) is None:
            raise ConfigError(f"sn: Unsupported device {serial}, see the supported devices")
        devices.append(DeviceConfig(serial, m.group(2) or serial))
    names = [d.name for d in devices]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ConfigError(f"sn: Duplicate device name(s): {', '.join(duplicates)}")
    return tuple(devices)


def _smtp(cfg: Any) -> SmtpConfig:
    if not isinstance(cfg, dict) or not cfg.get("server"):
        raise ConfigError("smtp_server: 'server' is required")
    security = cfg.get("security")
    if security is not None:
        security = str(security).upper()
        if security not in ("SSL", "TLS"):
            raise ConfigError(f"smtp_server.security: 'SSL' or 'TLS' expected, got '{security}'")
    return SmtpConfig(
        server=str(cfg["server"]),
        port=_port(cfg.get("port", 587), "smtp_server.port") or 587,
        security=security,
        user=cfg.get("user"),
        password=cfg.get("password"))


def _alerts(alerts_cfg: Any, device_names: set[str],
            smtp: SmtpConfig | None) -> tuple[AlertConfig, ...]:
    if not alerts_cfg:
        return ()
    alerts = []
    for index, alert in enumerate(_as_list(alerts_cfg)):
        key = f"alerts[{index}]"
        if not isinstance(alert, dict):
            raise ConfigError(f"{key}: mapping expected")
        for required in ("sources", "trigger", "actions"):
            if required not in alert:
                raise ConfigError(f"{key}: '{required}' is required")

        sources = []
        for source in _as_list(alert["sources"]):
            device, _, sensor = str(source).partition(":")
            if not sensor:
                raise ConfigError(f"{key}.sources: Invalid source '{source}', "
                                  "'<device>:<sensor>' expected")
            if device not in device_names:
                raise ConfigError(f"{key}.sources: Unknown device '{device}'")
            sources.append((device, sensor))

        if not isinstance(alert["trigger"], dict):
            raise ConfigError(f"{key}.trigger: mapping expected")
        try:
            Trigger(alert["trigger"], [])
        except ValueError as err:
            raise ConfigError(f"{key}.trigger: {err}") from None

        actions: list[MailActionConfig | PrintActionConfig] = []
        for action in _as_list(alert["actions"]):
            if not isinstance(action, dict) or not {"mail", "print"} & set(action):
                raise ConfigError(f"{key}.actions: 'mail' or 'print' action expected")
            if "mail" in action:
                actions.append(_mail_action(action["mail"], f"{key}.actions.mail"))
                if smtp is None:
                    raise ConfigError(f"{key}: Mail alerts require the 'smtp_server' "
                                      "configuration")
            if "print" in action:
                actions.append(PrintActionConfig(**_strings(
                    action["print"] or {}, f"{key}.actions.print", ("message",))))
        alerts.append(AlertConfig(tuple(sources), dict(alert["trigger"]), tuple(actions)))
    return tuple(alerts)


def _mail_action(cfg: Any, key: str) -> MailActionConfig:
    if not isinstance(cfg, dict) or not cfg.get("from") or not cfg.get("to"):
        raise ConfigError(f"{key}: 'from' and 'to' are required")
    options = _strings(cfg, key, ("subject", "message"))
    return MailActionConfig(from_=str(cfg["from"]),
                            to=tuple(str(to) for to in _as_list(cfg["to"])), **options)


def _strings(cfg: Any, key: str, allowed: tuple[str, ...]) -> dict[str, str]:
    if not isinstance(cfg, dict):
        raise ConfigError(f"{key}: mapping expected")
    return {name: str(cfg[name]) for name in allowed if cfg.get(name) is not None}


def _mqtt(cfg: Any, device_names: set[str]) -> MqttConfig:
    if not isinstance(cfg, dict) or not cfg.get("host"):
        raise ConfigError("mqtt: 'host' is required")
    publish = cfg.get("publish")
    if not isinstance(publish, dict) or not publish:
        raise ConfigError("mqtt.publish: mapping of devices and sensors expected")
    for device in publish:
        if device != "*" and device not in device_names:
            raise ConfigError(f"mqtt.publish: Unknown device '{device}'")
    for option in ("auth", "tls", "will"):
        if cfg.get(option) is not None and not isinstance(cfg[option], dict):
            raise ConfigError(f"mqtt.{option}: mapping expected")
    if cfg.get("auth") is not None and not cfg["auth"].get("username"):
        raise ConfigError("mqtt.auth: 'username' is required")
    return MqttConfig(
        host=str(cfg["host"]),
        publish=dict(publish),
        port=_port(cfg.get("port", 1883), "mqtt.port") or 1883,
        client_id=cfg.get("client_id"),
        auth=cfg.get("auth"),
        tls=cfg.get("tls"),
        will=cfg.get("will"),
        topic=str(cfg.get("topic") or ""))
