"""Sensors: read-only controls, and a module's status line.

`display` is text. `display-int` and `progress` are numbers. A read-only bool, select,
number or text is a sensor too, so a value the device will not take a write for is not
offered as one.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
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
    """Set up a sensor for every read-only control."""
    await async_setup_control_platform("sensor", MoonLightSensor)(hass, entry, async_add_entities)


class MoonLightSensor(MoonLightEntity, SensorEntity):
    """One read-only value."""

    def __init__(self, coordinator: MoonLightCoordinator, control: Control) -> None:
        """Bind the sensor and apply a device class when the unit is one Home Assistant knows."""
        super().__init__(coordinator, control.module, control.name)
        if control.unit == "dBm":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif control.type in {"display-int", "progress"}:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            if control.unit:
                self._attr_native_unit_of_measurement = control.unit

    @property
    def native_value(self) -> str | int | float | None:
        """The value, in the form the sensor's type can show."""
        control = self.control
        if control is None:
            return None
        value = control.value
        if control.type in {"display-int", "progress"}:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None
            return value
        if control.type in {"select", "palette"} and control.value_is_index:
            if isinstance(value, int) and 0 <= value < len(control.options):
                return control.options[value]
            return None
        if isinstance(value, bool | int | float | str):
            return value
        return None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Status carries the module's severity. Progress carries its total. `module` and `control` stay."""
        attributes: dict[str, object] = dict(super().extra_state_attributes)
        control = self.control
        if control is None:
            return attributes
        if control.name == "@status":
            module = self.coordinator.module(control.module)
            if module is not None and module.severity is not None:
                attributes["severity"] = module.severity
        elif control.type == "progress" and control.total is not None:
            attributes["total"] = control.total
            if control.unit:
                attributes["unit"] = control.unit
        return attributes
