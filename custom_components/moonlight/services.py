"""Actions that name a module the way the web UI does.

`set_control` writes one control. The value is JSON, so a number, a bool and a string
stay distinct: `40`, `true`, `"Rainbow"`. `apply_look` applies one effect look by name.
`add_module` creates a module under a parent. `remove_module` deletes one and its children.
"""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service

from .const import (
    ATTR_CONTROL,
    ATTR_LOOK,
    ATTR_MODULE,
    ATTR_PARENT,
    ATTR_TYPE,
    ATTR_VALUE,
    DOMAIN,
    SERVICE_ADD_MODULE,
    SERVICE_APPLY_LOOK,
    SERVICE_CLEAR_CHILDREN,
    SERVICE_REMOVE_MODULE,
    SERVICE_REPLACE_MODULE,
    SERVICE_SET_CONTROL,
)
from .entity import home_assistant_error
from .exceptions import MoonLightConnectionError, MoonLightError


def _one_device(value: Any) -> str:
    """One device id.

    A card sends the id as a string. Home Assistant's service target turns that
    same field into a one-item list before the action schema runs.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], str):
        return value[0]
    raise vol.Invalid("value should be a string")


_SET_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _one_device,
        vol.Required(ATTR_MODULE): cv.string,
        vol.Required(ATTR_CONTROL): cv.string,
        vol.Required(ATTR_VALUE): cv.string,
    }
)
_LOOK_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _one_device,
        vol.Required(ATTR_LOOK): cv.string,
    }
)
_ADD_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _one_device,
        vol.Required(ATTR_TYPE): cv.string,
        vol.Required(ATTR_PARENT): cv.string,
    }
)
_REMOVE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _one_device,
        vol.Required(ATTR_MODULE): cv.string,
    }
)
_REPLACE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): _one_device,
        vol.Required(ATTR_MODULE): cv.string,
        vol.Required(ATTR_TYPE): cv.string,
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions. A second config entry does not register them again."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_CONTROL):
        return

    async def _set_control(call: ServiceCall) -> None:
        value = _parse_value(call.data[ATTR_VALUE])
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.async_set_control(call.data[ATTR_MODULE], call.data[ATTR_CONTROL], value)
            except MoonLightError as err:
                raise home_assistant_error(
                    err,
                    module=call.data[ATTR_MODULE],
                    control=call.data[ATTR_CONTROL],
                ) from err

    async def _apply_look(call: ServiceCall) -> None:
        name = call.data[ATTR_LOOK]
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.async_apply_look(name)
            except MoonLightError as err:
                raise home_assistant_error(err, look=name) from err

    async def _add_module(call: ServiceCall) -> None:
        type_name = call.data[ATTR_TYPE]
        parent = call.data[ATTR_PARENT]
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.async_add_module(type_name, parent)
            except MoonLightError as err:
                raise _module_error(err, "add", f"{type_name} under {parent}") from err

    async def _remove_module(call: ServiceCall) -> None:
        name = call.data[ATTR_MODULE]
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.async_remove_module(name)
            except MoonLightError as err:
                raise _module_error(err, "remove", name) from err

    async def _replace_module(call: ServiceCall) -> None:
        name = call.data[ATTR_MODULE]
        type_name = call.data[ATTR_TYPE]
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.async_replace_module(name, type_name)
            except MoonLightError as err:
                raise _module_error(err, "replace", f"{name} with {type_name}") from err

    async def _clear_children(call: ServiceCall) -> None:
        name = call.data[ATTR_MODULE]
        for coordinator in await _coordinators(hass, call):
            try:
                await coordinator.async_clear_children(name)
            except MoonLightError as err:
                raise _module_error(err, "clear", name) from err

    hass.services.async_register(DOMAIN, SERVICE_SET_CONTROL, _set_control, schema=_SET_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_APPLY_LOOK, _apply_look, schema=_LOOK_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ADD_MODULE, _add_module, schema=_ADD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_MODULE, _remove_module, schema=_REMOVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REPLACE_MODULE, _replace_module, schema=_REPLACE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CLEAR_CHILDREN, _clear_children, schema=_REMOVE_SCHEMA)


async def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[Any]:
    """The loaded entries the call targets. No target is an error, not a guess."""
    # Imported lazily: the service module is loaded from async_setup, before entries exist.
    from .coordinator import MoonLightCoordinator

    entry_ids = await service.async_extract_config_entry_ids(call)
    if not entry_ids:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_device")
    found: list[MoonLightCoordinator] = []
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"title": entry.title},
            )
        found.append(entry.runtime_data)
    if not found:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_device")
    return found


def _module_error(err: MoonLightError, action: str, name: str) -> HomeAssistantError:
    """The device refused to add or remove a module, or it could not be reached."""
    if isinstance(err, MoonLightConnectionError):
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="not_connected",
            translation_placeholders={"error": str(err)},
        )
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="module_change_failed",
        translation_placeholders={"action": action, "name": name, "error": str(err)},
    )


def _parse_value(raw: str) -> Any:
    """JSON so `40` is a number and `"40"` is text. MoonLight treats those differently."""
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="value_not_json",
            translation_placeholders={"value": raw, "detail": err.msg},
        ) from err
    if value is None or isinstance(value, dict | list):
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="value_not_scalar")
    return value
