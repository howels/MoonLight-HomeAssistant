"""The light is Drivers' on and brightness. Looks are effect presets only."""

import pytest
from homeassistant.components.light import ATTR_EFFECT
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError

from .test_init import _setup


async def test_light_reads_drivers(hass, aioclient_mock) -> None:
    """On and brightness come from the Drivers card."""
    await _setup(hass, aioclient_mock)
    state = hass.states.get("light.mm_abcd_drivers_light")
    assert state.state == "on"
    assert state.attributes["brightness"] == 128
    assert state.attributes["effect"] == "Rainbow"
    assert state.attributes["effect_list"] == ["Rainbow"]


async def test_turn_off_writes_drivers_on(hass, aioclient_mock, moonlight_ws) -> None:
    """Turning the light off clears Drivers on and leaves brightness."""
    await _setup(hass, aioclient_mock)
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: "light.mm_abcd_drivers_light"}, blocking=True
    )
    assert {"module": "Drivers", "control": "on", "value": False} in moonlight_ws.sent
    assert hass.states.get("light.mm_abcd_drivers_light").state == "off"


async def test_unknown_effect_names_the_look(hass, aioclient_mock) -> None:
    """A look the device does not have fails with that name."""
    await _setup(hass, aioclient_mock)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: "light.mm_abcd_drivers_light", ATTR_EFFECT: "Missing"},
            blocking=True,
        )


async def test_look_select_is_on_control(hass, aioclient_mock, moonlight_ws) -> None:
    """The Look select lives on Control, and a driver preset is not an option."""
    await _setup(hass, aioclient_mock)
    state = hass.states.get("select.mm_abcd_control_look")
    assert state.state == "Rainbow"
    assert state.attributes["options"] == ["Rainbow"]
    aioclient_mock.post("http://192.0.2.10:80/api/list/Control/presets/1/apply", json={"ok": True})
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.mm_abcd_control_look", "option": "Rainbow"},
        blocking=True,
    )
    assert any(item.get("resync") for item in moonlight_ws.sent if isinstance(item, dict))
