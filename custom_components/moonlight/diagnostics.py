"""Diagnostics for one MoonLight entry.

The download is for a bug report. It names the modules and the control types.
Control values are left out.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import MOONLIGHT_API_VERSION, NAV_GROUPS
from .coordinator import MoonLightConfigEntry
from .models import nav_roots


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MoonLightConfigEntry
) -> dict[str, Any]:
    """Return the tree shape and the last socket error."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "title": entry.title,
            "host": coordinator.host,
            "port": coordinator.port,
            "unique_id": entry.unique_id,
        },
        "api_version": MOONLIGHT_API_VERSION,
        "connected": data.connected,
        "last_error": data.last_error,
        "system": {
            key: data.system.get(key)
            for key in ("name", "version", "build", "firmware", "board", "chip", "mac", "mode")
        },
        "nav_groups": [list(group) for group in NAV_GROUPS],
        "roots": [module.name for module in nav_roots(data.modules)],
        "modules": [
            {
                "name": module.name,
                "type": module.type,
                "role": module.role,
                "parent": module.parent,
                "ordinal": module.ordinal,
                "enabled": module.enabled,
                "status": module.status,
                "severity": module.severity,
            }
            for module in data.modules.values()
        ],
        "controls": [
            {
                "module": control.module,
                "name": control.name,
                "type": control.type,
                "readonly": control.readonly,
                "min_mode": control.min_mode,
            }
            for control in sorted(data.controls.values(), key=lambda item: (item.module, item.name))
        ],
        "looks": [{"name": look.name, "active": look.active} for look in data.looks],
        "unknown_types": sorted(data.unknown_types),
    }
