"""HTTP errors stay distinct."""

import pytest
from custom_components.moonlight.client import MoonLightClient
from custom_components.moonlight.exceptions import MoonLightCommandError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .conftest import HOST, PORT


async def test_refused_control_uses_the_device_reason(hass, aioclient_mock) -> None:
    """POST /api/control's error string is the exception message."""
    aioclient_mock.post(
        f"http://{HOST}:{PORT}/api/control",
        status=400,
        json={"error": "value out of range"},
    )
    client = MoonLightClient(async_get_clientsession(hass), HOST, PORT)
    with pytest.raises(MoonLightCommandError, match="value out of range"):
        await client.async_set_control("Pulse", "speed", 999)


async def test_https_address_is_requested_with_tls(hass, aioclient_mock) -> None:
    """An https device is read at https://, not at http:// on the same port."""
    aioclient_mock.get(f"https://{HOST}:{PORT}/api/system", json={"name": "MM"})
    client = MoonLightClient(async_get_clientsession(hass), HOST, PORT, tls=True)
    assert await client.async_get_system() == {"name": "MM"}


async def test_system_without_a_mac_is_still_json(hass, aioclient_mock) -> None:
    """v6 `/api/system` has no MAC. The client returns the body and the tree supplies the MAC."""
    aioclient_mock.get(f"http://{HOST}:{PORT}/api/system", json={"fps": 40})
    client = MoonLightClient(async_get_clientsession(hass), HOST, PORT)
    assert await client.async_get_system() == {"fps": 40}
