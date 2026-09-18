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
        self.features: dict[str, bool] = {}
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
                temperature = float(value)
                if not 12 <= temperature <= 29:
                    raise ValueError("temperature must be between 12 and 29 °C")
                await self._send(p.CMD_SET_COMFORT_TEMPERATURE, bytes([p.temp_to_byte(temperature)]))
            elif command.startswith("fan/"):
                await self._set_fan_percentage(command.removeprefix("fan/"), value)
            elif command.startswith("time_delay/"):
                await self._set_time_delay(command.removeprefix("time_delay/"), value)
            elif command.startswith("ewt_postheating/"):
                await self._set_ewt_postheating(command.removeprefix("ewt_postheating/"), value)
            elif command == "filter_reset" and value.upper() in {"PRESS", "ON", "1"}:
                await self._send(p.CMD_RESET_AND_SELF_TEST, bytes([0, 0, 0, 1]))
            elif command == "error_reset" and value.upper() in {"PRESS", "ON", "1"}:
                await self._send(p.CMD_RESET_AND_SELF_TEST, bytes([1, 0, 0, 0]))
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
            await self._send(p.CMD_GET_OPERATION_HOURS)
            await self._send(p.CMD_GET_TIME_DELAY)
            await self._send(p.CMD_GET_VALVE_STATUS)
            await self._send(p.CMD_GET_INPUTS)
            await self._send(p.CMD_GET_ANALOG_INPUTS)
            if self.features.get("bypass"):
                await self._send(p.CMD_GET_BYPASS_CONTROL_STATUS)
            if self.features.get("preheating"):
                await self._send(p.CMD_GET_PREHEATING_STATUS)
            if self.features.get("enthalpy"):
                await self._send(p.CMD_GET_SENSOR_DATA)
            if self.features.get("ewt") or self.features.get("postheating"):
                await self._send(p.CMD_GET_EWT_POSTHEATING)
            try:
                chunk = await asyncio.wait_for(self.reader.read(256), timeout=5)
            except asyncio.TimeoutError:
                continue
            if not chunk:
                raise ConnectionError("ComfoAir closed the TCP connection")
            LOGGER.debug("RX %d bytes: %s", len(chunk), chunk.hex(" "))
            for frame in parser.feed(chunk):
                LOGGER.debug(
                    "RX frame 0x%02X (%d bytes): %s",
                    frame.msg_id,
                    len(frame.data),
                    frame.data.hex(" "),
                )
                self._handle_frame(frame)
            await asyncio.sleep(5)

    async def _request(self, command: int, response: int) -> None:
        await self._send(command)
        if self.reader is None:
            raise ConnectionError("not connected")
        parser = p.FrameParser()
        deadline = self.loop.time() + 3
        while self.loop.time() < deadline:
            remaining = max(0.1, deadline - self.loop.time())
            try:
                chunk = await asyncio.wait_for(self.reader.read(256), timeout=remaining)
            except asyncio.TimeoutError as err:
                raise asyncio.TimeoutError(
                    f"no response 0x{response:02X} to command "
                    f"0x{command:02X} within 3 seconds"
                ) from err
            if not chunk:
                raise ConnectionError(
                    "ComfoAir closed the TCP connection before replying "
                    f"to command 0x{command:02X}"
                )
            LOGGER.debug("RX %d bytes while waiting for 0x%02X: %s", len(chunk), response, chunk.hex(" "))
            for frame in parser.feed(chunk):
                LOGGER.debug(
                    "RX frame 0x%02X (%d bytes): %s",
                    frame.msg_id,
                    len(frame.data),
                    frame.data.hex(" "),
                )
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
            wire_frame = p.encode_frame(command, data)
            LOGGER.debug("TX command 0x%02X: %s", command, wire_frame.hex(" "))
            self.writer.write(wire_frame)
            await self.writer.drain()

    def _handle_frame(self, frame: p.Frame) -> None:
        try:
            if frame.msg_id == p.RES_GET_VENTILATION_LEVEL and len(frame.data) >= 9:
                keys = ("return_air_level_absent", "return_air_level_low", "return_air_level_medium",
                        "supply_air_level_absent", "supply_air_level_low", "supply_air_level_medium",
                        "return_air_level", "supply_air_level")
                self.state.update(dict(zip(keys, frame.data[:8])))
                self.state.update({"ventilation_level": frame.data[8] - 1, "level": frame.data[8]})
                if len(frame.data) >= 12:
                    self.state.update({"supply_fan_active": frame.data[9] == 1,
                                       "return_air_level_high": frame.data[10],
                                       "supply_air_level_high": frame.data[11]})
            elif frame.msg_id == p.RES_GET_TEMPERATURES and len(frame.data) >= 6:
                self.state["target_temperature"] = p.byte_to_temp(frame.data[0])
                present = frame.data[5]
                if present & 1:
                    self.state["outside_air_temperature"] = p.byte_to_temp(frame.data[1])
                if present & 2:
                    self.state["supply_air_temperature"] = p.byte_to_temp(frame.data[2])
                if present & 4:
                    self.state["return_air_temperature"] = p.byte_to_temp(frame.data[3])
                    self.state["current_temperature"] = p.byte_to_temp(frame.data[3])
                if present & 8 and len(frame.data) > 4:
                    self.state["exhaust_air_temperature"] = p.byte_to_temp(frame.data[4])
                for bit, key in ((16, "ewt_temperature"), (32, "reheating_temperature"), (64, "kitchen_hood_temperature")):
                    if present & bit and len(frame.data) > {16: 6, 32: 7, 64: 8}[bit]:
                        self.state[key] = p.byte_to_temp(frame.data[{16: 6, 32: 7, 64: 8}[bit]])
            elif frame.msg_id == p.RES_GET_STATUS:
                self.features.update({
                    "preheating": bool(frame.data[0]) if len(frame.data) > 0 else False,
                    "bypass": bool(frame.data[1]) if len(frame.data) > 1 else False,
                    "postheating": bool(len(frame.data) > 4 and frame.data[4] & 4),
                    "enthalpy": bool(len(frame.data) > 9 and frame.data[9]),
                    "ewt": bool(len(frame.data) > 10 and frame.data[10]),
                })
            elif frame.msg_id == p.RES_GET_FAN_STATUS and len(frame.data) >= 6:
                self.state.update({
                    "supply_fan_speed": frame.data[0],
                    "exhaust_fan_speed": frame.data[1],
                    "supply_fan_speed_rpm": p.rpm_from_period(p.u16(frame.data, 2)),
                    "exhaust_fan_speed_rpm": p.rpm_from_period(p.u16(frame.data, 4)),
                })
            elif frame.msg_id == p.RES_GET_VENTILATION_LEVEL and len(frame.data) >= 12:
                keys = ("return_air_level_absent", "return_air_level_low", "return_air_level_medium",
                        "supply_air_level_absent", "supply_air_level_low", "supply_air_level_medium",
                        "return_air_level", "supply_air_level")
                self.state.update(dict(zip(keys, frame.data[:8])))
                self.state.update({"ventilation_level": frame.data[8] - 1, "level": frame.data[8],
                                   "supply_fan_active": frame.data[9] == 1,
                                   "return_air_level_high": frame.data[10], "supply_air_level_high": frame.data[11]})
            elif frame.msg_id == p.RES_GET_OPERATION_HOURS and len(frame.data) >= 19:
                self.state.update({"level0_hours": p.u24(frame.data, 0), "level1_hours": p.u24(frame.data, 3),
                    "level2_hours": p.u24(frame.data, 6), "frost_protection_hours": p.u16(frame.data, 9),
                    "preheating_hours": p.u16(frame.data, 11), "bypass_open_hours": p.u16(frame.data, 13),
                    "filter_hours": p.u16(frame.data, 15), "level3_hours": p.u24(frame.data, 17)})
            elif frame.msg_id == p.RES_GET_TIME_DELAY and len(frame.data) >= 8:
                self.state.update(dict(zip(("bathroom_switch_on_delay_minutes", "bathroom_switch_off_delay_minutes",
                    "l1_switch_off_delay_minutes", "boost_ventilation_minutes", "filter_warning_weeks",
                    "rf_high_time_short_minutes", "rf_high_time_long_minutes", "extractor_hood_switch_off_delay_minutes"),
                    frame.data[:8])))
            elif frame.msg_id == p.RES_GET_VALVE_STATUS and len(frame.data) >= 4:
                self.state.update({"bypass_valve": frame.data[0], "bypass_valve_open": frame.data[0] != 0,
                    "preheating_valve_open": frame.data[1] == 1, "motor_current_bypass": frame.data[2],
                    "motor_current_preheating": frame.data[3]})
            elif frame.msg_id == p.RES_GET_INPUTS and len(frame.data) >= 2:
                self.state.update({"step_switch_l1": bool(frame.data[0] & 1), "step_switch_l2": bool(frame.data[0] & 2),
                    "bathroom_switch": bool(frame.data[1] & 1), "kitchen_hood_switch": bool(frame.data[1] & 2),
                    "external_filter_switch": bool(frame.data[1] & 4), "heat_recovery_switch": bool(frame.data[1] & 8),
                    "bathroom_switch_2": bool(frame.data[1] & 16)})
            elif frame.msg_id == p.RES_GET_ANALOG_INPUTS and len(frame.data) >= 4:
                self.state.update({f"analog_input_{i + 1}": round(v * 10 / 255, 2) for i, v in enumerate(frame.data[:4])})
            elif frame.msg_id == p.RES_GET_BYPASS_CONTROL_STATUS:
                for i, key in ((2, "bypass_factor"), (3, "bypass_step"), (4, "bypass_correction")):
                    if len(frame.data) > i: self.state[key] = frame.data[i]
                if len(frame.data) > 6: self.state["summer_mode"] = frame.data[6] != 0
            elif frame.msg_id == p.RES_GET_PREHEATING_STATUS and len(frame.data) >= 6:
                self.state.update({"preheating_valve": {0: "Closed", 1: "Open"}.get(frame.data[0], "Unknown"),
                    "frost_protection_active": frame.data[1] != 0, "preheating_state": frame.data[2] != 0,
                    "frost_protection_minutes": p.u16(frame.data, 3), "frost_protection_level": frame.data[5]})
            elif frame.msg_id == p.RES_GET_SENSOR_DATA and frame.data:
                self.state["enthalpy_temperature"] = p.byte_to_temp(frame.data[0])
            elif frame.msg_id == p.RES_GET_EWT_POSTHEATING and len(frame.data) >= 7:
                self.state.update({"ewt_low_temperature": p.byte_to_temp(frame.data[0]), "ewt_high_temperature": p.byte_to_temp(frame.data[1]),
                    "ewt_speed_up": frame.data[2], "kitchen_hood_speed_up": frame.data[3], "postheating_power": frame.data[4],
                    "postheating_power_i": frame.data[5], "postheating_target_temperature": p.byte_to_temp(frame.data[6])})
            elif frame.msg_id == p.RES_GET_FAULTS and len(frame.data) >= 9:
                self.state["filter_status"] = "Ok" if frame.data[8] == 0 else "Full"
                if len(frame.data) >= 17:
                    self.state.update({
                        "current_errors": self._format_errors(frame.data[0], frame.data[13], frame.data[1], frame.data[9]),
                        "last_errors": self._format_errors(frame.data[2], frame.data[14], frame.data[3], frame.data[10]),
                        "second_last_errors": self._format_errors(frame.data[4], frame.data[15], frame.data[5], frame.data[11]),
                        "third_last_errors": self._format_errors(frame.data[6], frame.data[16], frame.data[7], frame.data[12]),
                    })
            self._publish_state()
        except (IndexError, ValueError) as err:
            LOGGER.warning("Invalid ComfoAir frame 0x%02X: %s", frame.msg_id, err)

    @staticmethod
    def _format_errors(a_low: int, a_high: int, e: int, ea: int) -> str:
        codes = [f"A{i + 1}" for i in range(8) if a_low & (1 << i)]
        codes.extend(f"A{9 + i}" for i in range(7) if a_high & (1 << i))
        codes.extend(f"E{i + 1}" for i in range(8) if e & (1 << i))
        codes.extend(f"EA{i + 1}" for i in range(8) if ea & (1 << i))
        return ", ".join(codes) if codes else "OK"

    def _publish_state(self) -> None:
        for key, value in self.state.items():
            self._publish(key, value)
        level = self.state.get("level")
        if level is not None:
            self._publish("climate/mode", "off" if level == 1 else "fan_only")
            self._publish("climate/fan_mode", {0: "auto", 1: "off", 2: "low", 3: "medium", 4: "high"}.get(level, "auto"))
            if "current_temperature" in self.state:
                self._publish("climate/current_temperature", self.state["current_temperature"])

    def _publish(self, suffix: str, value: Any) -> None:
        self.mqtt.publish(self._topic(suffix), str(value), qos=1, retain=True)

    async def _set_fan_percentage(self, key: str, value: str) -> None:
        keys = ("return_air_level_absent", "return_air_level_low", "return_air_level_medium",
                "supply_air_level_absent", "supply_air_level_low", "supply_air_level_medium",
                "return_air_level_high", "supply_air_level_high")
        if key not in keys:
            raise ValueError(f"unknown fan percentage: {key}")
        self.state[key] = max(15, min(95, int(float(value))))
        await self._send(p.CMD_SET_VENTILATION_LEVEL, bytes([self.state[k] for k in keys] + [0]))

    async def _set_time_delay(self, key: str, value: str) -> None:
        keys = ("bathroom_switch_on_delay_minutes", "bathroom_switch_off_delay_minutes",
                "l1_switch_off_delay_minutes", "boost_ventilation_minutes", "filter_warning_weeks",
                "rf_high_time_short_minutes", "rf_high_time_long_minutes", "extractor_hood_switch_off_delay_minutes")
        if key not in keys:
            raise ValueError(f"unknown time delay: {key}")
        self.state[key] = max(0, min(255, int(float(value))))
        await self._send(p.CMD_SET_TIME_DELAY, bytes(self.state[k] for k in keys))

    async def _set_ewt_postheating(self, key: str, value: str) -> None:
        keys = ("ewt_low_temperature", "ewt_high_temperature", "ewt_speed_up",
                "kitchen_hood_speed_up", "postheating_target_temperature")
        if key not in keys:
            raise ValueError(f"unknown EWT/postheating value: {key}")
        numeric = float(value)
        self.state[key] = numeric
        data = []
        for item in keys:
            item_value = float(self.state[item])
            data.append(p.temp_to_byte(item_value) if "temperature" in item else max(0, min(100, int(item_value))))
        await self._send(p.CMD_SET_EWT_POSTHEATING, bytes(data))

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
            "current_temperature_topic": self._topic("current_temperature"),
            "temperature_command_topic": self._topic("set/climate/temperature"),
            "min_temp": 12,
            "max_temp": 29,
            "temp_step": 0.5,
            "precision": 0.5,
            "temperature_unit": "C",
            **availability,
        }
        self.mqtt.publish(
            "homeassistant/climate/comfoair_mqtt_bridge/config",
            json.dumps(climate, separators=(",", ":")),
            qos=1,
            retain=True,
        )
        for key, name in (("filter_reset", "Reset filter"), ("error_reset", "Reset errors")):
            self._discovery("button", key, {"name": name, "command_topic": self._topic(f"set/{key}"), "payload_press": "PRESS", "device": device, **availability})
        temp_keys = {"outside_air_temperature", "supply_air_temperature", "return_air_temperature", "exhaust_air_temperature",
                     "ewt_temperature", "reheating_temperature", "kitchen_hood_temperature", "enthalpy_temperature"}
        pct_keys = {"supply_fan_speed", "exhaust_fan_speed", "return_air_level", "supply_air_level"}
        rpm_keys = {"supply_fan_speed_rpm", "exhaust_fan_speed_rpm"}
        hours_keys = {"level0_hours", "level1_hours", "level2_hours", "level3_hours", "frost_protection_hours", "preheating_hours", "bypass_open_hours", "filter_hours"}
        number_keys = {"return_air_level_absent", "return_air_level_low", "return_air_level_medium", "return_air_level_high",
                       "supply_air_level_absent", "supply_air_level_low", "supply_air_level_medium", "supply_air_level_high",
                       "bathroom_switch_on_delay_minutes", "bathroom_switch_off_delay_minutes", "l1_switch_off_delay_minutes",
                       "boost_ventilation_minutes", "filter_warning_weeks", "rf_high_time_short_minutes", "rf_high_time_long_minutes",
                       "extractor_hood_switch_off_delay_minutes", "ewt_low_temperature", "ewt_high_temperature", "ewt_speed_up",
                       "kitchen_hood_speed_up", "postheating_target_temperature"}
        sensor_keys = {"supply_fan_speed", "exhaust_fan_speed", "supply_fan_speed_rpm", "exhaust_fan_speed_rpm",
                       "ventilation_level", "return_air_level", "supply_air_level", "outside_air_temperature",
                       "supply_air_temperature", "return_air_temperature", "exhaust_air_temperature", "filter_status",
                       "current_errors", "last_errors", "second_last_errors", "third_last_errors", "bypass_valve",
                       "bypass_factor", "bypass_step", "bypass_correction", "bypass_open_hours", "motor_current_bypass",
                       "motor_current_preheating", "preheating_hours", "frost_protection_minutes", "preheating_valve",
                       "frost_protection_level", "enthalpy_temperature", "ewt_temperature", "reheating_temperature",
                       "kitchen_hood_temperature", "analog_input_1", "analog_input_2", "analog_input_3", "analog_input_4",
                       "postheating_power", "postheating_power_i"}
        for key in set(self.state) | temp_keys | pct_keys | rpm_keys | hours_keys | sensor_keys:
            if key in number_keys:
                continue
            config = {"name": key.replace("_", " ").title(), "unique_id": f"comfoair_mqtt_bridge_{key}", "state_topic": self._topic(key), "device": device, **availability}
            if key in temp_keys: config.update({"device_class": "temperature", "unit_of_measurement": "°C"})
            elif key in pct_keys: config.update({"unit_of_measurement": "%"})
            elif key in rpm_keys: config.update({"unit_of_measurement": "rpm"})
            elif key in hours_keys: config.update({"unit_of_measurement": "h", "device_class": "duration"})
            self._discovery("sensor", key, config)
        for key in ("supply_fan_active", "frost_protection_active", "summer_mode", "bypass_valve_open", "preheating_state",
                    "step_switch_l1", "step_switch_l2", "bathroom_switch", "bathroom_switch_2", "external_filter_switch",
                    "heat_recovery_switch", "kitchen_hood_switch", "preheating_valve_open"):
            self._discovery("binary_sensor", key, {"name": key.replace("_", " ").title(), "unique_id": f"comfoair_mqtt_bridge_{key}", "state_topic": self._topic(key), "payload_on": "True", "payload_off": "False", "device": device, **availability})
        for key in sorted(number_keys):
            command_group = "fan" if "level" in key else "time_delay" if key.endswith("minutes") or key == "filter_warning_weeks" else "ewt_postheating"
            config = {"name": key.replace("_", " ").title(), "unique_id": f"comfoair_mqtt_bridge_{key}", "state_topic": self._topic(key), "command_topic": self._topic(f"set/{command_group}/{key}"), "device": device, **availability, "mode": "box"}
            if "temperature" in key: config.update({"unit_of_measurement": "°C", "min": -20, "max": 40, "step": 0.5})
            elif "level" in key or "speed_up" in key: config.update({"unit_of_measurement": "%", "min": 0 if "speed_up" in key else 15, "max": 100 if "speed_up" in key else 95, "step": 1})
            elif key == "filter_warning_weeks": config.update({"unit_of_measurement": "weeks", "min": 1, "max": 52, "step": 1})
            else: config.update({"unit_of_measurement": "min", "min": 0, "max": 120, "step": 1})
            self._discovery("number", key, config)

    def _discovery(self, component: str, key: str, config: dict[str, Any]) -> None:
        self.mqtt.publish(f"homeassistant/{component}/comfoair_mqtt_bridge/{key}/config", json.dumps(config, separators=(",", ":")), qos=1, retain=True)

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
