"""Config entry setup. One entry is one MoonLight endpoint."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import AnyDeviceEntry

from .const import DOMAIN, PLATFORMS
from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_CARDS = "cards"
_CARD_URL = "/moonlight/moonlight-cards.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the actions and the Lovelace cards."""
    async_setup_services(hass)
    if not await _async_register_cards(hass):
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_register_on_start)
    return True


async def _async_register_on_start(event: Event) -> None:
    """The HTTP server and the frontend are up, so the cards can be served."""
    await _async_register_cards(event.hass)


async def _async_register_cards(hass: HomeAssistant) -> bool:
    """Serve the Basic, Pro and Effects cards, and ask the frontend to load them.

    False when the HTTP server or the frontend is not ready yet.
    """
    store = hass.data.setdefault(DOMAIN, {})
    if store.get(_CARDS):
        return True
    if hass.http is None or DATA_EXTRA_MODULE_URL not in hass.data:
        return False
    path = Path(__file__).parent / "www" / "moonlight-cards.js"
    await hass.http.async_register_static_paths([StaticPathConfig(_CARD_URL, str(path), False)])
    add_extra_js_url(hass, _CARD_URL)
    store[_CARDS] = True
    return True


async def _async_reload(hass: HomeAssistant, entry: MoonLightConfigEntry) -> None:
    """Options change which pages exist, so the entry loads again."""
    await hass.config_entries.async_reload(entry.entry_id)


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
    entry.async_on_unload(entry.add_update_listener(_async_reload))
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
