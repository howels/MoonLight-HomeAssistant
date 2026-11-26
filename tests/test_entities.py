"""Entities follow the card path, and a write uses the socket."""

import pytest
from custom_components.moonlight.const import CONF_EXPERT_MODE, DOMAIN
from custom_components.moonlight.exceptions import MoonLightCommandError, MoonLightExpertError
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er

from .conftest import MAC, state
from .test_init import _setup


def _entity_id(hass, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


async def test_nested_controls_use_the_card_path(hass, aioclient_mock) -> None:
    """Pulse's controls are on the Effects device, named by the cards above them."""
    await _setup(hass, aioclient_mock)
    speed = _entity_id(hass, "number", f"{MAC}_Pulse_speed")
    assert speed is not None
    assert hass.states.get(speed).state == "60.0"
    assert hass.states.get(speed).name.endswith("Layer · Pulse · Speed") or "Layer" in hass.states.get(speed).name
    mirror = _entity_id(hass, "switch", f"{MAC}_Pulse_mirror")
    assert hass.states.get(mirror).state == "off"
    waveform = _entity_id(hass, "select", f"{MAC}_Pulse_waveform")
    assert hass.states.get(waveform).state == "sin"
    note = _entity_id(hass, "text", f"{MAC}_Pulse_note")
    assert hass.states.get(note).state == "hello"
    width = _entity_id(hass, "number", f"{MAC}_Grid_width")
    assert hass.states.get(width).attributes["friendly_name"].endswith("Grid · Width")


async def test_expert_control_starts_disabled(hass, aioclient_mock) -> None:
    """minMode 1 is created and left disabled, as the web interface hides it."""
    await _setup(hass, aioclient_mock)
    entry = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{MAC}_Pulse_advanced")
    assert entry is not None
    assert er.async_get(hass).async_get(entry).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_unknown_password_and_light_controls_are_absent(hass, aioclient_mock) -> None:
    """A future type, a password, and Drivers on are not entities of their own."""
    await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{MAC}_Pulse_future") is None
    assert registry.async_get_entity_id("text", DOMAIN, f"{MAC}_Pulse_secret") is None
    assert registry.async_get_entity_id("switch", DOMAIN, f"{MAC}_Drivers_on") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{MAC}_Drivers_brightness") is None


async def test_number_write_goes_over_the_socket(hass, aioclient_mock, moonlight_ws) -> None:
    """A slider write is a socket frame, and the state moves before the next patch."""
    await _setup(hass, aioclient_mock)
    speed = _entity_id(hass, "number", f"{MAC}_Pulse_speed")
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: speed, "value": 40},
        blocking=True,
    )
    assert {"module": "Pulse", "control": "speed", "value": 40} in moonlight_ws.sent
    assert hass.states.get(speed).state == "40.0"


async def test_out_of_range_is_the_device_sentence(hass, aioclient_mock) -> None:
    """A value outside min and max fails before a frame is sent."""
    await _setup(hass, aioclient_mock)
    with pytest.raises(MoonLightCommandError, match="value out of range"):
        await hass.config_entries.async_entries(DOMAIN)[0].runtime_data.async_set_control("Pulse", "speed", 0)


async def test_a_patch_moves_the_number(hass, aioclient_mock, moonlight_ws) -> None:
    """A patch from the device updates the entity."""
    await _setup(hass, aioclient_mock)
    moonlight_ws.feed({"patch": [{"path": "Pulse/speed", "value": 12}]})
    await hass.async_block_till_done()
    speed = _entity_id(hass, "number", f"{MAC}_Pulse_speed")
    assert hass.states.get(speed).state == "12.0"


async def test_factory_reset_is_disabled_until_expert_mode(hass, aioclient_mock, moonlight_ws) -> None:
    """The button starts disabled, and the write is refused until Expert mode is on."""
    body = state()
    for module in body["modules"]:
        if module["name"] == "System":
            module["controls"].append(
                {"name": "factory reset", "type": "button", "confirm": True}
            )
    entry = await _setup(hass, aioclient_mock, state_body=body)
    entity_id = _entity_id(hass, "button", f"{MAC}_System_factory reset")
    assert entity_id is not None
    assert er.async_get(hass).async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    with pytest.raises(MoonLightExpertError):
        await entry.runtime_data.async_set_control("System", "factory reset", 1)
    assert not any(
        isinstance(item, dict) and item.get("control") == "factory reset" for item in moonlight_ws.sent
    )
    hass.config_entries.async_update_entry(entry, options={CONF_EXPERT_MODE: True})
    await entry.runtime_data.async_set_control("System", "factory reset", 1)
    assert {"module": "System", "control": "factory reset", "value": 1} in moonlight_ws.sent


async def test_status_sensor_carries_severity(hass, aioclient_mock) -> None:
    """The card's status line is a sensor, and severity rides as an attribute."""
    await _setup(hass, aioclient_mock)
    status = _entity_id(hass, "sensor", f"{MAC}_Layer_@status")
    state = hass.states.get(status)
    assert state.state == "running"
    assert state.attributes["severity"] == "status"
