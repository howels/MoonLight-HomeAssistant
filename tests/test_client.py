"""HTTP errors stay distinct."""

import pytest
from custom_components.moonlight.client import MoonLightClient
from custom_components.moonlight.exceptions import MoonLightCommandError, MoonLightResponseError
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


async def test_system_without_a_mac_is_not_moonlight(hass, aioclient_mock) -> None:
    """A 200 body with no MAC is a response error."""
    aioclient_mock.get(f"http://{HOST}:{PORT}/api/system", json={"name": "other"})
    client = MoonLightClient(async_get_clientsession(hass), HOST, PORT)
    with pytest.raises(MoonLightResponseError, match="not a MoonLight"):
        await client.async_get_system()
