# Copilot instructions

## Project focus

The supported deployment is the Home Assistant OS application/add-on in
`comfoair_mqtt_bridge/`. It connects to a Zehnder ComfoAir Standard 375 over a
Waveshare RS232-to-Ethernet TCP server and publishes Home Assistant MQTT
Discovery entities. `custom_components/comfoair/` is retained as a HACS/custom
integration reference and shares the protocol concepts, but changes intended
for the supported deployment normally belong in the add-on.

## Build, test, and validation commands

- Run the full Python test suite:
  `python -m pytest`
- Run one test module:
  `python -m pytest tests/test_addon_protocol.py`
- Run one test function:
  `python -m pytest tests/test_protocol.py::test_encode_then_parse_round_trip`
- Check Python syntax without running the application:
  `python -m compileall comfoair_mqtt_bridge custom_components tests`
- Build the add-on image locally for amd64:
  `docker build --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest -f comfoair_mqtt_bridge/Dockerfile comfoair_mqtt_bridge`

The test configuration is in `pyproject.toml`; tests are discovered from
`tests/`, use `pytest-asyncio` auto mode, and include filters for known
third-party Home Assistant deprecation warnings. There is no separate lint
configuration or lint command in this repository.

## Architecture

The add-on entrypoint is `comfoair_mqtt_bridge/run.sh`. Home Assistant
Supervisor supplies add-on options and MQTT service credentials; the script
validates the Waveshare host and starts `app.py`. Do not hardcode MQTT
credentials or assume a local broker hostname.

`comfoair_mqtt_bridge/app.py` owns the standalone runtime:

- Paho MQTT runs its network loop in the background.
- An asyncio TCP connection talks to the Waveshare adapter.
- The bridge polls standard and feature-dependent ComfoAir commands, parses
  unsolicited/replied frames, stores the latest state, and republishes retained
  MQTT state.
- MQTT Discovery configuration is retained under `homeassistant/.../config`.
- Commands arrive under `<base-topic>/set/#` and are translated to ComfoAir
  protocol writes.

`comfoair_mqtt_bridge/protocol.py` is the wire-format boundary. Frames use the
`0x07 0xF0 0x00 <command> <length> <data> <checksum> 0x07 0x0F` format with
checksum seed `173`; literal `0x07` bytes in the body are escaped by doubling.
Keep framing, escaping, checksum, and byte conversion logic here rather than
duplicating it in the bridge.

The custom integration follows a parallel Home Assistant-native design:
`transport.py` owns the TCP reader, `coordinator.py` polls and parses frames,
platform modules expose entities, and `mqtt_bridge.py` publishes MQTT
Discovery. If modifying that reference implementation, preserve the
coordinator/transport separation and its feature-gated polling.

## Repository-specific conventions

- Treat `comfoair_mqtt_bridge/config.yaml` as the add-on manifest. Keep its
  version synchronized with both changelogs when user-visible add-on behavior
  changes.
- The add-on supports `amd64`, `aarch64`, `armv7`, and `armhf`; changes to
  image dependencies or startup behavior must work through `build.yaml` and
  `Dockerfile` on all declared architectures.
- Use the configured base topic with `_topic()` for all runtime state and
  command topics. MQTT state and Discovery configuration are retained, and
  availability is published as `online`/`offline`.
- Boolean MQTT payloads are `ON`/`OFF`. This is required for Home Assistant
  MQTT entities and compatibility with `TimWeyand/lovelace-comfoair`.
- Keep the climate entity as the primary control. Configuration-oriented
  entities such as Boost/Bathroom, fan pairing, calibration, delays, and reset
  actions use MQTT Discovery `entity_category: config`.
- Optional entities and polling commands must be gated by feature flags learned
  from the ComfoAir status response. Do not publish controls for unsupported
  hardware features.
- Boost/Bathroom is CC-Ease button emulation through command `0x37`; it does not
  electrically switch the physical bathroom input. Preserve the long-press
  activation, short-press cancellation, and display-state detection behavior.
- When removing or renaming a Discovery entity, publish a retained empty
  configuration for the old component/object ID, as done by
  `_remove_discovery()`, so stale entities are removed from Home Assistant.
- Use structured logging through the module logger. Normal operation should
  remain concise; frame TX/RX payloads belong at `DEBUG`, while connection,
  command validation, and protocol failures should be visible at the
  appropriate warning/error level.
- Keep protocol and MQTT behavior covered by focused tests in `tests/`. The
  card compatibility test intentionally checks source-level Discovery markers
  such as `filter_warning`, `bypass_valve_open`, `summer_mode`,
  `preheating_state`, and `ON`/`OFF` payloads.

## Documentation and deployment references

`README.md` is the source for installation, Waveshare serial settings, MQTT
topics, logging, Boost/Bathroom behavior, and Lovelace card compatibility.
`repository.yaml` describes the add-on repository metadata. The supported
installation path is the Home Assistant OS app/add-on, not the retained
custom integration directory.
