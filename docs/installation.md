# Installation

## Raspberry Pi

The bridge runs on any Raspberry Pi with Bluetooth Low Energy (BLE), built
in or via an adapter, and Raspberry Pi OS Bookworm or later (Python 3.11 or
later). Update the system and enable the Bluetooth interface:

```
sudo apt update
sudo apt full-upgrade
sudo bluetoothctl power on
```

The BLE access doesn't require root privileges, but membership of the
`bluetooth` group. Add your user to this group to run the commands of
[Debugging](debugging.md) (log out and in again to apply it):

```
sudo usermod -aG bluetooth $USER
```

The devices should run the latest firmware. Connect them once to the
Airthings app to update it.

## Airthings Bridge

Install the bridge into a Python virtual environment in /opt/airthings_bridge
(Raspberry Pi OS doesn't allow installing Python packages globally with pip):

```
sudo python3 -m venv /opt/airthings_bridge
sudo /opt/airthings_bridge/bin/pip install https://github.com/Drolla/WavePlus_Bridge/archive/master.zip
```

Check that the devices are in range:

```
/opt/airthings_bridge/bin/airthings-bridge scan
```

Download the configuration template and adapt it, see
[Configuration](configuration.md):

```
sudo wget -O /opt/airthings_bridge/airthings_bridge.yaml https://raw.githubusercontent.com/Drolla/WavePlus_Bridge/master/airthings_bridge.yaml
sudo nano /opt/airthings_bridge/airthings_bridge.yaml
```

Start the bridge for a first test, with the log written to the terminal:

```
sudo /opt/airthings_bridge/bin/airthings-bridge \
       --config /opt/airthings_bridge/airthings_bridge.yaml --log ""
```

Open the web page http://\<Raspberry Pi address\>:\<port\> in a browser.

## Service

The bridge runs as systemd service under a dedicated user, which has access
to BLE, may open the HTTP port 80, and writes into /var/lib/airthings_bridge
(CSV file) and /var/log/airthings_bridge (log file). Create the user, install
the service file, and start the service:

```
sudo useradd --system --no-create-home airthings_bridge
sudo wget -O /etc/systemd/system/airthings_bridge.service https://raw.githubusercontent.com/Drolla/WavePlus_Bridge/master/systemd/airthings_bridge.service
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
sudo /opt/airthings_bridge/bin/pip install --upgrade https://github.com/Drolla/WavePlus_Bridge/archive/master.zip
sudo systemctl restart airthings_bridge
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
  the new configuration file, and update the graph decimations, see
  [Configuration](configuration.md#csv-file-and-graphs).
* Move the CSV file to the new location:

  ```
  sudo mkdir -p /var/lib/airthings_bridge
  sudo mv /var/log/waveplus_bridge.csv /var/lib/airthings_bridge/airthings_bridge.csv
  sudo chown -R airthings_bridge: /var/lib/airthings_bridge
  ```

  It is converted to the new format at the first start. The original file is
  kept as `airthings_bridge.csv.v1.bak`.
* Start the service, and remove the old installation:
  `sudo rm -r /opt/waveplus_bridge`

The [changelog](../CHANGELOG.md) lists all changes of version 2.
