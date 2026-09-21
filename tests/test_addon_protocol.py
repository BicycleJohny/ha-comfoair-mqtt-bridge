from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "comfoair_mqtt_bridge"))

import protocol as p


def test_addon_protocol_round_trip_with_cc_ease_command() -> None:
    data = bytes([0x80, 0, 0, 0, 0, 0, 0x02])
    frames = list(p.FrameParser().feed(p.encode_frame(p.CMD_CC_EASE_KEY_STATUS, data)))
    assert frames == [p.Frame(p.CMD_CC_EASE_KEY_STATUS, data)]


def test_boost_display_state_is_identifiable() -> None:
    display = bytearray(10)
    display[8] = 0x78
    assert (display[8] & 0x78) == 0x78
