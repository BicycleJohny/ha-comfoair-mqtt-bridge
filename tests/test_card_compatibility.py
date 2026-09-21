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
