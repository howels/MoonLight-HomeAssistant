"""Selects: a MoonLight select or palette, and the Look select on the Control card.

A palette value may be the option's name. A select value may be the index. The entity
shows the name either way, and writes back the form the device stored.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform, home_assistant_error
from .exceptions import MoonLightError
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
    look: MoonLightLookSelect | None = None

    @callback
    def _sync_look() -> None:
        nonlocal look
        if coordinator.module(_CONTROL) is None:
            if look is not None:
                look.async_remove()
                look = None
            return
        if look is None:
            look = MoonLightLookSelect(coordinator)
            async_add_entities([look])

    entry.async_on_unload(coordinator.async_add_listener(_sync_look))
    _sync_look()
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
        # `{mac}_look`. The Basic card finds this entity by the `moonlight` attribute.
        self._attr_unique_id = f"{coordinator.mac}_look"
        self._attr_device_info = coordinator.async_device_info(_CONTROL)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Stay on the Control device if that card is recreated."""
        if self.coordinator.module(_CONTROL) is not None:
            self._attr_device_info = self.coordinator.async_device_info(_CONTROL)
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """The cards find the effect list by this attribute. The registry does not send the unique id."""
        return {"moonlight": "look"}

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
        except MoonLightError as err:
            raise home_assistant_error(err, look=option) from err

