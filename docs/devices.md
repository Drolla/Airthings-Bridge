# Supported devices

The bridge reads the Airthings devices over Bluetooth Low Energy (BLE). The
model is derived from the serial number (see under the magnetic backplate).
The device access is ported from
[airthings-ble](https://github.com/Airthings/airthings-ble).

| Model            | Serial number | Measurements (logged)                                              | Status values         |
|------------------|---------------|--------------------------------------------------------------------|-----------------------|
| Wave Gen 1       | 2900...       | humidity, radon_st, radon_lt, temperature                          | illuminance           |
| Wave Mini        | 2920...       | humidity, temperature, pressure, voc                               | illuminance, battery  |
| Wave Plus        | 2930...       | humidity, radon_st, radon_lt, temperature, pressure, co2, voc      | illuminance, battery  |
| Wave Radon       | 2950...       | humidity, radon_st, radon_lt, temperature                          | illuminance, battery  |
| Wave Enhance     | 321..., 322...| humidity, temperature, pressure, co2, voc, noise                   | lux, battery          |
| Corentium Home 2 | 325...        | radon_st, radon_week, radon_month, radon_lt, temperature, humidity | radon_year, battery   |

The measurements are logged into the CSV file and shown as graphs. All
values are provided by the `/data` request and can be published to MQTT.

Only the Wave Plus has been tested with real devices. The other models are
tested with the data samples of airthings-ble. Feedback is welcome.

## Values

| Key         | Value                     | Unit  |
|-------------|---------------------------|-------|
| radon_st    | Radon, 1 day average      | Bq/m³ |
| radon_week  | Radon, 7 days average     | Bq/m³ |
| radon_month | Radon, 30 days average    | Bq/m³ |
| radon_lt    | Radon, long term average  | Bq/m³ |
| radon_year  | Radon, 1 year average     | Bq/m³ |
| temperature | Temperature               | °C    |
| humidity    | Relative humidity         | %rH   |
| co2         | CO2                       | ppm   |
| voc         | Volatile organic compounds| ppb   |
| pressure    | Air pressure              | hPa   |
| noise       | Noise                     | dBA   |
| lux         | Light                     | lx    |
| illuminance | Illuminance               | raw sensor value for the Wave Plus and Wave Radon, % for the other models |
| battery     | Battery level             | %     |

Notes:

* The Corentium Home 2 provides its 1 year radon average also as long term
  average (`radon_lt`), which is logged instead of `radon_year`.
* Values that a device reports as invalid (e.g. a radon value during the
  first hours after the start) are omitted.
* The battery level is calculated from the battery voltage, with the
  discharge curves of airthings-ble.
* The illuminance and the battery level of the Wave Plus, Wave Radon and
  Wave Mini are read at most once per hour, to save battery.
