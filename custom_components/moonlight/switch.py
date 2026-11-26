"""Switches: a MoonLight bool control, including the synthetic `enabled` flag."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform
from .models import Control

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a switch for every writable bool."""
    await async_setup_control_platform("switch", MoonLightSwitch)(hass, entry, async_add_entities)


class MoonLightSwitch(MoonLightEntity, SwitchEntity):
    """One bool control."""

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the switch to one bool control."""
        super().__init__(coordinator, control.module, control.name)

    @property
    def is_on(self) -> bool | None:
        """The control's value, when it is a bool."""
        control = self.control
        if control is None or not isinstance(control.value, bool):
            return None
        return control.value

    async def async_turn_on(self, **kwargs: object) -> None:
        """Set the bool true."""
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: object) -> None:
        """Set the bool false."""
        await self._async_write(False)
