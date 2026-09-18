"""Config flow for the ComfoAir TCP/MQTT bridge."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT

from . import protocol as p
from .const import DEFAULT_NAME, DOMAIN
from .transport import ComfoAirTransport

_LOGGER = logging.getLogger(__name__)
CONF_MQTT_TOPIC = "mqtt_topic"


class ComfoAirConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup of a Waveshare-connected ComfoAir."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow for an existing bridge."""
        return ComfoAirOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            topic = user_input[CONF_MQTT_TOPIC].strip().strip("/")
            error = await self._probe(host, port)
            if error is None:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input.get("name", DEFAULT_NAME).strip() or DEFAULT_NAME,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_MQTT_TOPIC: topic,
                    },
                )
            errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required("name", default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=8899): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_MQTT_TOPIC, default="comfoair"): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _probe(self, host: str, port: int) -> str | None:
        transport = ComfoAirTransport(host, port, self.hass)
        try:
            await transport.connect()
            await transport.request(
                p.CMD_GET_FIRMWARE_VERSION,
                p.RES_GET_FIRMWARE_VERSION,
                timeout=3.0,
            )
        except (ConnectionError, OSError, TimeoutError) as err:
            _LOGGER.debug("ComfoAir probe failed for %s:%d: %s", host, port, err)
            return "cannot_connect"
        finally:
            await transport.disconnect()
        return None


class ComfoAirOptionsFlow(OptionsFlow):
    """Allow changing the Waveshare and MQTT connection settings."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and validate the connection settings."""
        errors: dict[str, str] = {}
        current = self.config_entry.data
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            topic = user_input[CONF_MQTT_TOPIC].strip().strip("/")
            error = await self._probe(host, port)
            if error is None:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data={
                        **self.config_entry.data,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_MQTT_TOPIC: topic,
                    },
                )
                self.hass.config_entries.async_schedule_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(
                    title="",
                    data={},
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=current.get(CONF_HOST, "")
                    ): str,
                    vol.Required(
                        CONF_PORT, default=current.get(CONF_PORT, 8899)
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required(
                        CONF_MQTT_TOPIC,
                        default=current.get(CONF_MQTT_TOPIC, "comfoair"),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _probe(self, host: str, port: int) -> str | None:
        """Verify the adapter and ventilation unit before saving."""
        transport = ComfoAirTransport(host, port, self.hass)
        try:
            await transport.connect()
            await transport.request(
                p.CMD_GET_FIRMWARE_VERSION,
                p.RES_GET_FIRMWARE_VERSION,
                timeout=3.0,
            )
        except (ConnectionError, OSError, TimeoutError) as err:
            _LOGGER.debug("ComfoAir options probe failed for %s:%d: %s", host, port, err)
            return "cannot_connect"
        finally:
            await transport.disconnect()
        return None
