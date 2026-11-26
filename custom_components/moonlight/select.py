"""Selects: a MoonLight select or palette, and the Look select on the Control card.

A palette value may be the option's name. A select value may be the index. The entity
shows the name either way, and writes back the form the device stored.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform
from .exceptions import MoonLightCommandError, MoonLightConnectionError
from .models import Control

PARALLEL_UPDATES = 1

_CONTROL = "Control"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Look select on Control, then one select per writable select and palette."""
    coordinator = entry.runtime_data
    if coordinator.module(_CONTROL) is not None:
        async_add_entities([MoonLightLookSelect(coordinator)])
    await async_setup_control_platform("select", MoonLightSelect)(hass, entry, async_add_entities)


class MoonLightSelect(MoonLightEntity, SelectEntity):
    """One select or palette."""

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the select."""
        super().__init__(coordinator, control.module, control.name)

    @property
    def options(self) -> list[str]:
        """Option names. The current value is included when the device has a name the list does not."""
        control = self.control
        if control is None:
            return []
        names = list(control.options)
        current = self.current_option
        if current and current not in names:
            names.append(current)
        return names

    @property
    def current_option(self) -> str | None:
        """The selected name."""
        control = self.control
        if control is None:
            return None
        if control.value_is_index:
            if isinstance(control.value, int) and 0 <= control.value < len(control.options):
                return control.options[control.value]
            return None
        if isinstance(control.value, str):
            return control.value
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the index or the name, matching the form the device already uses."""
        control = self.control
        if control is None:
            await self._async_write(option)
            return
        if control.value_is_index:
            await self._async_write(control.options.index(option) if option in control.options else option)
            return
        await self._async_write(option)


class MoonLightLookSelect(CoordinatorEntity[MoonLightCoordinator], SelectEntity):
    """Effect looks, on the Control device. That is the card the web UI keeps presets on."""

    _attr_has_entity_name = True
    _attr_name = "Look"
    _attr_icon = "mdi:palette-swatch"

    def __init__(self, coordinator: MoonLightCoordinator) -> None:
        """Bind the select to the Control device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_look"
        self._attr_device_info = coordinator.async_device_info(_CONTROL)

    @property
    def available(self) -> bool:
        """Unavailable while the socket is down."""
        return super().available and self.coordinator.connected

    @property
    def options(self) -> list[str]:
        """Effect looks only. A Drivers or Layouts preset is not a look."""
        return [look.name for look in self.coordinator.data.looks]

    @property
    def current_option(self) -> str | None:
        """The look the device marks active."""
        for look in self.coordinator.data.looks:
            if look.active:
                return look.name
        return None

    async def async_select_option(self, option: str) -> None:
        """Apply the look."""
        try:
            await self.coordinator.async_apply_look(option)
        except MoonLightCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unknown_look",
                translation_placeholders={"name": option, "error": str(err)},
            ) from err
        except MoonLightConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
                translation_placeholders={"error": str(err)},
            ) from err

