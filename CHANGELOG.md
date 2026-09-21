# Changelog

All notable changes to this project are documented in this file.

## [0.2.10] - 2026-09-21

- Added Boost/Bathroom control through an MQTT Discovery switch.
- The climate entity now supports the `boost` preset.
- Boost is activated and deactivated by emulating short and long fan-button
  presses on the CC-Ease controller.
- Controls, fan calibration, delays, and reset buttons are marked as
  configuration entities and appear in the device Settings section.
- Binary states use the standard MQTT `ON`/`OFF` values for automatic
  recognition by the MQTT Comfoair Card.
- Filter status is now published as a `binary_sensor` with the
  `filter_warning` key; the old `sensor.filter_status` Discovery entry is
  removed.

## [0.2.9] - 2026-09-19

- Added an MQTT Discovery switch for pairing supply and return fan levels.
- When enabled, `Supply Air Level` values are copied to the corresponding
  `Return Air Level` values, and every subsequent change is written as a pair.
- When disabled, supply and return levels can be configured independently.

## [0.2.8] - 2026-09-18

- Removed unused `number` entities:
  - EWT High Temperature
  - EWT Low Temperature
  - EWT Speed Up
  - Extractor Hood Switch Off Delay Minutes
  - Kitchen Hood Speed Up
  - L1 Switch Off Delay Minutes
  - Postheating Target Temperature
- The remaining `number` entities use the MQTT Discovery `slider` mode.
- Removed entities are automatically deleted from MQTT Discovery during updates.
- Bypass remains a state-only entity because no verified protocol command is
  available to force it on.
- Added documentation about MQTT Discovery localization limitations.

## [0.2.7] - 2026-09-18

- Extended MQTT polling with available ComfoAir data:
  - fan speeds and percentages,
  - operation hours,
  - time delays,
  - physical and analog inputs,
  - bypass, preheating, enthalpy, and EWT/post-heating,
  - error diagnostics.
- Added MQTT Discovery entities of type `sensor`, `binary_sensor`, `number`,
  and `button`.
- Added commands for fan percentages, time delays, EWT/post-heating, and error
  reset.

## [0.2.6] - 2026-09-18

- Added the current return-air temperature to the MQTT `climate` entity.
- Set the temperature precision to 0.5 °C.

## [0.2.5] - 2026-09-18

- Added an MQTT Discovery button for filter reset.

## [0.2.4] - 2026-09-18

- Added detailed hexadecimal logging for transmitted and received RS232/TCP
  frames.

## [0.2.3] - 2026-09-18

- Response-wait timeouts now include the command and expected response.

## [0.2.2] - 2026-09-18

- Improved differentiation of ComfoAir connection-loss causes.

## [0.2.1] - 2026-09-18

- Removed the dependency on a pre-published GHCR image.
- Home Assistant now builds the image locally from `build.yaml`.
