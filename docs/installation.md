# Installation

## Raspberry Pi

Install Raspberry Pi OS (Lite is enough) with
[Raspberry Pi Imager](https://www.raspberrypi.com/software/), which can also
set up the Wi-Fi, the user and SSH.

The bridge runs on any Raspberry Pi with Bluetooth Low Energy (BLE), built
in or via an adapter, and Raspberry Pi OS Bookworm or later (Python 3.11 or
later). Update the system, install the required packages and enable the
Bluetooth interface:

```
sudo apt update
sudo apt full-upgrade
sudo apt install -y python3-venv git
sudo bluetoothctl power on
```

The devices should run the latest firmware. Connect them once to the
Airthings app to update it.

## Airthings Bridge

The bridge is a git clone in /opt/airthings_bridge, with its Python virtual
environment in `.venv`. It runs under a dedicated user without root
privileges, and writes its CSV file and log file into /var/airthings_bridge.

Create the user, which has access to BLE, and the data directory:

```
sudo useradd --system --home-dir /opt/airthings_bridge --shell /usr/sbin/nologin --groups bluetooth airthings_bridge
sudo install -d -o airthings_bridge -g airthings_bridge /var/airthings_bridge
```

Fetch and install the bridge:

```
sudo git clone https://github.com/Drolla/Airthings-Bridge.git /opt/airthings_bridge
sudo chown -R airthings_bridge: /opt/airthings_bridge
sudo -u airthings_bridge -H bash -c '
  cd /opt/airthings_bridge
  python3 -m venv .venv
  .venv/bin/pip install -e .
'
```

Check that the devices are in range:

```
sudo -u airthings_bridge /opt/airthings_bridge/.venv/bin/airthings-bridge scan
```

Copy the configuration template and adapt it, see
[Configuration](configuration.md). The file may contain passwords, so only
the user airthings_bridge can read it:

```
sudo -u airthings_bridge cp /opt/airthings_bridge/airthings_bridge.yaml /opt/airthings_bridge/config.yaml
sudo chmod 600 /opt/airthings_bridge/config.yaml
sudo nano /opt/airthings_bridge/config.yaml
```

Start the bridge for a first test, with the log written to the terminal.
Only the service may open port 80, so the test uses port 8080:

```
sudo -u airthings_bridge /opt/airthings_bridge/.venv/bin/airthings-bridge \
       --config /opt/airthings_bridge/config.yaml --port 8080 --log ""
```

Open the web page http://\<Raspberry Pi address\>:8080 in a browser.

## Service

The systemd service runs the bridge as user airthings_bridge, and may open
the HTTP port 80. Install and start it:

```
sudo cp /opt/airthings_bridge/systemd/airthings_bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now airthings_bridge
```

Check the service status and the log output (if no log file is configured):

```
systemctl status airthings_bridge
journalctl -u airthings_bridge -f
```

Stop and disable the service with:

```
sudo systemctl disable --now airthings_bridge
```

## Update

```
sudo systemctl stop airthings_bridge
sudo -u airthings_bridge -H bash -c '
  cd /opt/airthings_bridge
  git pull
  .venv/bin/pip install -e .
'
sudo systemctl start airthings_bridge
```

## Upgrade from version 1.x (Wave Plus Bridge)

* Stop and remove the init.d service of version 1.x:

  ```
  sudo /etc/init.d/waveplus_bridge stop
  sudo update-rc.d waveplus_bridge remove
  sudo rm /etc/init.d/waveplus_bridge
  ```

* Install version 2 as described above, without starting the service yet.
  Take over the settings of /opt/waveplus_bridge/waveplus_bridge.yaml into
  `config.yaml`, and update the graph decimations, see
  [Configuration](configuration.md#csv-file-and-graphs).
* Move the CSV file to the new location:

  ```
  sudo mv /var/log/waveplus_bridge.csv /var/airthings_bridge/airthings_bridge.csv
  sudo chown airthings_bridge: /var/airthings_bridge/airthings_bridge.csv
  ```

  It is converted to the new format at the first start. The original file is
  kept as `airthings_bridge.csv.v1.bak`.
* Start the service, and remove the old installation:
  `sudo rm -r /opt/waveplus_bridge`

The [changelog](../CHANGELOG.md) lists all changes of version 2.
