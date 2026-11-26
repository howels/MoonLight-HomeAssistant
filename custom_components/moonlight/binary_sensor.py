"""The connectivity sensor. It stays available while the socket is down, so it can read off."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MoonLightConfigEntry, MoonLightCoordinator
from .entity import MoonLightEntity, async_setup_control_platform
from .models import Control

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MoonLightConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the endpoint connectivity sensor, and a sensor for every read-only bool."""
    async_add_entities([MoonLightConnectedSensor(entry.runtime_data)])
    await async_setup_control_platform("binary_sensor", MoonLightBinarySensor)(hass, entry, async_add_entities)


class MoonLightConnectedSensor(BinarySensorEntity):
    """Whether `/ws` is open. This entity is on the endpoint device."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MoonLightCoordinator) -> None:
        """Bind the sensor to the coordinator without using control availability."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.mac}_connected"
        self._attr_device_info = coordinator.async_device_info(None)

    @property
    def is_on(self) -> bool:
        """True while the WebSocket is subscribed."""
        return self.coordinator.connected

    async def async_added_to_hass(self) -> None:
        """Update when the coordinator publishes, including a socket drop."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle))

    def _handle(self) -> None:
        self.async_write_ha_state()


class MoonLightBinarySensor(MoonLightEntity, BinarySensorEntity):
    """A read-only bool."""

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the sensor."""
        super().__init__(coordinator, control.module, control.name)

    @property
    def is_on(self) -> bool | None:
        """The bool, when the device sent one."""
        control = self.control
        if control is None or not isinstance(control.value, bool):
            return None
        return control.value
