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

Mail alerts require the `smtp_server` configuration:

| Key                | Default    | Description                                             |
|--------------------|------------|---------------------------------------------------------|
| `server`           | (required) | SMTP server address                                     |
| `port`             | 587        | SMTP server port, e.g. 25, 465, 587                     |
| `security`         | none       | `SSL`, or `TLS` (STARTTLS); the certificate is verified |
| `user`, `password` | none       | Login                                                   |

An alert has:

* `sources`: one or multiple values, `<device name>:<value>`
* `trigger`: the condition
  * `above` or `below`: a level, or a list of levels
  * `for`: time span (seconds or `HH:MM:SS`) the condition has to last,
    applied to each level
  * `min_interval`: minimum time between repeated alerts, ignored if a
    higher level is reached
* `actions`: one or multiple actions
  * `mail`: `from`, `to` (address or list), `subject`, `message`
  * `print`: `message`, logged with level INFO

In `message`, `%v` is replaced by the value, `%d` by the device and `%s` by
the value name.

```
smtp_server:
    server: mail.server.com
    port: 465
    security: SSL
    user: bridge@myhome.com
    password: secret

alerts:
    -   sources: [office:radon_st, living:radon_st]
        trigger:
            above: [100, 200, 400]
            for: "00:30:00"
            min_interval: "12:00:00"
        actions:
            -   mail:
                    from: bridge@myhome.com
                    to: [liam@family.com, olivia@family.com]
                    subject: Radon alert
                    message: "Radon level %v Bq/m3 (%d)"
            -   print:
                    message: "Radon level %v Bq/m3 (%d)"
```

### MQTT publishing

| Key         | Default                    | Description                                       |
|-------------|----------------------------|---------------------------------------------------|
| `host`      | (required)                 | MQTT broker address                               |
| `port`      | 1883                       | MQTT broker port                                  |
| `topic`     | none                       | Topic root                                        |
| `publish`   | (required)                 | Published values per device; `'*'` selects all values, or all devices |
| `client_id` | random                     | Client ID                                         |
| `auth`      | none                       | `username`, `password`                            |
| `tls`       | none                       | `ca_certs`, `certfile`, `keyfile`, `tls_version`, `ciphers`, `insecure` |
| `will`      | 'Connection lost' to `<topic>/status` | `topic`, `payload`, `qos`, `retain`    |

```
mqtt:
    host: test.mosquitto.org
    topic: my_home/airthings_bridge
    publish:
        office: [radon_st, radon_lt]
        living: '*'
```

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

`/data` response (times in seconds since epoch):

```
{"current_time": 1761670800,
 "devices": {"office": {"humidity": 59.0, "radon_st": 34, ..., "update_time": 1761670790}}}
```
