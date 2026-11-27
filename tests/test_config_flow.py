"""Adding a device, by hand and by discovery."""

from ipaddress import IPv4Address

import aiohttp
from custom_components.moonlight.const import DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import HOST, MAC, PORT, mock_device, state, system


async def test_user_creates_an_entry(hass, aioclient_mock) -> None:
    """A host that answers /api/system is added, keyed on its MAC."""
    mock_device(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MM-abcd"
    assert result["result"].unique_id == MAC


async def test_user_reports_a_host_that_does_not_answer(hass, aioclient_mock) -> None:
    """No answer is a connection error, not a claim that the body was wrong."""
    aioclient_mock.get(
        f"http://{HOST}:{PORT}/api/system",
        exc=aiohttp.ClientConnectionError("refused"),
    )
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_connect"


async def test_user_reports_a_host_that_is_not_moonlight(hass, aioclient_mock) -> None:
    """A JSON body without a MAC, and a state with no System card, is not a MoonLight device."""
    aioclient_mock.get(f"http://{HOST}:{PORT}/api/system", json={"ok": True})
    aioclient_mock.get(f"http://{HOST}:{PORT}/api/state", json={"ok": True})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["errors"]["base"] == "invalid_response"


async def test_https_url_uses_port_443(hass, aioclient_mock) -> None:
    """An https URL with a blank port field connects on 443 with TLS."""
    mock_device(aioclient_mock, port=443, scheme="https")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "https://192.0.2.10"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].data[CONF_HOST] == HOST
    assert result["result"].data[CONF_PORT] == 443
    assert result["result"].data["tls"] is True


async def test_port_field_replaces_the_https_default(hass, aioclient_mock) -> None:
    """The port field replaces 443, and the https scheme still selects TLS."""
    mock_device(aioclient_mock, host="moonlight.local", port=8443, scheme="https")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "https://moonlight.local", CONF_PORT: 8443}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].data[CONF_PORT] == 8443
    assert result["result"].data["tls"] is True


async def test_already_configured_updates_the_address(hass, aioclient_mock) -> None:
    """The same MAC updates the existing entry instead of adding a second one."""
    mock_device(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: "192.0.2.20", CONF_PORT: 80}, unique_id=MAC, title="old"
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: 8080}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == HOST
    assert entry.data[CONF_PORT] == 8080


async def test_zeroconf_confirm(hass, aioclient_mock) -> None:
    """A discovered board is shown, then added."""
    mock_device(aioclient_mock)
    address = IPv4Address(HOST)
    info = ZeroconfServiceInfo(
        ip_address=address,
        ip_addresses=[address],
        port=PORT,
        hostname="mm-abcd.local.",
        type="_http._tcp.local.",
        name="MM-abcd._http._tcp.local.",
        properties={"mm": "1"},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "zeroconf_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MM-abcd"


async def test_user_reads_the_mac_from_the_system_card(hass, aioclient_mock) -> None:
    """A v6 `/api/system` has no MAC. The System card does."""
    body = state()
    for module in body["modules"]:
        if module["name"] == "System":
            module["controls"].append(
                {"name": "mac", "type": "text", "value": MAC, "readonly": True}
            )
            module["controls"].append({"name": "deviceName", "type": "text", "value": "Board"})
    mock_device(aioclient_mock, system_body={"fps": 40}, state_body=body)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Board"
    assert result["result"].unique_id == MAC


async def test_expert_mode_is_an_option(hass, aioclient_mock) -> None:
    """Expert mode is off until the options flow turns it on."""
    mock_device(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST, CONF_PORT: PORT}, unique_id=MAC)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "show_layouts": False,
            "show_effects": True,
            "show_drivers": False,
            "show_system": False,
            "show_files": False,
            "show_network": False,
            "show_devices": False,
            "show_services": False,
            "show_firmware": False,
            "show_other": False,
            "expert_mode": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["expert_mode"] is True
    assert entry.options["show_effects"] is True
    assert entry.options["show_system"] is False


async def test_wled_discovery_warns_before_adding(hass, aioclient_mock) -> None:
    """A board also advertises the service the WLED integration browses."""
    mock_device(aioclient_mock)
    wled = MockConfigEntry(domain="wled", data={CONF_HOST: HOST, CONF_PORT: 80}, unique_id=MAC)
    wled.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "wled"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == MAC


async def test_reconfigure_rejects_a_different_device(hass, aioclient_mock) -> None:
    """A new address must be the same MAC."""
    other = system()
    other["mac"] = "bb:bb:cc:dd:ee:ff"
    mock_device(aioclient_mock, system_body=other)
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: HOST, CONF_PORT: PORT}, unique_id=MAC)
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_PORT: PORT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
