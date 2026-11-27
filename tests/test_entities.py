"""Entities follow the card path, and a write is POST /api/control."""

import pytest
from custom_components.moonlight.const import CONF_EXPERT_MODE, DOMAIN
from custom_components.moonlight.exceptions import MoonLightCommandError, MoonLightExpertError
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.helpers import entity_registry as er

from .conftest import HOST, MAC, PORT, control_posts, mock_control, state
from .test_init import PIPELINE, _setup


def _entity_id(hass, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


async def test_nested_controls_use_the_card_path(hass, aioclient_mock) -> None:
    """Pulse's controls are on the Effects device, named by the cards above them."""
    await _setup(hass, aioclient_mock, options=PIPELINE)
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
    await _setup(hass, aioclient_mock, options=PIPELINE)
    entry = er.async_get(hass).async_get_entity_id("number", DOMAIN, f"{MAC}_Pulse_advanced")
    assert entry is not None
    assert er.async_get(hass).async_get(entry).disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_unknown_password_and_light_controls_are_absent(hass, aioclient_mock) -> None:
    """A future type and a password are skipped. The light owns the desk's first channel."""
    await _setup(hass, aioclient_mock, options=PIPELINE)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{MAC}_Pulse_future") is None
    assert registry.async_get_entity_id("text", DOMAIN, f"{MAC}_Pulse_secret") is None
    assert registry.async_get_entity_id("switch", DOMAIN, f"{MAC}_Control_switch1") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{MAC}_Control_fader1") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{MAC}_Control_encoder1") is None
    assert registry.async_get_entity_id("switch", DOMAIN, f"{MAC}_Drivers_on") is not None


async def test_number_write_is_a_post(hass, aioclient_mock, moonlight_ws) -> None:
    """A slider write is POST /api/control, and the state moves before the next patch."""
    await _setup(hass, aioclient_mock, options=PIPELINE)
    mock_control(aioclient_mock)
    speed = _entity_id(hass, "number", f"{MAC}_Pulse_speed")
    await hass.services.async_call(
        NUMBER_DOMAIN,
        "set_value",
        {ATTR_ENTITY_ID: speed, "value": 40},
        blocking=True,
    )
    assert {"module": "Pulse", "control": "speed", "value": 40} in control_posts(aioclient_mock)
    assert {"module": "Pulse", "control": "speed", "value": 40} not in moonlight_ws.sent
    assert hass.states.get(speed).state == "40.0"


async def test_a_stale_document_does_not_undo_a_write(hass, aioclient_mock, moonlight_ws) -> None:
    """Enabled stays off when a document still carries the value from before the POST."""
    await _setup(hass, aioclient_mock)
    mock_control(aioclient_mock)
    enabled = _entity_id(hass, "switch", f"{MAC}_Control_enabled")
    assert hass.states.get(enabled).state == "on"
    assert hass.states.get(enabled).attributes["control"] == "enabled"
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: enabled}, blocking=True)
    assert {"module": "Control", "control": "enabled", "value": False} in control_posts(aioclient_mock)
    moonlight_ws.feed({"patch": [{"path": "Control/enabled", "value": True}]})
    await hass.async_block_till_done()
    assert hass.states.get(enabled).state == "off"
    moonlight_ws.feed({"patch": [{"path": "Control/enabled", "value": False}]})
    await hass.async_block_till_done()
    moonlight_ws.feed({"patch": [{"path": "Control/enabled", "value": True}]})
    await hass.async_block_till_done()
    assert hass.states.get(enabled).state == "on"


async def test_a_held_write_yields_when_the_device_keeps_its_value(hass, aioclient_mock, moonlight_ws) -> None:
    """A value the device still has after the hold window is the value shown."""
    await _setup(hass, aioclient_mock)
    mock_control(aioclient_mock)
    enabled = _entity_id(hass, "switch", f"{MAC}_Control_enabled")
    await hass.services.async_call("switch", "turn_off", {ATTR_ENTITY_ID: enabled}, blocking=True)
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    written, previous, _at = coordinator._held[("Control", "enabled")]
    coordinator._held[("Control", "enabled")] = (written, previous, 0.0)
    moonlight_ws.feed({"patch": [{"path": "Control/enabled", "value": True}]})
    await hass.async_block_till_done()
    assert hass.states.get(enabled).state == "on"


async def test_out_of_range_is_the_device_sentence(hass, aioclient_mock) -> None:
    """A value outside min and max fails before a frame is sent."""
    await _setup(hass, aioclient_mock, options=PIPELINE)
    with pytest.raises(MoonLightCommandError, match="value out of range"):
        await hass.config_entries.async_entries(DOMAIN)[0].runtime_data.async_set_control("Pulse", "speed", 0)


async def test_a_patch_moves_the_number(hass, aioclient_mock, moonlight_ws) -> None:
    """A patch from the device updates the entity."""
    await _setup(hass, aioclient_mock, options=PIPELINE)
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
    entry = await _setup(hass, aioclient_mock, state_body=body, options=PIPELINE)
    entity_id = _entity_id(hass, "button", f"{MAC}_System_factory reset")
    assert entity_id is not None
    assert er.async_get(hass).async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    with pytest.raises(MoonLightExpertError):
        await entry.runtime_data.async_set_control("System", "factory reset", 1)
    assert not any(
        isinstance(item, dict) and item.get("control") == "factory reset" for item in moonlight_ws.sent
    )
    hass.config_entries.async_update_entry(entry, options={**PIPELINE, CONF_EXPERT_MODE: True})
    await hass.async_block_till_done()
    aioclient_mock.post(f"http://{HOST}:{PORT}/api/control", json={"ok": True})
    await entry.runtime_data.async_set_control("System", "factory reset", 1)
    sent = {"module": "System", "control": "factory reset", "value": 1} in moonlight_ws.sent
    posted = any(
        call[2] == {"module": "System", "control": "factory reset", "value": 1}
        for call in aioclient_mock.mock_calls
        if str(call[0]).lower() == "post"
    )
    assert sent or posted


async def test_status_sensor_carries_severity(hass, aioclient_mock) -> None:
    """The card's status line is a sensor, and severity rides as an attribute."""
    await _setup(hass, aioclient_mock, options=PIPELINE)
    status = _entity_id(hass, "sensor", f"{MAC}_Layer_@status")
    state = hass.states.get(status)
    assert state.state == "running"
    assert state.attributes["severity"] == "status"


async def test_control_desk_follows_declaration_order(hass, aioclient_mock) -> None:
    """Display, then switches, encoders and faders. An empty slot is unavailable."""
    entry = await _setup(hass, aioclient_mock)
    numbers = [control.name for control in entry.runtime_data.controls_for("number")]
    assert numbers == ["encoder2", "fader2"]
    switches = [control.name for control in entry.runtime_data.controls_for("switch")]
    assert switches == ["switch2", "enabled"]
    sensors = [control.name for control in entry.runtime_data.controls_for("sensor")]
    assert sensors == ["display"]
    fader = _entity_id(hass, "number", f"{MAC}_Control_fader2")
    assert hass.states.get(fader).state == "40.0"
    assert hass.states.get(fader).name.endswith("3 Fader 2 · Speed")
    switch = _entity_id(hass, "switch", f"{MAC}_Control_switch2")
    assert hass.states.get(switch).state == "unavailable"
    assert hass.states.get(switch).name.endswith("1 Switch 2")
    display = _entity_id(hass, "sensor", f"{MAC}_Control_display")
    assert hass.states.get(display).state == "MoonLight"
    assert hass.states.get(display).attributes["control"] == "display"
    fader_state = hass.states.get(fader)
    assert fader_state.attributes["module"] == "Control"
    assert fader_state.attributes["control"] == "fader2"
