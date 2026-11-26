"""The MoonLight integration: a MoonLight device in Home Assistant, over MoonLight's own API.

This first version adds the device to the device registry and creates no entities yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MoonLightError, fetch_system
from .const import DOMAIN, MANUFACTURER

# Entity platforms (light, select, number, switch, sensor) are added here as they are written.
PLATFORMS: list[Platform] = []


@dataclass
class MoonLightData:
    """What a config entry holds while it is loaded."""

    host: str
    port: int
    system: dict[str, Any]


type MoonLightConfigEntry = ConfigEntry[MoonLightData]


async def async_setup_entry(hass: HomeAssistant, entry: MoonLightConfigEntry) -> bool:
    """Read the device once and register it; retried by Home Assistant while it is offline."""
    host, port = entry.data[CONF_HOST], entry.data[CONF_PORT]
    try:
        system = await fetch_system(async_get_clientsession(hass), host, port)
    except MoonLightError as err:
        raise ConfigEntryNotReady(str(err)) from err

    mac = dr.format_mac(system["mac"])
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        connections={(dr.CONNECTION_NETWORK_MAC, mac)},
        identifiers={(DOMAIN, mac)},
        manufacturer=MANUFACTURER,
        model=system.get("board"),
        name=system.get("name"),
        sw_version=system.get("version"),
        configuration_url=f"http://{host}:{port}/",
    )
    entry.runtime_data = MoonLightData(host=host, port=port, system=system)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MoonLightConfigEntry) -> bool:
    """Unload the entry's platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
