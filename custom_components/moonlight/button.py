"""Buttons: a MoonLight button control, and one button per effect-look pad.

The device treats one write as the press. Factory reset and SD card format are created
disabled, and the press is refused until Expert mode is on.

A pad's unique id is the preset slot, so a renamed look keeps the same entity.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform, home_assistant_error
from .exceptions import MoonLightError
from .models import Control, Look, preset_name

PARALLEL_UPDATES = 1

_CONTROL = "Control"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a button for every button control, and one per filled effect pad."""
    coordinator = entry.runtime_data
    pads: dict[int, MoonLightPadButton] = {}

    @callback
    def _sync_pads() -> None:
        if coordinator.module(_CONTROL) is None:
            for slot in list(pads):
                pads.pop(slot).async_remove()
            return
        wanted = {look.slot for look in coordinator.data.looks}
        for slot in [slot for slot in pads if slot not in wanted]:
            pads.pop(slot).async_remove()
        added: list[MoonLightPadButton] = []
        for slot in sorted(wanted):
            if slot in pads:
                continue
            entity = MoonLightPadButton(coordinator, slot)
            pads[slot] = entity
            added.append(entity)
        if added:
            async_add_entities(added)

    entry.async_on_unload(coordinator.async_add_listener(_sync_pads))
    _sync_pads()
    await async_setup_control_platform("button", MoonLightButton)(hass, entry, async_add_entities)


class MoonLightButton(MoonLightEntity, ButtonEntity):
    """One button control."""

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the button."""
        super().__init__(coordinator, control.module, control.name)

    async def async_press(self) -> None:
        """Press the button. The value is a placeholder. The device runs the action."""
        await self._async_write(1)


class MoonLightPadButton(CoordinatorEntity[MoonLightCoordinator], ButtonEntity):
    """One filled effect pad. Pressing it applies that look."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, coordinator: MoonLightCoordinator, slot: int) -> None:
        """Bind the button to one preset slot on the Control device."""
        super().__init__(coordinator)
        self._slot = slot
        # `{mac}_pad_{slot}`. The Pro card collects pads by the `moonlight` attribute and `slot`.
        self._attr_unique_id = f"{coordinator.mac}_pad_{slot}"
        self._attr_device_info = coordinator.async_device_info(_CONTROL)

    def _look(self) -> Look | None:
        for look in self.coordinator.data.looks:
            if look.slot == self._slot:
                return look
        return None

    @property
    def name(self) -> str:
        """The preset bank, the pad's place, and the name on the pad. A rename keeps the slot."""
        look = self._look()
        return preset_name(self._slot, look.name if look is not None else None)

    @property
    def extra_state_attributes(self) -> dict[str, int | str]:
        """The Pro card lists pads by `slot`. The registry does not send the unique id."""
        return {"moonlight": "pad", "slot": self._slot}

    @property
    def available(self) -> bool:
        """Unavailable while the socket is down or the pad is empty."""
        return super().available and self.coordinator.connected and self._look() is not None

    async def async_press(self) -> None:
        """Apply the look in this slot."""
        look = self._look()
        if look is None:
            return
        try:
            await self.coordinator.async_apply_look(look.name)
        except MoonLightError as err:
            raise home_assistant_error(err, look=look.name) from err
