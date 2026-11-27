"""Base entity for one MoonLight control.

The control's type decides the platform. The entity reads the live value from the
coordinator, so a patch moves the state without the entity knowing the socket exists.
A control the device removes is removed here too.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .exceptions import (
    MoonLightCommandError,
    MoonLightConnectionError,
    MoonLightError,
    MoonLightExpertError,
    MoonLightResponseError,
)
from .models import Control, entity_name, is_destructive

# Expert and developer controls exist, and they start disabled so the device page stays readable.
_MODE_USER = 0


class MoonLightEntity(CoordinatorEntity[MoonLightCoordinator]):
    """Shared identity, availability and device for a MoonLight entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MoonLightCoordinator, module: str, control: str) -> None:
        """Bind the entity to one module and one control name. The value is read live."""
        super().__init__(coordinator)
        self._module = module
        self._control = control
        # `{mac}_{module}_{control}`. A Control slot is what the cards address as `_Control_{control}`.
        self._attr_unique_id = f"{coordinator.mac}_{module}_{control}"
        current = coordinator.control(module, control)
        self._attr_name = entity_name(coordinator.data.modules, current) if current is not None else control
        self._attr_device_info = coordinator.async_device_info(module)
        if current is not None:
            self._apply_registry_hints(current)

    @callback
    def _handle_coordinator_update(self) -> None:
        """A new tree can move a card, which changes the entity's name and its device."""
        current = self.control
        if current is not None:
            self._attr_name = entity_name(self.coordinator.data.modules, current)
            self._attr_device_info = self.coordinator.async_device_info(current.module)
            self._apply_registry_hints(current)
        super()._handle_coordinator_update()

    @property
    def control(self) -> Control | None:
        """The live control, or None when the device has removed it."""
        return self.coordinator.control(self._module, self._control)

    @property
    def available(self) -> bool:
        """Unavailable while the socket is down or the control has gone."""
        control = self.control
        return (
            super().available
            and self.coordinator.connected
            and control is not None
            and control.assigned
        )

    async def _async_write(self, value: Any) -> None:
        """Send one value. A refusal is the device's reason, in the user's language file."""
        try:
            await self.coordinator.async_set_control(self._module, self._control, value)
        except MoonLightError as err:
            raise home_assistant_error(err, module=self._module, control=self._control) from err

    def _apply_registry_hints(self, control: Control) -> None:
        """Where the entity sits on the device page. Expert controls start disabled, as the UI hides them until that mode.

        A factory reset or a format starts disabled as well. Expert mode is the other gate.
        """
        if is_destructive(control):
            self._attr_entity_registry_enabled_default = False
        else:
            self._attr_entity_registry_enabled_default = control.min_mode == _MODE_USER
        if control.name == "@status" or control.min_mode >= 2:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif control.min_mode >= 1 or control.type == "pin":
            self._attr_entity_category = EntityCategory.CONFIG
        else:
            self._attr_entity_category = None


def home_assistant_error(
    err: MoonLightError,
    *,
    module: str = "",
    control: str = "",
    look: str | None = None,
) -> HomeAssistantError:
    """The Home Assistant error for one device failure, using the strings file."""
    if isinstance(err, MoonLightExpertError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="expert_required",
            translation_placeholders={"module": module, "control": control},
        )
    if isinstance(err, MoonLightConnectionError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="not_connected",
            translation_placeholders={"error": str(err)},
        )
    if isinstance(err, MoonLightResponseError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="request_failed",
            translation_placeholders={"error": str(err)},
        )
    if look is not None and isinstance(err, MoonLightCommandError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="unknown_look",
            translation_placeholders={"name": look, "error": str(err)},
        )
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="command_failed",
        translation_placeholders={"module": module, "control": control, "error": str(err)},
    )


def async_setup_control_platform(
    platform: str,
    entity_type: Callable[[MoonLightCoordinator, Control], MoonLightEntity],
) -> Callable[[HomeAssistant, MoonLightConfigEntry, AddEntitiesCallback], None]:
    """Build `async_setup_entry` for a platform whose entities come from the tree.

    A later full document adds entities that appeared and removes ones that disappeared.
    """

    async def async_setup_entry(
        hass: HomeAssistant,
        entry: MoonLightConfigEntry,
        async_add_entities: AddEntitiesCallback,
    ) -> None:
        coordinator = entry.runtime_data
        known: dict[str, MoonLightEntity] = {}

        @callback
        def _sync() -> None:
            current = {f"{coordinator.mac}_{item.module}_{item.name}": item for item in coordinator.controls_for(platform)}
            for unique_id in [uid for uid in known if uid not in current]:
                known.pop(unique_id).async_remove()
            added: list[MoonLightEntity] = []
            for unique_id, control in current.items():
                if unique_id in known:
                    continue
                entity = entity_type(coordinator, control)
                known[unique_id] = entity
                added.append(entity)
            if added:
                async_add_entities(added)

        entry.async_on_unload(coordinator.async_add_listener(_sync))
        _sync()

    return async_setup_entry
