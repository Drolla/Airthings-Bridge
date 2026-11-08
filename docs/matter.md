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
| Radon (`radon`)       | Radon Concentration Measurement (Bq/m³) | Wave Plus, Wave Radon, Wave Gen 1, Corentium Home 2 |
| Battery               | Power Source                            | all except Wave Gen 1           |
| Pressure (optional)   | Pressure Measurement                    | Wave Plus, Wave Mini, Wave Enhance |
| CO2 (optional)        | Carbon Dioxide Concentration Measurement (ppm) | Wave Plus, Wave Enhance  |
| VOC (optional)        | TVOC Concentration Measurement (ppm)    | Wave Plus, Wave Mini, Wave Enhance |

Pressure, CO2 and VOC are only exposed if they are selected by `values`, see
[Controllers](#controllers). All values are on one Matter endpoint per
device.

A Matter sensor has a single radon value: the 1 day average `radon_st` by
default, or the value selected by `radon`. The air quality is the worst
level of radon, CO2 and VOC, with the levels of the Airthings app:

| Value | Fair from | Poor from |
|-------|-----------|-----------|
| Radon | 100 Bq/m³ | 150 Bq/m³ |
| CO2   | 800 ppm   | 1000 ppm  |
| VOC   | 250 ppb   | 2000 ppb  |

The air quality includes CO2 and VOC also if they aren't exposed. VOC is
exposed in ppm (the devices measure ppb), as Google Home shows ppb values
1000 times too high. A device that couldn't be read is reported as
unreachable. Noise and light aren't exposed.

## Controllers

The controllers don't show all values:

* **Google Home** shows air quality, temperature, humidity, pressure, CO2,
  VOC and battery, but not radon. It shows air quality, pressure, CO2 and VOC
  of a device as a group: an update shows the values of the group that
  changed, and the others as "Unknown". Matter reports only the changed
  values, so the air quality, which rarely changes, would mostly be
  "Unknown". Pressure, CO2 and VOC are therefore not exposed by default.
* **Apple Home** shows the air quality, but not radon.
* **Amazon Alexa** supports air quality, temperature, humidity and VOC, but
  not radon, CO2 and pressure.
* **Home Assistant** shows all values; select pressure, CO2 and VOC with
  `values`.

Radon is thus only shown through the air quality in Google Home, Apple Home
and Alexa.

Google Home keeps the values of a device that it got at the pairing. After a
change of `values` (or of the bridge version, if it exposes other values),
remove the bridge in Google Home and pair it again.

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
communicate with it over IPv6 (link-local addresses are enough, the router
doesn't need IPv6) on UDP port 5540. The Raspberry Pi and the hub of the
controller (e.g. Google Nest, Apple TV, HomePod) have to reach each other in
the same network, in both directions. Wi-Fi repeaters, mesh access points
and client isolation may block the traffic between devices.

IPv6 has to be enabled on the Raspberry Pi. The network interface needs an
IPv6 address (`fe80::...`):

```
ip -6 addr show wlan0
```

If it has none, IPv6 is disabled (`sysctl net.ipv6.conf.wlan0.disable_ipv6`
shows `1`). Enable it permanently where it was disabled:

* A line `net.ipv6.conf.….disable_ipv6 = 1` in /etc/sysctl.conf or
  /etc/sysctl.d/*.conf: remove it, then run `sudo sysctl --system`.
* The network connection (`nmcli -g ipv6.method connection show <name>`
  shows `disabled`):

  ```
  sudo nmcli connection modify <name> ipv6.method auto
  sudo nmcli connection up <name>
  ```

Restart the bridge afterwards, as matter.js reads the network addresses at
its start. Check then that the bridge announces its IPv6 address:
`avahi-browse` (package avahi-utils) shows the host name of the bridge,
`avahi-resolve` its IPv6 address (`_matterc._udp` instead of `_matter._tcp`
while the bridge isn't paired):

```
avahi-browse -rt _matter._tcp
avahi-resolve -6 -n DCA6321E9C410000.local
```

On Windows, the mDNS service of Windows conflicts with matter.js, and the
controllers don't find the bridge. Run the bridge with Matter on Linux.

## Pairing

The web UI shows the Matter status below the current data. While no
controller is paired, its link opens the pairing page with the QR code and
the manual pairing code. The bridge also logs them at its start, e.g. in the
journal of the service:

```
journalctl -u airthings_bridge | grep "pairing code"
```

```
Matter bridge not paired. Manual pairing code: 34970112332, QR code content: MT:Y.K90...
```

Scan the QR code or enter the manual pairing code in the controller. The
pairing code is generated at the first start and stays the same; `passcode`
and `discriminator` set it explicitly.

Like the code on the label of a Matter device, the pairing code allows
anybody in the local network to pair the bridge as long as it isn't paired.
It isn't shown anymore after the first pairing.

The bridge is not certified, and uses the Matter test vendor ID (0xFFF1,
product ID 0x8000):

* **Apple Home**: Add accessory, More options, enter the code. Confirm the
  warning about the uncertified accessory.
* **Google Home**: Add device, Matter device, enter the code. If Google Home
  refuses the uncertified device, create a Matter integration with vendor ID
  0xFFF1 and product ID 0x8000 in the
  [Google Home Developer Console](https://console.home.google.com/).
* **Home Assistant**: Matter integration, add the device with the Home
  Assistant companion app.

Further controllers are added with a pairing code of a paired controller
(e.g. "Linked Matter apps & services" in the device settings of Google
Home, "Turn on pairing mode" in Apple Home), as the pairing code is no
longer logged.

## Troubleshooting

### The controller doesn't find the bridge when pairing

* The bridge announces itself for pairing only while it isn't paired (web UI:
  "Matter: not paired"). Check the announcement with
  `avahi-browse -rt _matterc._udp`.
* Check IPv6 and the network, see [Network](#network). The phone and the hub
  of the controller have to be in the same network as the Raspberry Pi.

### The controller shows the bridge as offline

* After a restart of the bridge, the hub of the controller reconnects within
  a few minutes. The log shows `Reestablished 0 of 1 former subscriptions`
  if the bridge couldn't resume the subscription of the hub itself.
* IPv6 is disabled on the Raspberry Pi, see [Network](#network).
* The Raspberry Pi doesn't reach the hub. Find the link-local address of the
  hub, e.g. of a Google hub in the IPv6 lines of
  `avahi-browse -rt _googlecast._tcp`, or in the debug log
  (`Pairing request « udp://[fe80::…]`), and check that it answers:

  ```
  ping -6 -c 3 fe80::22df:b9ff:fe29:fb89%wlan0
  ```

  If neither this ping nor a ping of its IPv4 address is answered, the
  network blocks the traffic between the devices.

### Values are shown as "Unknown"

* Google Home: pressure, CO2 or VOC are selected by `values`, see
  [Controllers](#controllers).
* Values that a device reports as invalid (e.g. radon during the first hours
  after its start) aren't exposed.

### Values are missing or outdated after a change of `values`

Remove the bridge in the controller and pair it again, see
[Controllers](#controllers).

### The bridge stays paired after its removal in the controller

The controller removes its pairing at the bridge, which then shows the
pairing code again. Google Home did that only about two hours after the
removal in the app; its hub stayed connected until then. Check the pairing
state with the `/matter` request (see [Debugging](#debugging)). Wait, or
reset the pairings, see [Reset](#reset).

## Reset

To remove all pairings, stop the bridge, delete the storage directory, and
start the bridge. It shows a new pairing code. Remove the bridge also in the
controllers.

## Debugging

The `/matter` HTTP request shows the pairing state, and the number of paired
controllers:

```
curl http://<Raspberry Pi address>/matter
```

```
{"paired": true, "controllers": 1}
```

The bridge logs the warnings and errors of the Matter process. The level
INFO for the `airthings_bridge.consumers.matter` logger adds the state of
the Matter process (online, pairings), and DEBUG the debug messages of
matter.js, including all messages exchanged with the controllers. The
debug log grows fast; use it only for the analysis. Example of a log
configuration (see [Logging](debugging.md#logging)):

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
        filename: /var/log/airthings_bridge/airthings_bridge.log
        encoding: utf8
        mode: a
    root:
      level: WARNING
      handlers: [file]
    loggers:
      airthings_bridge.bridge:
        level: INFO
      airthings_bridge.consumers.matter:
        level: DEBUG
```

Useful lines of the debug log:

| Log line | Meaning |
|----------|---------|
| `Pairing request « udp://[fe80::…]:5540` | A controller connects, from the address of its hub |
| `Subscribe successful` | The controller subscribed, it gets the values |
| `ReportData`, then `StatusResponse` | Values sent, and acknowledged by the controller |
| `Reestablished 0 of 1 former subscriptions` | After a restart, the bridge couldn't resume a subscription; the controller reconnects itself |
| `removeFabric`, `pairings changed, 0 paired controller(s)` | A controller removed its pairing |
