# Airthings Bridge to Wifi/LAN and MQTT

[![Airthings](https://img.shields.io/badge/devices-Airthings-0072CE)](docs/devices.md)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

The Airthings Bridge is the successor of the
[Wave Plus Bridge](https://github.com/Drolla/WavePlus_Bridge) (version 1.x),
forked from it for version 2.0.

> 🟡 **Draft:** this project has not been verified yet on real devices. This
> will happen in November 2026.

The Airthings Bridge connects one or multiple
**Airthings** sensors to the **Wifi/LAN** network, using a **Raspberry Pi**
with Bluetooth Low Energy (BLE):

* Reading of the sensors in a configurable interval
* Web page with the current values and graphs, and a JSON API
* Logging of the sensor data in a CSV file
* Mail alerts with flexible alert conditions
* Publishing of the sensor data to an MQTT broker

Supported devices: Wave Plus, Wave Radon, Wave Mini, Wave Gen 1, Wave
Enhance and Corentium Home 2, see [Devices](docs/devices.md).

The bridge runs with Python 3.11 or later, as systemd service.

![Concept picture](Concept.png)

## Quick start

```
sudo python3 -m venv /opt/airthings_bridge
sudo /opt/airthings_bridge/bin/pip install https://github.com/Drolla/Airthings-Bridge/archive/refs/heads/main.zip
/opt/airthings_bridge/bin/airthings-bridge scan
/opt/airthings_bridge/bin/airthings-bridge "2930123456, office" --port 8080 --csv office.csv
```

Then open http://\<Raspberry Pi address\>:8080 in a browser.

## Documentation

* [Installation](docs/installation.md): Raspberry Pi, installation, service,
  upgrade from version 1.x
* [Configuration](docs/configuration.md): command line, YAML file, CSV file,
  mail alerts, MQTT, HTTP requests
* [Devices](docs/devices.md): supported devices and their values
* [Debugging](docs/debugging.md): device communication, mail, MQTT, logging
* [Changelog](CHANGELOG.md)

## License

MIT, see [LICENSE](LICENSE). The device access is based on
[waveplus-reader](https://github.com/Airthings/waveplus-reader) and
[airthings-ble](https://github.com/Airthings/airthings-ble) (MIT), the web UI
uses [Dygraphs](https://dygraphs.com) (MIT).
