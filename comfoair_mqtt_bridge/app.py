"""Standalone ComfoAir MQTT bridge for Home Assistant OS."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
from typing import Any

import paho.mqtt.client as mqtt

import protocol as p

LOGGER = logging.getLogger("comfoair_mqtt_bridge")


def temperature(value: int) -> float:
    return value / 2.0 - 20.0


class Bridge:
    """Connects the ComfoAir TCP stream to MQTT discovery and commands."""

    def __init__(
        self, host: str, port: int, topic: str, loop: asyncio.AbstractEventLoop
    ) -> None:
        self.host = host
        self.port = port
        self.topic = topic.strip("/")
        self.loop = loop
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.write_lock = asyncio.Lock()
        self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="comfoair-bridge")
        self.state: dict[str, Any] = {}
        self.stop_event = asyncio.Event()

        mqtt_host = os.environ["MQTT_HOST"]
        mqtt_port = int(os.environ.get("MQTT_PORT", "1883"))
        mqtt_user = os.environ.get("MQTT_USER")
        mqtt_password = os.environ.get("MQTT_PASSWORD")
        if mqtt_user:
            self.mqtt.username_pw_set(mqtt_user, mqtt_password)
        self.mqtt.will_set(self._topic("status"), "offline", qos=1, retain=True)
        self.mqtt.on_connect = self._mqtt_connected
        self.mqtt.on_message = self._mqtt_message
        self.mqtt.reconnect_delay_set(2, 60)
        self.mqtt.connect_async(mqtt_host, mqtt_port, 60)
        self.mqtt.loop_start()

    def _topic(self, suffix: str) -> str:
        return f"{self.topic}/{suffix}"

    def _mqtt_connected(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            LOGGER.error("MQTT connection failed: %s", reason_code)
            return
        LOGGER.info("MQTT connected")
        client.subscribe(self._topic("set/#"), qos=1)
        self._publish_discovery()
        self._publish("status", "online")

    def _mqtt_message(self, client, userdata, message) -> None:
        command = message.topic.removeprefix(self._topic("set/"))
        value = message.payload.decode(errors="replace").strip()
        asyncio.run_coroutine_threadsafe(
            self._handle_command(command, value), self.loop
        )

    async def _handle_command(self, command: str, value: str) -> None:
        try:
            if command == "climate/mode":
                await self._send(p.CMD_SET_LEVEL, bytes([1 if value == "off" else 2]))
            elif command == "climate/fan_mode":
                levels = {"off": 1, "low": 2, "medium": 3, "high": 4, "auto": 0}
                await self._send(p.CMD_SET_LEVEL, bytes([levels[value]]))
            elif command == "climate/temperature":
                encoded = int((float(value) + 20) * 2)
                if not 12 <= float(value) <= 29:
                    raise ValueError("temperature must be between 12 and 29 °C")
                await self._send(p.CMD_SET_COMFORT_TEMPERATURE, bytes([encoded]))
            elif command == "filter_reset" and value.upper() in {"PRESS", "ON", "1"}:
                await self._send(p.CMD_RESET_AND_SELF_TEST, bytes([0, 0, 0, 1]))
            else:
                LOGGER.warning("Unsupported MQTT command: %s", command)
        except (KeyError, ValueError) as err:
            LOGGER.warning("Invalid MQTT command %s: %s", command, err)

    async def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                await self._connect()
                await self._poll_loop()
            except (ConnectionError, OSError, asyncio.TimeoutError) as err:
                LOGGER.warning(
                    "ComfoAir connection lost (%s): %s",
                    type(err).__name__,
                    err or "no error details",
                )
                await self._close()
                await asyncio.sleep(5)

    async def _connect(self) -> None:
        LOGGER.info("Connecting to ComfoAir at %s:%d", self.host, self.port)
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        await self._request(p.CMD_GET_FIRMWARE_VERSION, p.RES_GET_FIRMWARE_VERSION)
        LOGGER.info("ComfoAir connection established")

    async def _poll_loop(self) -> None:
        parser = p.FrameParser()
        assert self.reader is not None
        while not self.stop_event.is_set():
            await self._send(p.CMD_GET_STATUS)
            await self._send(p.CMD_GET_FAN_STATUS)
            await self._send(p.CMD_GET_VENTILATION_LEVEL)
            await self._send(p.CMD_GET_TEMPERATURES)
            await self._send(p.CMD_GET_FAULTS)
            try:
                chunk = await asyncio.wait_for(self.reader.read(256), timeout=5)
            except asyncio.TimeoutError:
                continue
            if not chunk:
                raise ConnectionError("ComfoAir closed the TCP connection")
            for frame in parser.feed(chunk):
                self._handle_frame(frame)
            await asyncio.sleep(5)

    async def _request(self, command: int, response: int) -> None:
        await self._send(command)
        if self.reader is None:
            raise ConnectionError("not connected")
        parser = p.FrameParser()
        deadline = self.loop.time() + 3
        while self.loop.time() < deadline:
            chunk = await asyncio.wait_for(
                self.reader.read(256), timeout=max(0.1, deadline - self.loop.time())
            )
            if not chunk:
                raise ConnectionError(
                    "ComfoAir closed the TCP connection before replying "
                    f"to command 0x{command:02X}"
                )
            for frame in parser.feed(chunk):
                if frame.msg_id == response:
                    self._handle_frame(frame)
                    return
        raise asyncio.TimeoutError(
            f"no response 0x{response:02X} to command 0x{command:02X} within 3 seconds"
        )

    async def _send(self, command: int, data: bytes = b"") -> None:
        async with self.write_lock:
            if self.writer is None:
                raise ConnectionError("not connected")
            self.writer.write(p.encode_frame(command, data))
            await self.writer.drain()

    def _handle_frame(self, frame: p.Frame) -> None:
        try:
            if frame.msg_id == p.RES_GET_VENTILATION_LEVEL and len(frame.data) >= 9:
                self.state["ventilation_level"] = frame.data[8] - 1
                self.state["level"] = frame.data[8]
            elif frame.msg_id == p.RES_GET_TEMPERATURES and len(frame.data) >= 6:
                self.state["target_temperature"] = temperature(frame.data[0])
                present = frame.data[5]
                if present & 1:
                    self.state["outside_air_temperature"] = temperature(frame.data[1])
                if present & 2:
                    self.state["supply_air_temperature"] = temperature(frame.data[2])
                if present & 4:
                    self.state["return_air_temperature"] = temperature(frame.data[3])
            elif frame.msg_id == p.RES_GET_FAULTS and len(frame.data) >= 9:
                self.state["filter_status"] = "Ok" if frame.data[8] == 0 else "Full"
            self._publish_state()
        except (IndexError, ValueError) as err:
            LOGGER.warning("Invalid ComfoAir frame 0x%02X: %s", frame.msg_id, err)

    def _publish_state(self) -> None:
        for key, value in self.state.items():
            self._publish(key, value)
        level = self.state.get("level")
        if level is not None:
            self._publish("climate/mode", "off" if level == 1 else "fan_only")
            self._publish("climate/fan_mode", {0: "auto", 1: "off", 2: "low", 3: "medium", 4: "high"}.get(level, "auto"))

    def _publish(self, suffix: str, value: Any) -> None:
        self.mqtt.publish(self._topic(suffix), str(value), qos=1, retain=True)

    def _publish_discovery(self) -> None:
        device = {
            "identifiers": ["comfoair_mqtt_bridge"],
            "name": "ComfoAir Standard 375",
            "manufacturer": "Zehnder",
            "model": "ComfoAir Standard 375",
        }
        availability = {
            "availability_topic": self._topic("status"),
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        climate = {
            "name": "Ventilation",
            "unique_id": "comfoair_mqtt_bridge_climate",
            "device": device,
            "mode_state_topic": self._topic("climate/mode"),
            "mode_command_topic": self._topic("set/climate/mode"),
            "modes": ["off", "fan_only"],
            "fan_mode_state_topic": self._topic("climate/fan_mode"),
            "fan_mode_command_topic": self._topic("set/climate/fan_mode"),
            "fan_modes": ["off", "low", "medium", "high", "auto"],
            "temperature_state_topic": self._topic("target_temperature"),
            "temperature_command_topic": self._topic("set/climate/temperature"),
            "min_temp": 12,
            "max_temp": 29,
            "temp_step": 0.5,
            "temperature_unit": "C",
            **availability,
        }
        self.mqtt.publish(
            "homeassistant/climate/comfoair_mqtt_bridge/config",
            json.dumps(climate, separators=(",", ":")),
            qos=1,
            retain=True,
        )
        for key in ("ventilation_level", "supply_air_temperature", "return_air_temperature", "outside_air_temperature", "filter_status"):
            config = {
                "name": key.replace("_", " ").title(),
                "unique_id": f"comfoair_mqtt_bridge_{key}",
                "state_topic": self._topic(key),
                "device": device,
                **availability,
            }
            if key.endswith("temperature"):
                config.update({"device_class": "temperature", "unit_of_measurement": "°C"})
            self.mqtt.publish(
                f"homeassistant/sensor/comfoair_mqtt_bridge/{key}/config",
                json.dumps(config, separators=(",", ":")),
                qos=1,
                retain=True,
            )

    async def _close(self) -> None:
        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
        self.reader = None
        self.writer = None

    async def shutdown(self) -> None:
        self.stop_event.set()
        self._publish("status", "offline")
        await self._close()
        self.mqtt.loop_stop()
        self.mqtt.disconnect()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument("--options-file")
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    loop = asyncio.get_running_loop()
    bridge = Bridge(args.host, args.port, args.topic, loop)
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, bridge.stop_event.set)
    try:
        await bridge.run()
    finally:
        await bridge.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
