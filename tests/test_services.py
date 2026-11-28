"""The actions target a device and require JSON values."""

import pytest
from custom_components.moonlight.const import DOMAIN
from homeassistant.helpers import device_registry as dr

from .conftest import MAC, control_posts, mock_control
from .test_init import PIPELINE, _setup


async def test_set_control_json_number(hass, aioclient_mock, moonlight_ws) -> None:
    """The value 40 is a number, not the text 40."""
    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    mock_control(aioclient_mock)
    await hass.services.async_call(
        DOMAIN,
        "set_control",
        {"device_id": device.id, "module": "Pulse", "control": "speed", "value": "40"},
        blocking=True,
    )
    assert {"module": "Pulse", "control": "speed", "value": 40} in control_posts(aioclient_mock)
    assert {"module": "Pulse", "control": "speed", "value": 40} not in moonlight_ws.sent
    assert entry.runtime_data.control("Pulse", "speed").value == 40


async def test_set_control_accepts_a_target_list(hass, aioclient_mock) -> None:
    """Home Assistant delivers a service target's device id as a one-item list."""
    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    mock_control(aioclient_mock)
    await hass.services.async_call(
        DOMAIN,
        "set_control",
        {"device_id": [device.id], "module": "Pulse", "control": "speed", "value": "40"},
        blocking=True,
    )
    assert {"module": "Pulse", "control": "speed", "value": 40} in control_posts(aioclient_mock)


async def test_value_must_be_json(hass, aioclient_mock) -> None:
    """A bare word is not JSON, and the error says so."""
    from homeassistant.exceptions import ServiceValidationError

    entry = await _setup(hass, aioclient_mock)
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, MAC), entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "set_control",
            {"device_id": device.id, "module": "Pulse", "control": "speed", "value": "fast"},
            blocking=True,
        )


def _module_calls(aioclient_mock, method: str, suffix: str) -> list:
    return [
        call
        for call in aioclient_mock.mock_calls
        if str(call[0]).lower() == method and str(call[1]).endswith(suffix)
    ]


async def test_add_module_posts_the_type_and_parent(hass, aioclient_mock) -> None:
    """Adding Text under Layer is POST /api/modules, then the tree is read again."""
    from .conftest import HOST, PORT

    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    aioclient_mock.post(
        f"http://{HOST}:{PORT}/api/modules",
        json={"ok": True, "name": "Text"},
    )
    await hass.services.async_call(
        DOMAIN,
        "add_module",
        {"device_id": device.id, "type": "TextEffect", "parent": "Layer"},
        blocking=True,
    )
    posts = _module_calls(aioclient_mock, "post", "/api/modules")
    assert posts
    assert posts[-1][2] == {"type": "TextEffect", "parent_id": "Layer"}


async def test_remove_module_deletes_that_module(hass, aioclient_mock) -> None:
    """Removing Pulse is DELETE /api/modules/Pulse."""
    from urllib.parse import quote

    from .conftest import HOST, PORT

    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    aioclient_mock.delete(f"http://{HOST}:{PORT}/api/modules/{quote('Pulse')}", json={"ok": True})
    await hass.services.async_call(
        DOMAIN,
        "remove_module",
        {"device_id": device.id, "module": "Pulse"},
        blocking=True,
    )
    assert _module_calls(aioclient_mock, "delete", "/api/modules/Pulse")


async def test_add_module_refuses_a_missing_parent(hass, aioclient_mock) -> None:
    """A parent the tree does not have is refused before a request is sent."""
    from homeassistant.exceptions import HomeAssistantError

    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "add_module",
            {"device_id": device.id, "type": "TextEffect", "parent": "Missing"},
            blocking=True,
        )
    assert not _module_calls(aioclient_mock, "post", "/api/modules")


async def test_replace_module_posts_the_new_type(hass, aioclient_mock) -> None:
    """Replacing Pulse keeps the slot and sends the new type."""
    from .conftest import HOST, PORT

    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    aioclient_mock.post(f"http://{HOST}:{PORT}/api/modules/Pulse/replace", json={"ok": True})
    await hass.services.async_call(
        DOMAIN,
        "replace_module",
        {"device_id": device.id, "module": "Pulse", "type": "TextEffect"},
        blocking=True,
    )
    posts = _module_calls(aioclient_mock, "post", "/api/modules/Pulse/replace")
    assert posts
    assert posts[-1][2] == {"type": "TextEffect"}


async def test_clear_children_patches_the_layer(hass, aioclient_mock) -> None:
    """Clearing Layer removes its effects and leaves the layer."""
    from .conftest import HOST, PORT

    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    aioclient_mock.patch(f"http://{HOST}:{PORT}/api/state", json={"ok": True})
    await hass.services.async_call(
        DOMAIN,
        "clear_children",
        {"device_id": device.id, "module": "Layer"},
        blocking=True,
    )
    patches = _module_calls(aioclient_mock, "patch", "/api/state")
    assert patches
    assert patches[-1][2] == {"Effects": {"Layer": {"$patch": "replace"}}}
