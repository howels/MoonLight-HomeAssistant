"""Buttons: a MoonLight button control.

The device treats one write as the press. Factory reset and SD card format are created
disabled, and the press is refused until Expert mode is on.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up a button for every button control."""
    await async_setup_control_platform("button", MoonLightButton)(hass, entry, async_add_entities)


class MoonLightButton(MoonLightEntity, ButtonEntity):
    """One button control."""

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the button."""
        super().__init__(coordinator, control.module, control.name)

    async def async_press(self) -> None:
        """Press the button. The value is a placeholder. The device runs the action."""
        await self._async_write(1)
