"""The light is the desk's first channel. Looks stay on Control."""

import pytest
from custom_components.moonlight.const import DOMAIN
from homeassistant.components.light import ATTR_EFFECT
from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .conftest import MAC, control_posts, mock_control
from .test_init import _setup

LIGHT = "light.mm_abcd_control_light"


async def test_light_reads_the_desk(hass, aioclient_mock) -> None:
    """switch1 is power, fader1 is brightness, encoder1 selects the palette."""
    await _setup(hass, aioclient_mock)
    state = hass.states.get(LIGHT)
    assert state.state == "on"
    assert state.attributes["brightness"] == 128
    assert state.attributes["effect"] == "Rainbow"
    assert state.attributes["effect_list"] == ["Rainbow", "Party"]


async def test_turn_off_writes_switch1(hass, aioclient_mock) -> None:
    """Turning the light off clears switch1 and leaves the fader."""
    await _setup(hass, aioclient_mock)
    mock_control(aioclient_mock)
    await hass.services.async_call(
        LIGHT_DOMAIN, "turn_off", {ATTR_ENTITY_ID: LIGHT}, blocking=True
    )
    assert {"module": "Control", "control": "switch1", "value": False} in control_posts(aioclient_mock)
    assert hass.states.get(LIGHT).state == "off"


async def test_effect_writes_the_encoder_then_the_fader_then_power(hass, aioclient_mock) -> None:
    """A palette is encoder1's index. Brightness and power follow it."""
    await _setup(hass, aioclient_mock)
    mock_control(aioclient_mock)
    await hass.services.async_call(
        LIGHT_DOMAIN,
        "turn_on",
        {ATTR_ENTITY_ID: LIGHT, ATTR_EFFECT: "Party", "brightness": 10},
        blocking=True,
    )
    frames = [item for item in control_posts(aioclient_mock) if item.get("module") == "Control"]
    encoder = next(index for index, frame in enumerate(frames) if frame.get("control") == "encoder1")
    fader = next(index for index, frame in enumerate(frames) if frame.get("control") == "fader1")
    power = next(
        index
        for index, frame in enumerate(frames)
        if frame.get("control") == "switch1" and frame.get("value") is True
    )
    assert encoder < fader < power
    assert frames[encoder]["value"] == 1
    assert frames[fader]["value"] == 10


async def test_unknown_palette_names_it(hass, aioclient_mock) -> None:
    """A palette the device does not have fails with that name."""
    await _setup(hass, aioclient_mock)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            LIGHT_DOMAIN,
            "turn_on",
            {ATTR_ENTITY_ID: LIGHT, ATTR_EFFECT: "Missing"},
            blocking=True,
        )


async def test_look_select_is_on_control(hass, aioclient_mock, moonlight_ws) -> None:
    """The Look select lives on Control, and a driver preset is not an option."""
    await _setup(hass, aioclient_mock)
    state = hass.states.get("select.mm_abcd_control_look")
    assert state.state == "Rainbow"
    assert state.attributes["options"] == ["Rainbow"]
    assert state.attributes["moonlight"] == "look"
    aioclient_mock.post("http://192.0.2.10:80/api/list/Control/presets/1/apply", json={"ok": True})
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: "select.mm_abcd_control_look", "option": "Rainbow"},
        blocking=True,
    )
    assert any(item.get("resync") for item in moonlight_ws.sent if isinstance(item, dict))


async def test_a_filled_pad_is_a_button(hass, aioclient_mock, moonlight_ws) -> None:
    """One button per effect look, in slot order. A driver preset is not a pad."""
    await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    pad = registry.async_get_entity_id("button", DOMAIN, f"{MAC}_pad_1")
    assert pad is not None
    assert hass.states.get(pad).name.endswith("4 Preset 1 · Rainbow")
    assert hass.states.get(pad).attributes["moonlight"] == "pad"
    assert hass.states.get(pad).attributes["slot"] == 1
    assert registry.async_get_entity_id("button", DOMAIN, f"{MAC}_pad_2") is None
    aioclient_mock.post("http://192.0.2.10:80/api/list/Control/presets/1/apply", json={"ok": True})
    await hass.services.async_call("button", "press", {ATTR_ENTITY_ID: pad}, blocking=True)
    assert any(item.get("resync") for item in moonlight_ws.sent if isinstance(item, dict))
