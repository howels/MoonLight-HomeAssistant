"""System health: whether each MoonLight endpoint's WebSocket is up."""

from __future__ import annotations

from homeassistant.components import system_health
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .const import DOMAIN, MOONLIGHT_API_VERSION


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Register the health callback."""
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, str]:
    """One row for the integration version, and one row per loaded device."""
    integration = await async_get_integration(hass, DOMAIN)
    info: dict[str, str] = {
        "version": str(integration.version),
        "api_version": MOONLIGHT_API_VERSION,
    }
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            info[entry.title] = "not loaded"
            continue
        coordinator = entry.runtime_data
        info[f"{entry.title} ({coordinator.host}:{coordinator.port})"] = (
            "ok" if coordinator.connected else "websocket down"
        )
    return info
