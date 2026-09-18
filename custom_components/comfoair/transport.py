"""Async TCP transport for a Waveshare RS232-to-Ethernet adapter."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from homeassistant.core import HomeAssistant

from .protocol import Frame, FrameParser, encode_frame

_LOGGER = logging.getLogger(__name__)

BAUDRATE = 9600
DEFAULT_WAIT_TIMEOUT = 2.0


class ComfoAirTransport:
    """Owns the TCP connection and a background read loop."""

    def __init__(self, host: str, port: int, hass: HomeAssistant) -> None:
        self.hass = hass
        self.host = host
        self.port = port
        self._reader_task: asyncio.Task[None] | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._write_lock = asyncio.Lock()
        self._is_closing = False
        self._waiters: dict[int, list[asyncio.Future[Frame]]] = {}
        self._callbacks: list[Callable[[Frame], None]] = []
        self._disconnect_callbacks: list[Callable[[], None]] = []
        self._last_rx = 0.0

    @property
    def is_connected(self) -> bool:
        return (
            self._writer is not None
            and not self._writer.is_closing()
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    @property
    def seconds_since_rx(self) -> float:
        return float("inf") if not self._last_rx else time.monotonic() - self._last_rx

    def add_disconnect_callback(self, callback: Callable[[], None]) -> None:
        self._disconnect_callbacks.append(callback)

    async def connect(self) -> None:
        self._is_closing = False
        await self._teardown()
        _LOGGER.debug("Opening Waveshare TCP connection to %s:%d", self.host, self.port)
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._last_rx = time.monotonic()
        self._reader_task = self.hass.async_create_background_task(
            self._reader_loop(), "ComfoAir TCP reader"
        )

    async def disconnect(self) -> None:
        self._is_closing = True
        await self._teardown()

    async def _teardown(self) -> None:
        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        self._reader_task = None
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._reader = None
        self._writer = None
        self._fail_waiters(ConnectionError("transport closed"))

    async def _reader_loop(self) -> None:
        parser = FrameParser()
        try:
            assert self._reader is not None
            while True:
                chunk = await self._reader.read(256)
                if not chunk:
                    raise ConnectionError("TCP connection closed")
                self._last_rx = time.monotonic()
                for frame in parser.feed(chunk):
                    self._dispatch(frame)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            if not self._is_closing:
                _LOGGER.warning("ComfoAir TCP reader stopped: %s", err)
                self._fail_waiters(err)
                for callback in self._disconnect_callbacks:
                    callback()

    def _dispatch(self, frame: Frame) -> None:
        if frame.is_ack:
            return
        for callback in self._callbacks:
            callback(frame)
        waiters = self._waiters.pop(frame.msg_id, [])
        for future in waiters:
            if not future.done():
                future.set_result(frame)

    async def send(self, cmd: int, data: bytes = b"") -> None:
        async with self._write_lock:
            if self._writer is None:
                raise ConnectionError("ComfoAir TCP transport is not connected")
            self._writer.write(encode_frame(cmd, data))
            await self._writer.drain()

    async def request(
        self,
        cmd: int,
        expected_msg_id: int,
        data: bytes = b"",
        timeout: float = DEFAULT_WAIT_TIMEOUT,
    ) -> Frame:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Frame] = loop.create_future()
        self._waiters.setdefault(expected_msg_id, []).append(future)
        try:
            await self.send(cmd, data)
            return await asyncio.wait_for(future, timeout)
        finally:
            waiters = self._waiters.get(expected_msg_id)
            if waiters and future in waiters:
                waiters.remove(future)
                if not waiters:
                    self._waiters.pop(expected_msg_id, None)

    def add_callback(self, callback: Callable[[Frame], None]) -> None:
        self._callbacks.append(callback)

    def _fail_waiters(self, error: BaseException) -> None:
        for futures in self._waiters.values():
            for future in futures:
                if not future.done():
                    future.set_exception(error)
        self._waiters.clear()
