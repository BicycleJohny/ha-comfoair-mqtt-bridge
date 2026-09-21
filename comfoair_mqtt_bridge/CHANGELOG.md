# Changelog

## [0.2.10] - 2026-09-21

- Added Boost/Bathroom control through an MQTT Discovery switch.
- The climate entity now supports the `boost` preset.
- Controls and configuration entities are marked with the configuration
  entity category.
- Binary states use MQTT `ON`/`OFF` values for compatibility with the MQTT
  Comfoair Card.
- Filter status is published as `binary_sensor.filter_warning`; the original
  `sensor.filter_status` Discovery entry is removed.

## [0.2.9] - 2026-09-19

- Added an MQTT Discovery switch for pairing supply and return fan levels.
- When enabled, `Supply Air Level` values are copied to the corresponding
  `Return Air Level` values, and every subsequent change is written as a pair.
- When disabled, supply and return levels can be configured independently.

## [0.2.8] - 2026-09-18

- Removed selected EWT, post-heating, kitchen hood, and L1 `number` entities.
- The remaining `number` entities use `slider` mode.
- Removed MQTT Discovery entities are deleted during updates.
- Bypass remains a state-only entity.

## [0.2.7] - 2026-09-18

- Extended MQTT polling with available ComfoAir data.
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

- Added detailed hexadecimal logging for transmitted and received frames.

## [0.2.3] - 2026-09-18

- Timeouts now include the command and expected response.

## [0.2.2] - 2026-09-18

- Improved differentiation of ComfoAir connection-loss causes.

## [0.2.1] - 2026-09-18

- Removed the dependency on a pre-published GHCR image.
- Home Assistant now builds the image locally from `build.yaml`.
