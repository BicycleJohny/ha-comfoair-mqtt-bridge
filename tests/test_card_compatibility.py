from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = Path(__file__).parents[1] / "comfoair_mqtt_bridge" / "app.py"


def test_card_required_binary_sensor_topics_are_discovered() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    assert '"filter_warning"' in source
    assert '"bypass_valve_open"' in source
    assert '"summer_mode"' in source
    assert '"preheating_state"' in source
    assert '"payload_on": "ON"' in source
    assert '"payload_off": "OFF"' in source


def test_addon_source_remains_valid_python() -> None:
    ast.parse(APP_PATH.read_text(encoding="utf-8"))


def test_climate_discovery_remains_a_primary_control() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    climate_start = source.index('climate = {')
    climate_end = source.index('        self.mqtt.publish(', climate_start)
    climate_config = source[climate_start:climate_end]

    assert '"object_id": "ventilation"' in climate_config
    assert '"unique_id": "comfoair_mqtt_bridge_climate"' in climate_config
    assert '"entity_category"' not in climate_config
    assert '"preset_modes": ["boost"]' in climate_config
    assert '"preset_modes": ["none", "boost"]' not in climate_config
    assert '"current_temperature_topic": self._topic("climate/current_temperature")' in climate_config
