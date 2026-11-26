"""Add a MoonLight device: found on the network, or entered by address.

One entry per device, keyed on its MAC, so a later address updates the entry.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .address import parse_address
from .client import MoonLightClient
from .const import CONF_EXPERT_MODE, DEFAULT_PORT, DOMAIN
from .exceptions import MoonLightConnectionError, MoonLightError, MoonLightResponseError
from .models import require_mac, supplement_system

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
    }
)


class MoonLightConfigFlow(ConfigFlow, domain=DOMAIN):
    """One config entry per device."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> MoonLightOptionsFlow:
        """Expert mode. Factory reset and SD card format stay off until this is on."""
        return MoonLightOptionsFlow()

    def __init__(self) -> None:
        """Hold a discovered device between the probe and the confirm step."""
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The address typed by hand. A board is port 80. A computer is port 8080."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_probe(user_input[CONF_HOST], user_input[CONF_PORT])
            if isinstance(result, str):
                errors["base"] = result
            else:
                host, port, system = result
                await self.async_set_unique_id(format_mac(system["mac"]))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self._async_create(host, port, system)
        return self.async_show_form(step_id="user", data_schema=_SCHEMA, errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """A device announcing `_http._tcp` with TXT `mm=1`, which every MoonLight board does."""
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        result = await self._async_probe(host, port)
        if isinstance(result, str):
            return self.async_abort(reason=result)
        self._host, self._port, system = result
        await self.async_set_unique_id(format_mac(system["mac"]))
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host, CONF_PORT: self._port})
        self._name = _title(system, self._host)
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask before adding a discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={CONF_HOST: self._host, CONF_PORT: self._port},
            )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._name or ""},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the address of the device this entry already is. A different MAC is refused."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_probe(user_input[CONF_HOST], user_input[CONF_PORT])
            if isinstance(result, str):
                errors["base"] = result
            else:
                host, port, system = result
                await self.async_set_unique_id(format_mac(system["mac"]))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    title=_title(system, host),
                    data_updates={CONF_HOST: host, CONF_PORT: port},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _SCHEMA,
                user_input
                or {CONF_HOST: entry.data[CONF_HOST], CONF_PORT: entry.data[CONF_PORT]},
            ),
            errors=errors,
        )

    async def _async_probe(
        self, host: str, port: int
    ) -> tuple[str, int, dict[str, Any]] | str:
        """Return the checked address and the device identity, or a flow error key."""
        parsed = parse_address(host, port)
        if isinstance(parsed, str):
            return parsed
        host, port = parsed
        client = MoonLightClient(async_get_clientsession(self.hass), host, port)
        try:
            system = require_mac(
                supplement_system(await client.async_get_system(), await client.async_get_state())
            )
        except MoonLightConnectionError as err:
            _LOGGER.info("MoonLight at %s:%s did not answer: %s", host, port, err)
            return "cannot_connect"
        except MoonLightResponseError as err:
            _LOGGER.info("MoonLight at %s:%s is not a MoonLight device: %s", host, port, err)
            return "invalid_response"
        except MoonLightError as err:
            _LOGGER.info("MoonLight at %s:%s could not be read: %s", host, port, err)
            return "unknown"
        return host, port, system

    def _async_create(self, host: str, port: int, system: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title=_title(system, host), data={CONF_HOST: host, CONF_PORT: port})


class MoonLightOptionsFlow(OptionsFlow):
    """One switch. Off leaves factory reset and SD card format refused."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show Expert mode, default off."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_EXPERT_MODE) is True
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_EXPERT_MODE, default=current): bool}
            ),
        )


def _title(system: dict[str, Any], host: str) -> str:
    name = system.get("name")
    if isinstance(name, str) and name:
        return name
    return host
