"""Numbers: uint8, uint16, int16, int32 and pin controls."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform
from .models import Control

PARALLEL_UPDATES = 1

# A control that omitted min and max still has to be settable. The device rejects a value it cannot store.
_WIDE_MIN = -2147483648.0
_WIDE_MAX = 2147483647.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a number for every writable numeric control."""
    await async_setup_control_platform("number", MoonLightNumber)(hass, entry, async_add_entities)


class MoonLightNumber(MoonLightEntity, NumberEntity):
    """One numeric control. A uint8 is a slider. A pin, or a control marked `numberField`, is a box."""

    _attr_native_step = 1.0

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the number. The range is read live, because a resync can change it."""
        super().__init__(coordinator, control.module, control.name)
        box = control.number_field or control.type == "pin"
        self._attr_mode = NumberMode.BOX if box else NumberMode.SLIDER

    @property
    def native_min_value(self) -> float:
        """The device's minimum, or the wide fallback when the document omitted it."""
        control = self.control
        if control is None or control.minimum is None:
            return _WIDE_MIN
        return float(control.minimum)

    @property
    def native_max_value(self) -> float:
        """The device's maximum, or the wide fallback when the document omitted it."""
        control = self.control
        if control is None or control.maximum is None:
            return _WIDE_MAX
        return float(control.maximum)

    @property
    def native_value(self) -> float | None:
        """The current number."""
        control = self.control
        if control is None or isinstance(control.value, bool) or not isinstance(control.value, int | float):
            return None
        return float(control.value)

    async def async_set_native_value(self, value: float) -> None:
        """Send the number. A fractional slider step is still a whole control value."""
        await self._async_write(int(value))
