# Configuration

The bridge is configured by command line arguments, by a YAML file, or by
both. Command line arguments take precedence over the YAML file. Mail alerts,
MQTT publishing and custom logging can only be configured by the YAML file.
The configuration is checked at the start; an error names the invalid key.

## Command line

```
airthings-bridge [run] [-h] [--config CONFIG] [--period PERIOD] [--port PORT]
                 [--csv CSV] [--data_retention DATA_RETENTION] [--log LOG]
                 [--emulation] [--developer] [sn ...]

positional arguments:
  sn                    10-digit serial number of a device (see under the
                        magnetic backplate). This number can be combined with
                        a device nickname, separated by a comma from the
                        serial number ("2930123456, my_office")

options:
  --config CONFIG       YAML configuration file
  --period PERIOD       Time in seconds between reading the sensor values
  --port PORT           Port of the HTTP web server
  --csv CSV             CSV file to store data
  --data_retention DATA_RETENTION
                        Data retention time in seconds
  --log LOG             Log file. If not specified the stdout is used
  --emulation           Emulates the devices. This allows testing all other
                        features, like data logging, HTTP service, etc.
  --developer           Enables developer features, like the /eval HTTP
                        request that evaluates Python expressions
```

`run` is the default command. The other commands help setting up and
debugging the bridge, see [Debugging](debugging.md).

## YAML file

The template [airthings_bridge.yaml](../airthings_bridge.yaml) documents all
settings. Overview:

| Key                 | Default    | Description                                            |
|---------------------|------------|--------------------------------------------------------|
| `sn`                | (required) | Serial numbers, optionally with device names           |
| `period`            | 120        | Time in seconds between reading the devices            |
| `retries`           | 3          | Extra attempts to read a device                        |
| `retry_delay`       | 1          | Time in seconds between the attempts                   |
| `port`              | none       | HTTP port of the web UI                                |
| `log`               | stdout     | Log file, or logging configuration (see [Debugging](debugging.md#logging)) |
| `csv`               | none       | CSV file of the logged data                            |
| `data_retention`    | 2678400    | Time in seconds the logged data is kept (31 days)      |
| `graph_decimations` | none       | Reduction of the older data shown in the graphs        |
| `smtp_server`       | none       | SMTP server of the mail alerts                         |
| `alerts`            | none       | Mail and print alerts                                  |
| `mqtt`              | none       | MQTT broker and published data                         |
| `emulation`         | False      | Emulated devices, for tests                            |
| `developer`         | False      | Enables the `/eval` HTTP request                       |

### CSV file and graphs

The measurements of all devices (see [Devices](devices.md)) are logged into
the CSV file, which is reloaded after a restart. The column labels are
`<device name>:<measurement>`.

`graph_decimations` reduces the data that the web UI loads: data older than
the age (in seconds) is averaged over the number of records (decimation
factor). The format changed with version 2.0.0:

```
graph_decimations:
   691200: 8  # older than 8 days
   90000: 3   # older than 25 hours
```

### Mail alerts

An alert has one or multiple sources (`<device name>:<value>`), a trigger
(`above` or `below` one or multiple levels, optionally `for` a time span and
with a `min_interval` between repeated alerts), and one or multiple actions
(`mail` or `print`). Mail alerts require the `smtp_server` configuration. See
the template for details.

### MQTT publishing

The selected values are published, all retained, to the following topics:

| Topic                              | Payload                                     |
|------------------------------------|---------------------------------------------|
| `<topic>/status`                   | Bridge status: Online, Offline, or 'Connection lost' (will) |
| `<topic>/<device>/status`          | Online, or Offline if the device couldn't be read |
| `<topic>/<device>/<value>`         | Value, e.g. `<topic>/office/radon_st`        |
| `<topic>/<device>/update_time`     | Time of the reading (seconds since epoch), if selected |
| `<topic>/publish_time`             | Time of the publication                     |

The bridge reconnects automatically if the connection to the broker is lost.

## HTTP requests

| Request              | Response                                                           |
|----------------------|--------------------------------------------------------------------|
| `/`                  | Redirect to the web UI, /ui/index.html                             |
| `/data`              | Current values of all devices (JSON)                               |
| `/csv`               | Logged data (CSV), selected by glob patterns separated by `;` (`/csv?*:temp*;*:hum*`) or by a regular expression (`/csv?re=office:.*`) |
| `/meta`              | Measurements and devices (JSON), used by the web UI                |
| `/eval?<expression>` | Developer mode only: result of a Python expression                 |
