# Matter

The bridge can expose the devices as Matter devices, so that Matter
controllers like Apple Home, Google Home or Home Assistant show their values.
It appears as a Matter bridge with an air quality sensor per device.

The Matter side runs in a separate Node.js process based on
[matter.js](https://github.com/project-chip/matter.js). The bridge starts it,
passes it the values of each reading, and restarts it if it ends
unexpectedly. The bridge goes online in Matter after the first reading of the
devices, so that the controllers get real values from the start.

## Exposed values

| Value                 | Matter cluster                          | Models                          |
|-----------------------|-----------------------------------------|---------------------------------|
| Air quality           | Air Quality (good, fair, poor)          | all                             |
| Temperature           | Temperature Measurement                 | all                             |
| Humidity              | Relative Humidity Measurement           | all                             |
| Pressure              | Pressure Measurement                    | Wave Plus, Wave Mini, Wave Enhance |
| Radon (`radon`)       | Radon Concentration Measurement (Bq/m³) | Wave Plus, Wave Radon, Wave Gen 1, Corentium Home 2 |
| CO2                   | Carbon Dioxide Concentration Measurement (ppm) | Wave Plus, Wave Enhance  |
| VOC                   | TVOC Concentration Measurement (ppm)    | Wave Plus, Wave Mini, Wave Enhance |
| Battery               | Power Source                            | all except Wave Gen 1           |

A Matter sensor has a single radon value: the 1 day average `radon_st` by
default, or the value selected by `radon`. The air quality is the worst
level of radon, CO2 and VOC, with the levels of the Airthings app:

| Value | Fair from | Poor from |
|-------|-----------|-----------|
| Radon | 100 Bq/m³ | 150 Bq/m³ |
| CO2   | 800 ppm   | 1000 ppm  |
| VOC   | 250 ppb   | 2000 ppb  |

VOC is exposed in ppm (the devices measure ppb), as Google Home shows ppb
values 1000 times too high. A device that couldn't be read is reported as
unreachable. Noise and light aren't exposed.

The controllers don't show all values: Home Assistant shows all of them,
Apple Home and Google Home mainly the air quality, the temperature and the
humidity. Radon is rarely shown.

## Installation

The Matter process requires Node.js 20.19 or later (or 22.13 or later).
Install Node.js and check its version:

```
sudo apt install -y nodejs npm
node --version
```

If the version is too old (e.g. Node.js 18 of Raspberry Pi OS Bookworm),
install a current version from [NodeSource](https://github.com/nodesource/distributions)
instead.

Install matter.js (about 120 MB) in the bridge installation, as user
airthings_bridge:

```
sudo -u airthings_bridge -H bash -c '
  cd /opt/airthings_bridge/airthings_bridge/matter_js
  npm ci
'
```

Repeat the `npm ci` command after each update of the bridge, see
[Installation](installation.md#update).

The Matter state (pairings and pairing code) is stored in a directory, e.g.
in /var/lib/airthings_bridge:

```
matter:
    storage: /var/lib/airthings_bridge/matter
```

See [Configuration](configuration.md#matter) for the other settings.

## Network

The controllers find the bridge by mDNS (multicast UDP port 5353), and
communicate with it over IPv6 (link-local addresses are enough) on UDP port
5540. The Raspberry Pi has to be in the same network as the controller, or
as its hub (e.g. Apple TV, HomePod, Google Nest).

## Pairing

At its start, the bridge logs the pairing code while no controller is
paired, e.g. in the journal of the service:

```
journalctl -u airthings_bridge | grep "pairing code"
```

```
Matter bridge not paired. Manual pairing code: 34970112332, QR code: https://project-chip.github.io/connectedhomeip/qrcode.html?data=MT%3AY.K90...
```

Enter the manual pairing code in the controller, or open the link to show
the QR code. The pairing code is generated at the first start and stays the
same; `passcode` and `discriminator` set it explicitly.

The bridge is not certified, and uses the Matter test vendor ID (0xFFF1,
product ID 0x8000):

* **Apple Home**: Add accessory, More options, enter the code. Confirm the
  warning about the uncertified accessory.
* **Google Home**: Test vendor IDs are only accepted for a Matter integration
  of the [Google Home Developer Console](https://console.home.google.com/)
  with vendor ID 0xFFF1 and product ID 0x8000.
* **Home Assistant**: Matter integration, add the device with the Home
  Assistant companion app.

Further controllers are added with the pairing function of a paired
controller (e.g. "Turn on pairing mode" in Apple Home), as the pairing code
is no longer logged.

## Reset

To remove all pairings, stop the bridge, delete the storage directory, and
start the bridge. It logs a new pairing code. Remove the bridge also in the
controllers.

## Debugging

The bridge logs the warnings and errors of the Matter process. More details
are logged with the level INFO for the `airthings_bridge.consumers.matter`
logger, and the matter.js information with the level DEBUG, see
[Logging](debugging.md#logging).
