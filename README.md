# ComfoAir RS232 MQTT Bridge

Home Assistant OS add-on for Zehnder ComfoAir Standard 375 connected through a
Waveshare RS232 to Ethernet (B) adapter. The add-on uses the ComfoAir wire
protocol over TCP and publishes MQTT auto-discovery entities through the MQTT
service provided by Home Assistant.

## Install as a Home Assistant app

1. Open **Settings → Apps → App store**.
2. Add this repository URL as an app repository:
   `https://github.com/BicycleJohny/ha-comfoair-mqtt-bridge`
3. Install **ComfoAir MQTT Bridge**.
4. Configure the Waveshare IP address, TCP port (normally `8899`), MQTT base
   topic, and log level.
5. Start the app and enable **Start on boot**.

The app obtains MQTT host and credentials from the Home Assistant Supervisor
service. MQTT credentials are not stored in this repository or in the app
source code. The app image is built locally by Home Assistant from the
repository's `build.yaml`; no GHCR login or public container package is
required.

The former `custom_components/comfoair` directory is retained as a reusable
protocol-based integration reference. The supported Home Assistant OS
deployment is the `comfoair_mqtt_bridge` add-on.

## RS232 Server settings

Configure the adapter for transparent TCP communication:

- serial mode: RS232
- baud rate: 9600
- data bits: 8
- parity: none
- stop bits: 1
- TCP server mode, port `8899`

Use the Zehnder-specific RJ45 wiring. Do not use a Cisco-style RS232 cable.

## MQTT topics

The integration publishes retained discovery and state topics below the
configured base topic. Commands are accepted below `<base>/set/`, including:

- `climate/mode`: `off` or `fan_only`
- `climate/fan_mode`: `off`, `low`, `medium`, `high`, `auto`
- `climate/preset`: `none` or `boost`
- `climate/temperature`: Celsius value
- `boost`: `ON` or `OFF` for the Boost / Bathroom switch
- `filter_reset`: `PRESS`

The Boost / Bathroom switch emulates the CC-Ease fan-button action used by the
ComfoAir controller. It does not electrically switch the physical bathroom
input.

The climate entity, Boost/Bathroom switch, and filter reset are primary
controls. Other writable entities, including fan-level calibration, delay
times, fan pairing, and error reset, are marked as Home Assistant
configuration entities and appear under the device's **Settings** section.
- `pair_fan_levels`: `ON` or `OFF`

The app creates MQTT climate and sensor entities through Home Assistant MQTT
discovery. It also exposes fan tachometer/percentage sensors, operation-hour
counters, temperatures, filter/error diagnostics, physical input and optional
bypass/preheating/EWT/postheating entities. Writable fan percentages, selected
time delays, and filter warning weeks are published as slider number entities;
filter and error reset are buttons. Optional entities are only polled when the
controller advertises the corresponding feature.

The available protocol provides a read-only bypass status command, but no
verified command for forcing the bypass valve open or closed, so no bypass
control switch is exposed. MQTT Discovery also does not provide per-user
language variants for entity names; discovery names are therefore published in
English and Home Assistant's standard UI labels remain localized.

Additional command topics use the same retained MQTT API:

- `fan/<level_name>` for the eight supply/return fan percentages
- `pair_fan_levels`: when enabled, each supply and return level is written as
  a pair; the supply value is copied to the matching return level when the
  switch is enabled
- `time_delay/<name>` for switch/boost delays and filter warning weeks
- `ewt_postheating/<name>` for EWT and postheating values
- `error_reset`: `PRESS`

## Logging

The app writes its own structured log output to the Home Assistant app log.
Use the `log_level` option (`DEBUG`, `INFO`, `WARNING`, or `ERROR`) to control
verbosity. Normal operation logs only connection, MQTT, and warning/error
events; frame-level details are available at `DEBUG`.
