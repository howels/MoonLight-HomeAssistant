"""Config entry setup. One entry is one MoonLight endpoint."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import AnyDeviceEntry

from .const import DOMAIN, PLATFORMS
from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .services import async_setup_services


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the actions once. They target a device of this integration."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MoonLightConfigEntry) -> bool:
    """Read the tree, register the devices, and open the WebSocket.

    `async_config_entry_first_refresh` raises `ConfigEntryNotReady` when the host does not
    answer, and Home Assistant retries the entry.
    """
    coordinator = MoonLightCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    coordinator.async_sync_devices()
    coordinator.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MoonLightConfigEntry) -> bool:
    """Close the socket and unload the platforms."""
    await entry.runtime_data.async_shutdown()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: MoonLightConfigEntry, device_entry: AnyDeviceEntry
) -> bool:
    """Allow removing a side-nav device whose root module is gone. The endpoint stays."""
    coordinator = entry.runtime_data
    prefix = f"{coordinator.mac}_"
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == coordinator.mac:
            return False
        if identifier.startswith(prefix):
            return identifier.removeprefix(prefix) not in coordinator.data.modules
    return False
