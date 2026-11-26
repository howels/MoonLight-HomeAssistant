"""The master light: Drivers' on and brightness, which is where that card puts them.

Looks are the light's effect list so an automation can apply one. The same looks are the
Look select on the Control device, which is the card the web UI keeps them on.
A palette stays a select on Drivers. MoonLight snaps a colour to a palette, so the light
has no colour wheel.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .exceptions import MoonLightCommandError, MoonLightConnectionError

PARALLEL_UPDATES = 1

_DRIVERS = "Drivers"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the one light for the endpoint."""
    async_add_entities([MoonLightLight(entry.runtime_data)])


class MoonLightLight(CoordinatorEntity[MoonLightCoordinator], LightEntity):
    """On and brightness from the Drivers card."""

    _attr_has_entity_name = True
    _attr_translation_key = "light"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: MoonLightCoordinator) -> None:
        """Bind the light to the Drivers device when that card exists."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.mac}_light"
        self._attr_device_info = coordinator.async_device_info(
            _DRIVERS if coordinator.module(_DRIVERS) is not None else None
        )

    @property
    def available(self) -> bool:
        """The light needs the socket and the Drivers `on` control."""
        return (
            super().available
            and self.coordinator.connected
            and self.coordinator.control(_DRIVERS, "on") is not None
        )

    @property
    def supported_features(self) -> LightEntityFeature:
        """Effect when the device has at least one effect look."""
        if self.coordinator.data.looks:
            return LightEntityFeature.EFFECT
        return LightEntityFeature(0)

    @property
    def is_on(self) -> bool | None:
        """Drivers `on`."""
        control = self.coordinator.control(_DRIVERS, "on")
        if control is None or not isinstance(control.value, bool):
            return None
        return control.value

    @property
    def brightness(self) -> int | None:
        """Drivers `brightness`, already 0 to 255."""
        control = self.coordinator.control(_DRIVERS, "brightness")
        if control is None or isinstance(control.value, bool) or not isinstance(control.value, int):
            return None
        return control.value

    @property
    def effect_list(self) -> list[str]:
        """Effect looks. A preset that rewires pins or geometry is not in this list."""
        return [look.name for look in self.coordinator.data.looks]

    @property
    def effect(self) -> str | None:
        """The look the device currently marks active."""
        for look in self.coordinator.data.looks:
            if look.active:
                return look.name
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Apply a look first, then brightness, then on. A bad look changes nothing else."""
        if ATTR_EFFECT in kwargs:
            await self._async_look(str(kwargs[ATTR_EFFECT]))
        if ATTR_BRIGHTNESS in kwargs:
            await self._async_control("brightness", int(kwargs[ATTR_BRIGHTNESS]))
        await self._async_control("on", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear Drivers `on`. Brightness is left as it is, as the card's toggle does."""
        await self._async_control("on", False)

    async def _async_look(self, name: str) -> None:
        try:
            await self.coordinator.async_apply_look(name)
        except MoonLightCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="unknown_look",
                translation_placeholders={"name": name, "error": str(err)},
            ) from err
        except MoonLightConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_control(self, control: str, value: Any) -> None:
        try:
            await self.coordinator.async_set_control(_DRIVERS, control, value)
        except MoonLightCommandError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"module": _DRIVERS, "control": control, "error": str(err)},
            ) from err
        except MoonLightConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="not_connected",
                translation_placeholders={"error": str(err)},
            ) from err
