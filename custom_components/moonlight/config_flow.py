"""Add a MoonLight device: found on the network by zeroconf, or entered by address."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import MoonLightError, fetch_system
from .const import DEFAULT_PORT, DOMAIN


class MoonLightConfigFlow(ConfigFlow, domain=DOMAIN):
    """One config entry per device, keyed on its MAC, so a new address updates the entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The address typed by hand: a board on port 80, a host on 8080."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], user_input[CONF_PORT]
            try:
                system = await fetch_system(async_get_clientsession(self.hass), host, port)
            except MoonLightError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(format_mac(system["mac"]))
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(title=system.get("name") or host, data={CONF_HOST: host, CONF_PORT: port})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str, vol.Required(CONF_PORT, default=DEFAULT_PORT): int}),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """A device announcing `_http._tcp` with TXT `mm=1`, which every MoonLight board does."""
        self._host = discovery_info.host
        self._port = discovery_info.port or DEFAULT_PORT
        try:
            system = await fetch_system(async_get_clientsession(self.hass), self._host, self._port)
        except MoonLightError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(format_mac(system["mac"]))
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._host, CONF_PORT: self._port})
        self._name = system.get("name") or self._host
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask before adding a discovered device."""
        if user_input is not None:
            return self.async_create_entry(title=self._name, data={CONF_HOST: self._host, CONF_PORT: self._port})
        return self.async_show_form(step_id="zeroconf_confirm", description_placeholders={"name": self._name})
