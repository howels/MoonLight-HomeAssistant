"""Setup, the socket, and the side-nav devices."""

import aiohttp
from custom_components.moonlight.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import HOST, MAC, PORT, mock_device, state


async def _setup(hass, aioclient_mock):
    mock_device(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST, CONF_PORT: PORT}, unique_id=MAC)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_subscribes_and_orders_devices_like_the_nav(hass, aioclient_mock, moonlight_ws) -> None:
    """The socket subscribes to the whole tree, and the devices are the side-nav roots."""
    entry = await _setup(hass, aioclient_mock)
    assert {"subscribe": ["*"]} in moonlight_ws.sent
    assert entry.runtime_data.connected is True
    registry = dr.async_get(hass)
    endpoint = registry.async_get_device_by_identifier((DOMAIN, MAC), entry.entry_id)
    assert endpoint is not None
    assert endpoint.name == "MM-abcd"
    for root in ("Control", "Layouts", "Effects", "Drivers", "System"):
        device = registry.async_get_child_device_by_identifier((DOMAIN, f"{MAC}_{root}"), entry.entry_id)
        assert device is not None
        assert device.parent_device_id == endpoint.id
    assert registry.async_get_child_device_by_identifier((DOMAIN, f"{MAC}_Pulse"), entry.entry_id) is None


async def test_older_firmware_keeps_commands_on_http(hass, aioclient_mock, moonlight_ws) -> None:
    """A tree that arrives before any subscription is older firmware. A control is an HTTP post."""
    moonlight_ws.feed(state())
    entry = await _setup(hass, aioclient_mock)
    assert not any(isinstance(item, dict) and "subscribe" in item for item in moonlight_ws.sent)
    assert entry.runtime_data._commands_on_socket is False
    aioclient_mock.post(f"http://{HOST}:{PORT}/api/control", json={"ok": True})
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
    assert {"module": "Pulse", "control": "speed", "value": 40} not in moonlight_ws.sent
    posted = [
        call[2]
        for call in aioclient_mock.mock_calls
        if str(call[0]).lower() == "post" and str(call[1]).endswith("/api/control")
    ]
    assert {"module": "Pulse", "control": "speed", "value": 40} in posted


async def test_setup_is_not_ready_when_the_host_is_down(hass, aioclient_mock) -> None:
    """A host that does not answer leaves the entry to be retried."""
    aioclient_mock.get(
        f"http://{HOST}:{PORT}/api/system",
        exc=aiohttp.ClientConnectionError("refused"),
    )
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST, CONF_PORT: PORT}, unique_id=MAC)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_unload_closes_the_socket(hass, aioclient_mock, moonlight_ws) -> None:
    """Unload closes the socket."""
    entry = await _setup(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert moonlight_ws.closed is True


async def test_a_dropped_socket_marks_entities_unavailable(hass, aioclient_mock, moonlight_ws) -> None:
    """A close makes the light unavailable and the Connected sensor off."""
    await _setup(hass, aioclient_mock)
    state = hass.states.get("light.mm_abcd_drivers_light")
    assert state is not None
    assert state.state == "on"
    moonlight_ws.feed_close()
    await hass.async_block_till_done()
    assert hass.states.get("light.mm_abcd_drivers_light").state == "unavailable"
    assert hass.states.get("binary_sensor.mm_abcd_connected").state == "off"
