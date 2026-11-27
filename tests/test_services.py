"""The actions target a device and require JSON values."""

import pytest
from custom_components.moonlight.const import DOMAIN
from homeassistant.helpers import device_registry as dr

from .conftest import MAC
from .test_init import PIPELINE, _setup


async def test_set_control_json_number(hass, aioclient_mock, moonlight_ws) -> None:
    """The value 40 is a number, not the text 40."""
    entry = await _setup(hass, aioclient_mock, options=PIPELINE)
    device = dr.async_get(hass).async_get_child_device_by_identifier(
        (DOMAIN, f"{MAC}_Effects"), entry.entry_id
    )
    assert device is not None
    await hass.services.async_call(
        DOMAIN,
        "set_control",
        {"device_id": device.id, "module": "Pulse", "control": "speed", "value": "40"},
        blocking=True,
    )
    assert {"module": "Pulse", "control": "speed", "value": 40} in moonlight_ws.sent
    assert entry.runtime_data.control("Pulse", "speed").value == 40


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
