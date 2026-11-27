"""The endpoint light: the desk's first channel.

switch1 is power and forwards to the device's on control. fader1 is brightness.
encoder1 is the palette, which is the light's effect list. MoonLight snaps a colour
to a palette, so the light has no colour wheel. Effect looks stay on the Look select
and on one button per pad.
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import home_assistant_error
from .exceptions import MoonLightCommandError, MoonLightError
from .models import Control

PARALLEL_UPDATES = 1

_CONTROL = "Control"
_SWITCH = "switch1"
_FADER = "fader1"
_ENCODER = "encoder1"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the one light for the endpoint."""
    async_add_entities([MoonLightLight(entry.runtime_data)])


class MoonLightLight(CoordinatorEntity[MoonLightCoordinator], LightEntity):
    """Power, brightness and palette from the Control desk's first channel."""

    _attr_has_entity_name = True
    _attr_translation_key = "light"
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, coordinator: MoonLightCoordinator) -> None:
        """Bind the light to the Control device when that card exists."""
        super().__init__(coordinator)
        # `{mac}_light`. The Lovelace cards are given this entity and find the desk from its device.
        self._attr_unique_id = f"{coordinator.mac}_light"
        self._attr_device_info = coordinator.async_device_info(self._device_module())

    def _device_module(self) -> str | None:
        if self.coordinator.module(_CONTROL) is not None:
            return _CONTROL
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Follow Control if that card appears after setup."""
        self._attr_device_info = self.coordinator.async_device_info(self._device_module())
        super()._handle_coordinator_update()

    def _slot(self, name: str, fallback_module: str, fallback: str) -> Control | None:
        """The desk slot, or the control it drives when this firmware has no desk."""
        desk = self.coordinator.control(_CONTROL, name)
        if desk is not None:
            return desk
        return self.coordinator.control(fallback_module, fallback)

    def _palette(self) -> Control | None:
        """The palette encoder1 drives, or Drivers' palette when the slot has no target."""
        encoder = self.coordinator.control(_CONTROL, _ENCODER)
        if encoder is not None and encoder.target:
            module, _, name = encoder.target.partition(".")
            if name:
                target = self.coordinator.control(module, name)
                if target is not None and target.options:
                    return target
        palette = self.coordinator.control("Drivers", "palette")
        if palette is not None and palette.options:
            return palette
        return None

    @property
    def available(self) -> bool:
        """The light needs the socket and a power control."""
        return super().available and self.coordinator.connected and self._slot(_SWITCH, "Drivers", "on") is not None

    @property
    def supported_features(self) -> LightEntityFeature:
        """Effect when a palette list is present."""
        palette = self._palette()
        if palette is not None and palette.options:
            return LightEntityFeature.EFFECT
        return LightEntityFeature(0)

    @property
    def is_on(self) -> bool | None:
        """switch1. The desk forwards it to the device's on control."""
        control = self._slot(_SWITCH, "Drivers", "on")
        if control is None or not isinstance(control.value, bool):
            return None
        return control.value

    @property
    def brightness(self) -> int | None:
        """fader1, already 0 to 255."""
        control = self._slot(_FADER, "Drivers", "brightness")
        if control is None or isinstance(control.value, bool) or not isinstance(control.value, int):
            return None
        return control.value

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """The fader, including while the light is off.

        Home Assistant omits `brightness` when `is_on` is false. The desk keeps the
        fader, and the cards read `level` then.
        """
        control = self._slot(_FADER, "Drivers", "brightness")
        if control is None or isinstance(control.value, bool) or not isinstance(control.value, int):
            return {}
        return {"level": control.value}

    @property
    def effect_list(self) -> list[str]:
        """Palette names. encoder1's position selects one."""
        palette = self._palette()
        if palette is None:
            return []
        return list(palette.options)

    @property
    def effect(self) -> str | None:
        """The palette at encoder1's position."""
        palette = self._palette()
        if palette is None:
            return None
        encoder = self.coordinator.control(_CONTROL, _ENCODER)
        if encoder is not None and isinstance(encoder.value, int) and 0 <= encoder.value < len(palette.options):
            return palette.options[encoder.value]
        if isinstance(palette.value, str) and palette.value in palette.options:
            return palette.value
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Palette, then brightness, then power. Each write is the desk slot."""
        if ATTR_EFFECT in kwargs:
            await self._async_palette(str(kwargs[ATTR_EFFECT]))
        if ATTR_BRIGHTNESS in kwargs:
            await self._async_slot(_FADER, "Drivers", "brightness", int(kwargs[ATTR_BRIGHTNESS]))
        await self._async_slot(_SWITCH, "Drivers", "on", True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Clear switch1. Brightness stays, as the desk's power switch does."""
        await self._async_slot(_SWITCH, "Drivers", "on", False)

    async def _async_palette(self, name: str) -> None:
        palette = self._palette()
        if palette is None or name not in palette.options:
            raise home_assistant_error(MoonLightCommandError(f"no palette {name}"), look=name)
        index = palette.options.index(name)
        encoder = self.coordinator.control(_CONTROL, _ENCODER)
        if encoder is not None:
            await self._async_write(_CONTROL, _ENCODER, index)
            return
        await self._async_write(palette.module, palette.name, name if not palette.value_is_index else index)

    async def _async_slot(self, desk: str, module: str, control: str, value: Any) -> None:
        if self.coordinator.control(_CONTROL, desk) is not None:
            await self._async_write(_CONTROL, desk, value)
            return
        await self._async_write(module, control, value)

    async def _async_write(self, module: str, control: str, value: Any) -> None:
        try:
            await self.coordinator.async_set_control(module, control, value)
        except MoonLightError as err:
            raise home_assistant_error(err, module=module, control=control) from err
