# Changelog

All notable changes are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2.0.0] - unreleased

The Wave Plus Bridge becomes the Airthings Bridge.

### Added

- Support of the Wave Gen 1, Wave Mini, Wave Radon, Wave Enhance and
  Corentium Home 2, with the new values radon_week, radon_month, radon_year,
  noise and lux.
- Commands `scan`, `read`, `test-mail` and `test-mqtt`, see
  [Debugging](docs/debugging.md).
- `/meta` HTTP request with the measurements and devices. The web UI shows a
  graph per logged measurement, and units in the table of the current values.
- Installation with pip, and the `airthings-bridge` command.
- Configuration check at the start, with errors naming the invalid key.
- MQTT reconnection after a lost broker connection.
- Graceful stop: pending mails are sent, the MQTT status is set to Offline.
- Documentation in [docs/](docs), tests, and continuous integration.

### Changed

- Python 3.11 or later is required.
- BLE access by bleak instead of bluepy; the bridge runs without root.
- systemd service instead of the init.d service, running as user
  airthings_bridge.
- Renamed paths: /opt/airthings_bridge, /var/lib/airthings_bridge (CSV file),
  /var/log/airthings_bridge (log file), airthings_bridge.yaml.
- Logger names: `airthings_bridge.*` instead of `__main__` and `libs.*`.
- New CSV file format (logdb of the phc project), with a lower memory use.
  CSV files of version 1 are converted at the first start, and kept as
  `.v1.bak`.
- New `graph_decimations` format: `{<data age in seconds>: <factor>}`.
- Invalid values are omitted instead of being reported as 'N/A'.
- The battery level follows the discharge curves of airthings-ble.
- Print alerts don't require an SMTP server.
- Dygraph 2.2.1 is served by the bridge instead of a CDN.
- Single asyncio event loop instead of threads (aiohttp, aiomqtt,
  aiosmtplib).
- The `/eval` HTTP request is only available in developer mode.
- The `/` HTTP request redirects to the web UI.

### Removed

- The module demo programs (`waveplus.py`, `threadedsendmail.py`,
  `threadedmqttpublisher.py`), replaced by the new commands.

### Fixed

- Wrong units of the CO2 and VOC graphs.
- Negative Wave Plus temperatures.
- Retries and retry delay of the configuration were not applied.
- The alert trigger requirement check was not applied.
- Mail sending blocked after a failed mail.
- Crashes with emulation and without CSV file.
- Hanging stop while the MQTT broker was unreachable.

## [1.x]

Wave Plus Bridge, see the Git history of the master branch.
