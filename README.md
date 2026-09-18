# ComfoAir RS232 MQTT Bridge

Home Assistant custom integration for Zehnder ComfoAir Standard 375 connected
through a Waveshare RS232 to Ethernet (B) adapter. The integration uses the
ComfoAir wire protocol over a TCP stream and publishes MQTT auto-discovery
entities through the MQTT integration already configured in Home Assistant.

## Install through HACS

1. Add this GitHub repository as a **Custom repository** in HACS.
2. Select category **Integration** and install **ComfoAir RS232 MQTT Bridge**.
3. Restart Home Assistant.
4. Add the integration in **Settings → Devices & services**.

The setup form asks for the Waveshare IP address, TCP port (normally `8899`)
and the MQTT base topic (normally `comfoair`). MQTT credentials are not stored
by this integration; Home Assistant's configured MQTT connection is used.

## Waveshare settings

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
- `climate/temperature`: Celsius value
- `filter_reset`: `PRESS`

The component also creates native Home Assistant entities backed by the same
coordinator, including diagnostic sensors and fan-level controls.
