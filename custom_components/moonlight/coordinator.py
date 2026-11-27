"""One MoonLight device: the tree, the socket, and the commands.

`async_config_entry_first_refresh` reads the tree over HTTP. A background task then holds
`/ws` open. Patches update the same data object the entities read. A dropped socket marks
the entities unavailable and reconnects. The delay doubles from one second to thirty.

A command is checked locally, then sent with `POST /api/control`. That call returns the
device's refusal. The socket accepts the same object and does not answer it, so a frame
the device drops is a toggle that snaps back when the next document arrives. The web
interface posts a toggle for the same reason. A document that still has the value from
before the write does not move the entity back.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from aiohttp import WSMsgType
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import ChildDeviceInfo, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import MoonLightClient, host_for_url
from .const import (
    CONF_EXPERT_MODE,
    CONF_SHOW_OTHER,
    CONF_TLS,
    DOMAIN,
    HEARTBEAT_SECONDS,
    MANUFACTURER,
    PRESET_CONTROL,
    PRESET_MODULE,
    RETRY_MAX_SECONDS,
    RETRY_MIN_SECONDS,
    SECTION_OPTIONS,
)
from .exceptions import (
    MoonLightCommandError,
    MoonLightConnectionError,
    MoonLightError,
    MoonLightExpertError,
    MoonLightResponseError,
)
from .models import (
    Control,
    Look,
    Module,
    MoonLightData,
    apply_patch,
    coerce_value,
    control_order,
    entity_platform,
    is_destructive,
    nav_roots,
    parse_tree,
    rejection,
    require_mac,
    root_module,
    supplement_system,
    uses_socket_commands,
)

_LOGGER = logging.getLogger(__name__)

type MoonLightConfigEntry = ConfigEntry[MoonLightCoordinator]


class MoonLightCoordinator(DataUpdateCoordinator[MoonLightData]):
    """Holds one device's tree and the task that keeps it live."""

    config_entry: MoonLightConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MoonLightConfigEntry) -> None:
        """Build the client from the config entry. The socket starts after the first read."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.config_entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.port: int = entry.data[CONF_PORT]
        self.tls: bool = entry.data.get(CONF_TLS) is True
        self.client = MoonLightClient(async_get_clientsession(hass), self.host, self.port, tls=self.tls)
        self.mac = ""
        self._ws: Any = None
        self._stop = asyncio.Event()
        self._reported_drop = False
        self._resync_id = 0
        self._task: asyncio.Task[None] | None = None
        self._retry_delay = RETRY_MIN_SECONDS
        self.endpoint_device_id: str | None = None
        # v7.0.0 and later apply {"module","control","value"} on the socket. Older firmware ignores that frame and applies {"ps": slot} instead.
        self._commands_on_socket = False
        # (written value, value before the write). A document still carrying the old one is stale.
        self._held: dict[tuple[str, str], tuple[Any, Any]] = {}

    async def _async_update_data(self) -> MoonLightData:
        """Read identity and the tree. A failure here is retried by Home Assistant."""
        try:
            system = await self.client.async_get_system()
            state = await self.client.async_get_state()
            system = require_mac(supplement_system(system, state))
        except MoonLightConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except MoonLightResponseError as err:
            raise UpdateFailed(str(err)) from err
        parsed = parse_tree(state)
        if parsed is None:
            raise UpdateFailed(f"{self.host}:{self.port} returned /api/state without a module tree.")
        modules, controls, looks, unknown = parsed
        for ctype in sorted(unknown):
            _LOGGER.warning(
                "MoonLight at %s:%s has a control type %s that this integration does not map. "
                "Those controls are skipped.",
                self.host,
                self.port,
                ctype,
            )
        self.mac = dr.format_mac(system["mac"])
        return MoonLightData(
            system=system,
            modules=modules,
            controls=controls,
            looks=looks,
            connected=False,
            unknown_types=set(unknown),
        )

    def async_start(self) -> None:
        """Open the WebSocket and keep it open until unload."""
        self._task = self.config_entry.async_create_background_task(
            self.hass,
            self._async_listen(),
            name=f"moonlight websocket {self.host}",
        )

    async def async_shutdown(self) -> None:
        """Close the socket so unload does not wait out a reconnect delay."""
        self._stop.set()
        ws = self._ws
        self._ws = None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        task = self._task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self._task = None

    async def async_set_control(self, module: str, control: str, value: Any) -> None:
        """Set one control. The local check runs first. `POST /api/control` carries the write."""
        current = self.data.controls.get((module, control))
        if current is None:
            if module not in self.data.modules:
                raise MoonLightCommandError("module not found")
            raise MoonLightCommandError("control not found")
        if is_destructive(current) and not self.expert_mode:
            raise MoonLightExpertError(f"{module} {control}")
        value = coerce_value(current, value)
        reason = rejection(current, value)
        if reason is not None:
            raise MoonLightCommandError(reason)
        previous = current.value
        await self.client.async_set_control(module, control, value)
        # A full document can replace the tree while the POST is in flight. Write the live control.
        live = self.data.controls.get((module, control))
        if live is None:
            live = current
        live.value = value
        if control == "enabled" and isinstance(value, bool):
            found = self.data.modules.get(module)
            if found is not None:
                found.enabled = value
        if previous != value:
            self._held[(module, control)] = (value, previous)
        self.async_set_updated_data(self.data)

    @property
    def expert_mode(self) -> bool:
        """True after the user turns Expert mode on in the integration options."""
        return self.config_entry.options.get(CONF_EXPERT_MODE) is True

    async def async_apply_look(self, name: str, *, refresh: bool = True) -> None:
        """Apply one effect look by its name. The row id is what the device stores.

        `refresh` is false when the caller still has writes to send. A resync that
        lands before those writes puts the old values back.
        """
        look = next((item for item in self.data.looks if item.name == name), None)
        if look is None:
            raise MoonLightCommandError(f"no look named {name}")
        if self._commands_on_socket:
            await self.client.async_apply_list_row(PRESET_MODULE, PRESET_CONTROL, look.row)
        elif look.slot <= 0:
            raise MoonLightCommandError(f"no preset slot for {name}")
        elif not await self._async_send_json({"ps": look.slot}):
            raise MoonLightConnectionError("the WebSocket is down")
        self.data.looks = tuple(
            Look(item.name, item.row, item.name == name, item.slot) for item in self.data.looks
        )
        self.async_set_updated_data(self.data)
        if refresh:
            await self.async_refresh_tree()

    async def async_refresh_tree(self) -> None:
        """Read the tree again. v7.0.0 answers `{"resync": n}`. Older firmware answers `GET /api/state`."""
        if self._commands_on_socket and self._ws is not None and self.data.connected:
            await self._async_request_resync()
            return
        await self._async_reload_tree()

    def section_enabled(self, name: str) -> bool:
        """Control is always shown. Every other side-nav page waits for its option."""
        if name == "Control":
            return True
        key = SECTION_OPTIONS.get(name, CONF_SHOW_OTHER)
        return self.config_entry.options.get(key) is True

    def controls_for(self, platform: str) -> list[Control]:
        """Controls on one platform, in the order the web interface renders them.

        A page whose option is off contributes nothing. The tree is still parsed.
        """
        visible: list[Control] = []
        for control in self.data.controls.values():
            if entity_platform(control) != platform:
                continue
            root = root_module(self.data.modules, control.module)
            if root is None or not self.section_enabled(root.name):
                continue
            visible.append(control)
        return sorted(visible, key=lambda control: control_order(self.data.modules, control))

    def module(self, name: str) -> Module | None:
        """The module with this name, or None after it was removed."""
        return self.data.modules.get(name)

    def control(self, module: str, name: str) -> Control | None:
        """The live control, or None when the device no longer has it."""
        return self.data.controls.get((module, name))

    @property
    def connected(self) -> bool:
        """True while `/ws` is open. The client has sent `{"subscribe":["*"]}`."""
        return bool(self.data and self.data.connected)

    @callback
    def async_device_info(self, module_name: str | None) -> DeviceInfo | ChildDeviceInfo:
        """The endpoint, or the side-nav child device a module's card lives on."""
        if module_name is None or self.endpoint_device_id is None:
            system = self.data.system
            board = system.get("board")
            version = system.get("version")
            chip = system.get("chip")
            return DeviceInfo(
                identifiers={(DOMAIN, self.mac)},
                connections={(dr.CONNECTION_NETWORK_MAC, self.mac)},
                manufacturer=MANUFACTURER,
                model=board if isinstance(board, str) else "MoonLight",
                name=self._device_name(),
                sw_version=version if isinstance(version, str) else None,
                hw_version=chip if isinstance(chip, str) else None,
                configuration_url=f"{'https' if self.tls else 'http'}://{host_for_url(self.host)}:{self.port}/",
            )
        root = root_module(self.data.modules, module_name)
        if root is None:
            return self.async_device_info(None)
        return ChildDeviceInfo(
            identifiers={(DOMAIN, f"{self.mac}_{root.name}")},
            name=root.name,
            parent_device_id=self.endpoint_device_id,
        )

    @callback
    def async_sync_devices(self) -> None:
        """Create the endpoint and one child device per side-nav root. Remove a root that has gone.

        Child cards are not devices. Their controls are entities on the root, named by the
        path of cards, which is how the web UI nests them inside the selected root.
        """
        if not self.mac:
            return
        registry = dr.async_get(self.hass)
        entry_id = self.config_entry.entry_id
        endpoint = registry.async_get_or_create(
            config_entry_id=entry_id,
            **_device_kwargs(self.async_device_info(None)),
        )
        self.endpoint_device_id = endpoint.id
        alive: set[tuple[str, str]] = set()
        for module in nav_roots(self.data.modules):
            if not self.section_enabled(module.name):
                continue
            identifier = (DOMAIN, f"{self.mac}_{module.name}")
            alive.add(identifier)
            registry.async_get_or_create_child(
                config_entry_id=entry_id,
                identifiers={identifier},
                name=module.name,
                parent_device_id=endpoint.id,
            )
        for device in dr.async_entries_for_config_entry(registry, entry_id):
            if device.identifiers.isdisjoint({(DOMAIN, self.mac)}):
                registry.async_update_device(device.id, remove_config_entry_id=entry_id)
        for child in dr.async_child_entries_for_config_entry(registry, entry_id):
            if child.identifiers.isdisjoint(alive):
                registry.async_remove_device(child.id)

    async def _async_listen(self) -> None:
        """Hold `/ws` open. One failure waits, then the next attempt starts clean."""
        while not self._stop.is_set():
            await self._async_note_firmware()
            try:
                ws = await self.client.ws_connect(
                    heartbeat=HEARTBEAT_SECONDS if self._commands_on_socket else None
                )
            except MoonLightError as err:
                self._async_fail(err)
            else:
                self._ws = ws
                try:
                    await ws.send_json({"subscribe": ["*"]})
                    if not self._commands_on_socket:
                        reported = self.data.system.get("version")
                        _LOGGER.info(
                            "MoonLight at %s:%s reports version %s. Commands go over HTTP.",
                            self.host,
                            self.port,
                            reported if isinstance(reported, str) and reported else "unknown",
                        )
                    self._async_set_connected(True)
                    self._retry_delay = RETRY_MIN_SECONDS
                    async for message in ws:
                        if self._stop.is_set():
                            break
                        await self._async_handle(ws, message)
                except asyncio.CancelledError:
                    raise
                except MoonLightError as err:
                    self._async_fail(err)
                except Exception as err:
                    _LOGGER.exception("MoonLight at %s:%s WebSocket failed", self.host, self.port)
                    self._async_fail(err)
                finally:
                    self._ws = None
                    if not self._stop.is_set() and self.data.connected:
                        self._async_fail(MoonLightConnectionError("the socket closed"))
                    with contextlib.suppress(Exception):
                        await ws.close()
            if self._stop.is_set():
                return
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._retry_delay)
                return
            except TimeoutError:
                self._retry_delay = min(self._retry_delay * 2, RETRY_MAX_SECONDS)

    async def _async_note_firmware(self) -> None:
        """Read the version before the socket opens, so an update applies on the next connection.

        `/api/system` carries it from the build after v7.0.0. Before that, `Firmware.version`
        in `/api/state` does. A failed read keeps the version already held.
        """
        try:
            system = await self.client.async_get_system()
        except MoonLightError as err:
            _LOGGER.info(
                "MoonLight at %s:%s did not refresh /api/system (%s). The previous identity is kept.",
                self.host,
                self.port,
                err,
            )
        else:
            if not _text(system, "version") or not _text(system, "mac"):
                try:
                    state = await self.client.async_get_state()
                except MoonLightError as err:
                    _LOGGER.info(
                        "MoonLight at %s:%s did not refresh /api/state (%s). The previous identity is kept.",
                        self.host,
                        self.port,
                        err,
                    )
                    state = None
                system = supplement_system(system, state)
            if _text(system, "mac"):
                if not _text(system, "version"):
                    previous = self.data.system.get("version")
                    if isinstance(previous, str) and previous:
                        system["version"] = previous
                self.data.system = system
                self.mac = dr.format_mac(system["mac"])
                self.async_sync_devices()
        self._commands_on_socket = uses_socket_commands(self.data.system.get("version"))

    async def _async_handle(self, ws: Any, message: Any) -> None:
        """One inbound frame. A `{state, info}` compatibility frame is ignored."""
        if message.type != WSMsgType.TEXT:
            if message.type in {WSMsgType.CLOSED, WSMsgType.CLOSING, WSMsgType.ERROR}:
                detail = "the socket closed"
                if message.type is WSMsgType.ERROR:
                    detail = f"the socket failed ({message.data})"
                raise MoonLightConnectionError(detail)
            return
        try:
            payload = message.json()
        except ValueError:
            _LOGGER.warning(
                "MoonLight at %s:%s sent a WebSocket frame that is not JSON. The frame was ignored.",
                self.host,
                self.port,
            )
            return
        if not isinstance(payload, dict):
            _LOGGER.warning(
                "MoonLight at %s:%s sent a WebSocket frame that is not an object. The frame was ignored.",
                self.host,
                self.port,
            )
            return
        if isinstance(payload.get("modules"), list):
            self._replace_tree(payload)
            return
        if "patch" in payload:
            if apply_patch(self.data, payload.get("patch")):
                _LOGGER.info(
                    "MoonLight at %s:%s sent a patch for a control that is not in the tree. "
                    "Asking for the tree again.",
                    self.host,
                    self.port,
                )
                await self.async_refresh_tree()
            else:
                self._apply_held()
                self.async_set_updated_data(self.data)
            return
        if "state" in payload and "info" in payload:
            return
        _LOGGER.debug(
            "MoonLight at %s:%s sent a WebSocket message with keys %s. It was ignored.",
            self.host,
            self.port,
            sorted(payload)[:6],
        )

    def _replace_tree(self, payload: dict[str, Any]) -> None:
        """Install a full document. An empty document keeps the tree already held."""
        parsed = parse_tree(payload)
        if parsed is None:
            _LOGGER.error(
                "MoonLight at %s:%s sent a state document with no modules. The previous tree is unchanged.",
                self.host,
                self.port,
            )
            self.data.last_error = "state document with no modules"
            self.async_set_updated_data(self.data)
            return
        modules, controls, looks, unknown = parsed
        seen = self.data.unknown_types
        for ctype in sorted(unknown - seen):
            _LOGGER.warning(
                "MoonLight at %s:%s has a control type %s that this integration does not map. "
                "Those controls are skipped.",
                self.host,
                self.port,
                ctype,
            )
        self.data.modules = modules
        self.data.controls = controls
        self.data.looks = looks
        self.data.unknown_types.update(unknown)
        self.data.last_error = None
        self._apply_held()
        self.async_set_updated_data(self.data)
        self.async_sync_devices()
        name = self._device_name()
        if name and self.config_entry.title != name:
            self.hass.config_entries.async_update_entry(self.config_entry, title=name)

    async def _async_reload_tree(self) -> None:
        """Read `/api/state` again. Older firmware has no `resync` frame."""
        try:
            state = await self.client.async_get_state()
        except MoonLightError as err:
            _LOGGER.info(
                "MoonLight at %s:%s did not refresh /api/state (%s).",
                self.host,
                self.port,
                err,
            )
            return
        self._replace_tree(state)

    async def _async_send_json(self, payload: dict[str, Any]) -> bool:
        """Send one object on the open socket. False when the socket cannot take it."""
        ws = self._ws
        if ws is None or not self.data.connected:
            return False
        try:
            await ws.send_json(payload)
        except (ConnectionError, RuntimeError, MoonLightError) as err:
            _LOGGER.info(
                "MoonLight at %s:%s did not take a WebSocket write (%s).",
                self.host,
                self.port,
                err,
            )
            return False
        return True

    def _apply_held(self) -> None:
        """Keep a write that the device has accepted when a document still has the old value.

        The next document that carries the written value confirms it. A different value is a
        later change, from the device or from another client, and it stands.
        """
        finished: list[tuple[str, str]] = []
        for key, (new, old) in self._held.items():
            live = self.data.controls.get(key)
            if live is None or live.value != old:
                finished.append(key)
                continue
            live.value = new
            if key[1] == "enabled" and isinstance(new, bool):
                found = self.data.modules.get(key[0])
                if found is not None:
                    found.enabled = new
        for key in finished:
            self._held.pop(key, None)

    async def _async_request_resync(self, ws: Any | None = None) -> None:
        """Ask the device for the tree. The answer is a full document carrying this id."""
        socket = self._ws if ws is None else ws
        if socket is None or not self.data.connected:
            return
        self._resync_id += 1
        with contextlib.suppress(ConnectionError, RuntimeError, MoonLightError):
            await socket.send_json({"resync": self._resync_id})

    @callback
    def _async_set_connected(self, connected: bool) -> None:
        """Publish the socket state. The connectivity sensor and every control read it."""
        if self.data.connected == connected:
            return
        self.data.connected = connected
        if connected:
            self.data.last_error = None
            self._reported_drop = False
            _LOGGER.info("MoonLight at %s:%s WebSocket connected.", self.host, self.port)
        self.async_set_updated_data(self.data)

    @callback
    def _async_fail(self, err: BaseException) -> None:
        """Record one socket failure. The warning is once per outage, not once per retry."""
        message = str(err) or err.__class__.__name__
        self.data.last_error = message
        if not self._reported_drop:
            _LOGGER.warning(
                "MoonLight at %s:%s WebSocket is down: %s. Entities are unavailable until it reconnects.",
                self.host,
                self.port,
                message,
            )
            self._reported_drop = True
        else:
            _LOGGER.debug("MoonLight at %s:%s WebSocket still down: %s", self.host, self.port, message)
        self._async_set_connected(False)

    def _device_name(self) -> str:
        name = self.data.system.get("name")
        if isinstance(name, str) and name:
            return name
        return self.config_entry.title or self.host


def _device_kwargs(info: DeviceInfo) -> dict[str, Any]:
    """`async_get_or_create` takes the device fields as keyword arguments."""
    return dict(info)


def _text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None
