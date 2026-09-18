"""ComfoAir ventilation integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import DEFAULT_NAME, DOMAIN
from .coordinator import ComfoAirCoordinator
from .transport import ComfoAirTransport
from .mqtt_bridge import ComfoAirMqttBridge

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
]


_UNIQUE_ID_MIGRATIONS = {
    # Renamed for supply/exhaust terminology ("intake" fan is supply fan).
    "intake_fan_speed": "supply_fan_speed",
    "intake_fan_speed_rpm": "supply_fan_speed_rpm",
    "return_fan_speed": "exhaust_fan_speed",
    "return_fan_speed_rpm": "exhaust_fan_speed_rpm",
}


def _migrate_unique_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rename entity-registry unique IDs for keys that have been renamed."""
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    for old_suffix, new_suffix in _UNIQUE_ID_MIGRATIONS.items():
        old_unique_id = f"{prefix}{old_suffix}"
        new_unique_id = f"{prefix}{new_suffix}"
        entity_id = registry.async_get_entity_id(Platform.SENSOR, DOMAIN, old_unique_id)
        if entity_id is None:
            continue
        if registry.async_get_entity_id(Platform.SENSOR, DOMAIN, new_unique_id):
            # New entity already exists; drop the stale one to avoid a clash.
            _LOGGER.debug("Removing stale entity %s during migration", entity_id)
            registry.async_remove(entity_id)
            continue
        _LOGGER.info("Migrating unique_id %s -> %s", old_unique_id, new_unique_id)
        registry.async_update_entity(entity_id, new_unique_id=new_unique_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ComfoAir from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    name = entry.title or DEFAULT_NAME

    _LOGGER.debug("Setting up ComfoAir entry %s on %s:%s", name, host, port)

    _migrate_unique_ids(hass, entry)

    transport = ComfoAirTransport(host=host, port=port, hass=hass)
    coordinator = ComfoAirCoordinator(hass, entry, transport, device_name=name)

    try:
        await transport.connect()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("ComfoAir transport.connect to %s failed: %r", port, err)
        raise ConfigEntryNotReady(f"cannot open {port}: {err}") from err

    try:
        await coordinator.async_probe()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("ComfoAir probe on %s failed: %r", port, err)
        await transport.disconnect()
        raise ConfigEntryNotReady(f"probe failed: {err}") from err

    _LOGGER.debug(
        "ComfoAir probe ok: firmware=%s v%s, features=%s",
        coordinator.firmware_name,
        coordinator.firmware_version,
        {k: v for k, v in coordinator.features.items() if v},
    )

    await coordinator.async_config_entry_first_refresh()

    bridge = ComfoAirMqttBridge(
        hass,
        coordinator,
        entry.data.get("mqtt_topic", "comfoair"),
    )
    await bridge.async_start()
    coordinator.mqtt_bridge = bridge
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = hass.data.get(DOMAIN, {}).pop(
        entry.entry_id, None
    )
    if coordinator is not None:
        await coordinator.mqtt_bridge.async_stop()
        await coordinator.transport.disconnect()
    return unloaded
