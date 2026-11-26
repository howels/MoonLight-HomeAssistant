"""Text controls: text, textarea, a file path and an IPv4 address.

Password controls are not entities. The API returns them obfuscated, and writing that
text back would store the obfuscation as the password.
"""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform
from .models import IPV4_ADDRESS, Control

PARALLEL_UPDATES = 1

# Long enough for a path or a broker URL. The device rejects a value it will not store.
_MAX_LENGTH = 2048


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a text entity for every writable text control."""
    await async_setup_control_platform("text", MoonLightText)(hass, entry, async_add_entities)


class MoonLightText(MoonLightEntity, TextEntity):
    """One text control."""

    _attr_mode = TextMode.TEXT
    _attr_native_max = _MAX_LENGTH

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the text entity. An IPv4 control carries a pattern so a bad address fails here."""
        super().__init__(coordinator, control.module, control.name)
        self._apply_pattern(control)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the IPv4 pattern on the control the device currently describes."""
        control = self.control
        if control is not None:
            self._apply_pattern(control)
        super()._handle_coordinator_update()

    def _apply_pattern(self, control: Control) -> None:
        self._attr_pattern = IPV4_ADDRESS.pattern if control.type == "ipv4" else None

    @property
    def native_value(self) -> str | None:
        """The text, when the device sent a string."""
        control = self.control
        if control is None or not isinstance(control.value, str):
            return None
        return control.value

    async def async_set_value(self, value: str) -> None:
        """Write the text."""
        await self._async_write(value)
