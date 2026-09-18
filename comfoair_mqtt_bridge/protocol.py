"""ComfoAir wire protocol used by the standalone Home Assistant add-on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

PREFIX = 0x07
HEAD = 0xF0
TAIL = 0x0F
ACK = 0xF3
CHECKSUM_SEED = 173

CMD_GET_FIRMWARE_VERSION = 0x69
RES_GET_FIRMWARE_VERSION = 0x6A
CMD_GET_FAN_STATUS = 0x0B
RES_GET_FAN_STATUS = 0x0C
CMD_GET_VENTILATION_LEVEL = 0xCD
RES_GET_VENTILATION_LEVEL = 0xCE
CMD_GET_TEMPERATURES = 0xD1
RES_GET_TEMPERATURES = 0xD2
CMD_GET_STATUS = 0xD5
RES_GET_STATUS = 0xD6
CMD_GET_FAULTS = 0xD9
RES_GET_FAULTS = 0xDA
CMD_SET_LEVEL = 0x99
CMD_SET_COMFORT_TEMPERATURE = 0xD3
CMD_RESET_AND_SELF_TEST = 0xDB


@dataclass(frozen=True)
class Frame:
    msg_id: int
    data: bytes

    @property
    def is_ack(self) -> bool:
        return self.msg_id == ACK


def _checksum(cmd: int, data: bytes) -> int:
    return (CHECKSUM_SEED + cmd + len(data) + sum(data)) & 0xFF


def encode_frame(cmd: int, data: bytes = b"") -> bytes:
    body = bytearray(data + bytes([_checksum(cmd, data)]))
    escaped = bytearray()
    for value in body:
        escaped.append(value)
        if value == PREFIX:
            escaped.append(PREFIX)
    return bytes([PREFIX, HEAD, 0, cmd, len(data)]) + bytes(escaped) + bytes(
        [PREFIX, TAIL]
    )


class FrameParser:
    """Incremental parser for ComfoAir frames."""

    def __init__(self) -> None:
        self._state = 0
        self._body = bytearray()
        self._remaining = 0

    def feed(self, chunk: bytes) -> Iterator[Frame]:
        for value in chunk:
            frame = self._step(value)
            if frame is not None:
                yield frame

    def _reset(self) -> None:
        self._state = 0
        self._body.clear()
        self._remaining = 0

    def _resync(self, value: int) -> None:
        self._reset()
        if value == PREFIX:
            self._state = 1

    def _step(self, value: int) -> Frame | None:
        if self._state == 0:
            if value == PREFIX:
                self._state = 1
        elif self._state == 1:
            if value == ACK:
                self._reset()
                return Frame(ACK, b"")
            if value == HEAD:
                self._state = 2
            else:
                self._resync(value)
        elif self._state == 2:
            if value == 0:
                self._state = 3
            else:
                self._resync(value)
        elif self._state == 3:
            self._body.append(value)
            self._state = 4
        elif self._state == 4:
            self._body.append(value)
            self._remaining = value + 1
            self._state = 5
        elif self._state == 5:
            if self._remaining == 0:
                if value == PREFIX:
                    self._state = 7
                else:
                    self._resync(value)
            elif value == PREFIX:
                self._state = 6
            else:
                self._body.append(value)
                self._remaining -= 1
        elif self._state == 6:
            if value == PREFIX:
                self._body.append(value)
                self._remaining -= 1
                self._state = 5
            else:
                self._resync(value)
        elif self._state == 7:
            if value == TAIL:
                frame = self._finalize()
                self._reset()
                return frame
            self._resync(value)
        return None

    def _finalize(self) -> Frame | None:
        if len(self._body) < 3:
            return None
        cmd, length = self._body[:2]
        if len(self._body) != length + 3:
            return None
        data = bytes(self._body[2:-1])
        if self._body[-1] != _checksum(cmd, data):
            return None
        return Frame(cmd, data)
