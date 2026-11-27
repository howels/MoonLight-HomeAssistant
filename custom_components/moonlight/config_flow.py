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
from .const import (
    CONF_EXPERT_MODE,
    CONF_SHOW_DEVICES,
    CONF_SHOW_DRIVERS,
    CONF_SHOW_EFFECTS,
    CONF_SHOW_FILES,
    CONF_SHOW_FIRMWARE,
    CONF_SHOW_LAYOUTS,
    CONF_SHOW_NETWORK,
    CONF_SHOW_OTHER,
    CONF_SHOW_SERVICES,
    CONF_SHOW_SYSTEM,
    CONF_TLS,
    DEFAULT_PORT,
    DOMAIN,
)
from .exceptions import MoonLightConnectionError, MoonLightError, MoonLightResponseError
from .models import require_mac, supplement_system

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
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
        self._tls: bool = False
        self._name: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The address typed by hand. A board is port 80. A computer is port 8080."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_probe(user_input[CONF_HOST], user_input.get(CONF_PORT))
            if isinstance(result, str):
                errors["base"] = result
            else:
                host, port, tls, system = result
                await self.async_set_unique_id(format_mac(system["mac"]))
                self._abort_if_unique_id_configured(updates=_address(host, port, tls))
                return await self._async_offer(host, port, tls, system)
        return self.async_show_form(step_id="user", data_schema=_SCHEMA, errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """A device announcing `_http._tcp` with TXT `mm=1`, which every MoonLight board does."""
        host = discovery_info.host
        port = discovery_info.port or DEFAULT_PORT
        result = await self._async_probe(host, port)
        if isinstance(result, str):
            return self.async_abort(reason=result)
        self._host, self._port, self._tls, system = result
        await self.async_set_unique_id(format_mac(system["mac"]))
        self._abort_if_unique_id_configured(updates=_address(self._host, self._port, self._tls))
        self._name = _title(system, self._host)
        self.context["title_placeholders"] = {"name": self._name}
        if self._wled_conflict(self._host, format_mac(system["mac"])):
            return await self.async_step_wled()
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask before adding a discovered device."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data=_address(self._host or "", self._port, self._tls),
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
            result = await self._async_probe(user_input[CONF_HOST], user_input.get(CONF_PORT))
            if isinstance(result, str):
                errors["base"] = result
            else:
                host, port, tls, system = result
                await self.async_set_unique_id(format_mac(system["mac"]))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry,
                    title=_title(system, host),
                    data_updates=_address(host, port, tls),
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
        self, host: str, port: int | None
    ) -> tuple[str, int, bool, dict[str, Any]] | str:
        """Return the checked address and the device identity, or a flow error key."""
        parsed = parse_address(host, port)
        if isinstance(parsed, str):
            return parsed
        host, port, tls = parsed
        client = MoonLightClient(async_get_clientsession(self.hass), host, port, tls=tls)
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
        return host, port, tls, system

    async def _async_offer(
        self, host: str, port: int, tls: bool, system: dict[str, Any]
    ) -> ConfigFlowResult:
        """Create the entry. A board also advertises the service Home Assistant's WLED integration browses."""
        mac = system.get("mac")
        if isinstance(mac, str) and self._wled_conflict(host, format_mac(mac)):
            self._host = host
            self._port = port
            self._tls = tls
            self._name = _title(system, host)
            return await self.async_step_wled()
        return self._async_create(host, port, tls, system)

    async def async_step_wled(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The same board is already a WLED device. Adding it here as well is still allowed."""
        if user_input is not None:
            return self._async_create(self._host or "", self._port, self._tls, {"name": self._name})
        return self.async_show_form(
            step_id="wled",
            description_placeholders={"host": self._host or ""},
        )

    def _wled_conflict(self, host: str, mac: str) -> bool:
        """True when the WLED integration already has this host or this MAC.

        MoonLight advertises `_wled._tcp` as well as `_http._tcp`, so Home Assistant
        offers the device to both integrations.
        """
        for entry in self.hass.config_entries.async_entries("wled"):
            if entry.data.get(CONF_HOST) == host:
                return True
            unique_id = entry.unique_id
            if not isinstance(unique_id, str) or not unique_id:
                continue
            try:
                if format_mac(unique_id) == mac:
                    return True
            except ValueError:
                continue
        return False

    def _async_create(self, host: str, port: int, tls: bool, system: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(title=_title(system, host), data=_address(host, port, tls))


def _address(host: str, port: int, tls: bool) -> dict[str, Any]:
    """The address stored on the config entry. `tls` is false for a plain http device."""
    return {CONF_HOST: host, CONF_PORT: port, CONF_TLS: tls}


def _option(options: dict[str, Any], key: str) -> bool:
    return options.get(key) is True


class MoonLightOptionsFlow(OptionsFlow):
    """Which pages to show, and Expert mode. Control is always shown."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pages default off. Expert mode defaults off."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SHOW_LAYOUTS, default=_option(options, CONF_SHOW_LAYOUTS)): bool,
                    vol.Required(CONF_SHOW_EFFECTS, default=_option(options, CONF_SHOW_EFFECTS)): bool,
                    vol.Required(CONF_SHOW_DRIVERS, default=_option(options, CONF_SHOW_DRIVERS)): bool,
                    vol.Required(CONF_SHOW_SYSTEM, default=_option(options, CONF_SHOW_SYSTEM)): bool,
                    vol.Required(CONF_SHOW_FILES, default=_option(options, CONF_SHOW_FILES)): bool,
                    vol.Required(CONF_SHOW_NETWORK, default=_option(options, CONF_SHOW_NETWORK)): bool,
                    vol.Required(CONF_SHOW_DEVICES, default=_option(options, CONF_SHOW_DEVICES)): bool,
                    vol.Required(CONF_SHOW_SERVICES, default=_option(options, CONF_SHOW_SERVICES)): bool,
                    vol.Required(CONF_SHOW_FIRMWARE, default=_option(options, CONF_SHOW_FIRMWARE)): bool,
                    vol.Required(CONF_SHOW_OTHER, default=_option(options, CONF_SHOW_OTHER)): bool,
                    vol.Required(CONF_EXPERT_MODE, default=_option(options, CONF_EXPERT_MODE)): bool,
                }
            ),
        )


def _title(system: dict[str, Any], host: str) -> str:
    name = system.get("name")
    if isinstance(name, str) and name:
        return name
    return host
