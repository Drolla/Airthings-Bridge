# Debugging

The commands are shown with the following alias, which runs them as user
airthings_bridge. `-v` logs debug information.

```
alias airthings-bridge='sudo -u airthings_bridge /opt/airthings_bridge/.venv/bin/airthings-bridge'
```

## Device communication

Check that the devices are in range and that their serial numbers are
correct:

```
airthings-bridge scan
```

```
Scanning during 10 s ...
Serial      Model             Address                                 RSSI
2930031376  Wave Plus         A4:DA:32:B9:53:C2                       -71
2930089521  Wave Plus         A4:DA:32:B9:3F:B6                       -83
2 Airthings device(s) found
```

Read the devices once, or repeatedly with `--period`:

```
airthings-bridge read 2930031376 2930089521 --period 60
```

```
21:30:12 2930031376 (Wave Plus): humidity=59.0, radon_st=34, radon_lt=46, temperature=22.48, ...
21:30:15 2930089521 (Wave Plus): humidity=63.0, radon_st=59, radon_lt=45, temperature=21.57, ...
```

Without a stable communication, it doesn't make sense to run the bridge.
Frequent root causes are a disabled Bluetooth interface, a device out of
range, or a wrong serial number.

## Mail and MQTT

Send a test mail with the SMTP server of the configuration file:

```
airthings-bridge test-mail --config /opt/airthings_bridge/config.yaml --to me@home.com -v
```

Publish a test message to `<topic>/test` with the MQTT broker of the
configuration file (the message is not retained, and the bridge status is
not changed):

```
airthings-bridge test-mqtt --config /opt/airthings_bridge/config.yaml -v
```

A generic MQTT client (e.g. MQTT Explorer) shows the published messages.

## Minimal configuration

Run the bridge with only the serial numbers. Without HTTP port, the bridge
logs debug information to the terminal:

```
airthings-bridge 2930031376 2930089521
```

## Logging

The bridge logs to the log file (`log`), or to stdout. The log file is kept
across restarts and is not rotated. The loggers are named
after the modules, e.g.:

| Logger                                   | Default level |
|------------------------------------------|---------------|
| `airthings_bridge`                       | WARNING       |
| `airthings_bridge.bridge`                | INFO (DEBUG without HTTP port) |
| `airthings_bridge.consumers.alerts`      | INFO (print alerts) |
| `airthings_bridge.airthings.common`      | WARNING (INFO on the console, shows the device discovery) |
| `airthings_bridge.consumers.mqtt`        | MQTT connection |
| `airthings_bridge.mail`                  | Mail sending |
| `airthings_bridge.web.server`            | HTTP requests (CSV generation time) |

`log` can also be a Python logging configuration (`logging.config`
dictionary). This example corresponds to the default configuration with a
log file; change the levels as needed:

```
log:
    version: 1
    formatters:
      default:
        format: '%(asctime)s - %(name)13s[%(levelname)7s] - %(message)s'
        datefmt: '%Y-%m-%d %H:%M:%S'
    handlers:
      file:
        level: DEBUG
        formatter: default
        class: logging.FileHandler
        filename: /var/airthings_bridge/airthings_bridge.log
        encoding: utf8
        mode: a
    root:
      level: WARNING
      handlers: [file]
    loggers:
      airthings_bridge:
        level: WARNING
      airthings_bridge.bridge:
        level: INFO
      airthings_bridge.consumers.alerts:
        level: INFO
      airthings_bridge.airthings.common:
        level: DEBUG
```

## Emulation and developer mode

`--emulation` (or `emulation: True`) emulates the devices, which allows
testing the web UI, the logging, the alerts and MQTT without BLE. An empty
CSV file is pre-filled with emulated data.

`--developer` (or `developer: True`) enables the `/eval?<expression>` HTTP
request, which evaluates a Python expression, e.g.
`/eval?bridge.devices`. Never enable it on a network you don't trust.

## Development

```
pip install -e .[dev]
ruff check .
mypy
pytest
```
