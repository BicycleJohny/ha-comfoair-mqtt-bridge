"""MQTT discovery and command bridge for the ComfoAir coordinator."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ComfoAirMqttBridge:
    """Publish a small, stable MQTT API for Home Assistant and other clients."""

    def __init__(self, hass: HomeAssistant, coordinator, topic: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.topic = topic.rstrip("/")
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def status_topic(self) -> str:
        return f"{self.topic}/status"

    async def async_start(self) -> None:
        await self._publish_discovery()
        self._unsubscribers.append(
            await mqtt.async_subscribe(
                self.hass, f"{self.topic}/set/#", self._async_command, qos=1
            )
        )
        self.coordinator.async_add_listener(self._coordinator_updated)
        await self.async_publish_state()

    async def async_stop(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self.coordinator.remove_listener(self._coordinator_updated)
        await mqtt.async_publish(
            self.hass, self.status_topic, "offline", qos=1, retain=True
        )

    @callback
    def _coordinator_updated(self) -> None:
        self.hass.async_create_task(self.async_publish_state())

    async def async_publish_state(self) -> None:
        state = self.coordinator.data
        if not state:
            return
        payloads = {
            "climate/mode": "off"
            if state.get("current_level_raw") == 1
            else "fan_only",
            "climate/fan_mode": self._fan_mode(state.get("current_level_raw")),
            "climate/temperature": state.get("target_temperature"),
            "climate/current_temperature": state.get("current_temperature"),
            "ventilation_level": state.get("ventilation_level"),
            "supply_air_temperature": state.get("supply_air_temperature"),
            "return_air_temperature": state.get("return_air_temperature"),
            "outside_air_temperature": state.get("outside_air_temperature"),
            "filter_status": state.get("filter_status"),
        }
        await self._publish("status", "online")
        for suffix, value in payloads.items():
            if value is not None:
                await self._publish(suffix, value)

    async def _publish_discovery(self) -> None:
        device = {
            "identifiers": [f"{DOMAIN}_{self.coordinator.entry.entry_id}"],
            "name": self.coordinator.device_name,
            "manufacturer": "Zehnder",
            "model": self.coordinator.firmware_name or "ComfoAir Standard 375",
        }
        availability = {
            "availability_topic": self.status_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        climate = {
            "name": "Ventilation",
            "unique_id": f"{self.topic}_climate",
            "device": device,
            "mode_state_topic": f"{self.topic}/climate/mode",
            "mode_command_topic": f"{self.topic}/set/climate/mode",
            "modes": ["off", "fan_only"],
            "fan_mode_state_topic": f"{self.topic}/climate/fan_mode",
            "fan_mode_command_topic": f"{self.topic}/set/climate/fan_mode",
            "fan_modes": ["off", "low", "medium", "high", "auto"],
            "temperature_state_topic": f"{self.topic}/climate/temperature",
            "current_temperature_topic": f"{self.topic}/climate/current_temperature",
            "temperature_command_topic": f"{self.topic}/set/climate/temperature",
            "min_temp": 12,
            "max_temp": 29,
            "temp_step": 0.5,
            "temperature_unit": "C",
            **availability,
        }
        await self._discovery("climate", climate)
        sensors = {
            "ventilation_level": ("Ventilation level", None),
            "supply_air_temperature": ("Supply air temperature", "°C"),
            "return_air_temperature": ("Return air temperature", "°C"),
            "outside_air_temperature": ("Outside air temperature", "°C"),
            "filter_status": ("Filter status", None),
        }
        for key, (name, unit) in sensors.items():
            config: dict[str, Any] = {
                "name": name,
                "unique_id": f"{self.topic}_{key}",
                "state_topic": f"{self.topic}/{key}",
                "device": device,
                **availability,
            }
            if unit:
                config["unit_of_measurement"] = unit
                config["device_class"] = "temperature"
            await self._discovery("sensor", config, key)

    async def _discovery(
        self, component: str, config: dict[str, Any], object_id: str = "main"
    ) -> None:
        topic = f"homeassistant/{component}/{self.topic.replace('/', '_')}/{object_id}/config"
        await mqtt.async_publish(
            self.hass, topic, json.dumps(config, separators=(",", ":")), qos=1, retain=True
        )

    async def _publish(self, suffix: str, value: Any) -> None:
        await mqtt.async_publish(
            self.hass,
            f"{self.topic}/{suffix}",
            json.dumps(value) if isinstance(value, (dict, list)) else str(value),
            qos=1,
            retain=True,
        )

    async def _async_command(self, message) -> None:
        suffix = message.topic.removeprefix(f"{self.topic}/set/")
        value = message.payload.decode().strip()
        try:
            if suffix == "climate/mode":
                await self.coordinator.async_set_level(1 if value == "off" else 2)
            elif suffix == "climate/fan_mode":
                levels = {"off": 1, "low": 2, "medium": 3, "high": 4, "auto": 0}
                await self.coordinator.async_set_level(levels[value])
            elif suffix == "climate/temperature":
                await self.coordinator.async_set_comfort_temperature(float(value))
            elif suffix == "filter_reset" and value.upper() in {"PRESS", "ON", "1"}:
                await self.coordinator.async_reset_filter()
        except (KeyError, ValueError) as err:
            _LOGGER.warning("Invalid MQTT command %s: %s", suffix, err)
