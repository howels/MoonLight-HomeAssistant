"""HTTP and WebSocket client for one MoonLight device.

Setup reads `/api/system` and `/api/state`. The MAC and the version are taken from
`/api/system` when it has them, and from the System and Firmware cards when it does not.
After that the WebSocket at `/ws` carries the live tree. From v7.0.0 a command uses the
socket when it is open. Older firmware ignores that frame, so the command is
`POST /api/control`, which is also how a refusal is read back: the socket does not
answer a write.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import REQUEST_TIMEOUT, WEBSOCKET_MAX_BYTES
from .exceptions import MoonLightCommandError, MoonLightConnectionError, MoonLightResponseError

_COMMAND_STATUS = frozenset({400, 404, 409, 413})


def host_for_url(host: str) -> str:
    """Bracket an IPv6 address so it can sit in an `http://` URL."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


class MoonLightClient:
    """One device, reached through Home Assistant's shared aiohttp session."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, *, tls: bool = False) -> None:
        """Store the address. The session outlives this client.

        `tls` selects `https` and `wss`. An entry added before TLS was stored leaves it false.
        """
        self._session = session
        self.host = host
        self.port = port
        self.tls = tls

    def _url(self, path: str) -> str:
        scheme = "https" if self.tls else "http"
        return f"{scheme}://{host_for_url(self.host)}:{self.port}{path}"

    async def _async_request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        """Perform one HTTP call and return the JSON body.

        A connection failure and a body that is not MoonLight's API are different errors,
        so the config flow can say which one the user hit.
        """
        url = self._url(path)
        try:
            async with self._session.request(
                method,
                url,
                json=body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                text = await response.text()
                status = response.status
        except TimeoutError as err:
            raise MoonLightConnectionError(
                f"{self.host}:{self.port} did not answer within {REQUEST_TIMEOUT} seconds"
            ) from err
        except aiohttp.ClientError as err:
            raise MoonLightConnectionError(f"{self.host}:{self.port} is unreachable ({err})") from err
        try:
            payload: Any = json.loads(text) if text else {}
        except ValueError as err:
            raise MoonLightResponseError(f"{path} returned a body that is not JSON") from err
        if status >= 400:
            message = payload.get("error") if isinstance(payload, dict) else None
            detail = message if isinstance(message, str) and message else f"HTTP {status}"
            if status in _COMMAND_STATUS and isinstance(message, str) and message:
                raise MoonLightCommandError(message)
            if status >= 500:
                raise MoonLightConnectionError(f"{path} returned {detail}")
            raise MoonLightResponseError(f"{path} returned {detail}")
        if payload is not None and not isinstance(payload, dict):
            raise MoonLightResponseError(f"{path} returned JSON that is not an object")
        return payload

    async def async_get_system(self) -> dict[str, Any]:
        """`GET /api/system`. v6.0.0 and v7.0.0 omit `mac` and `version` here."""
        payload = await self._async_request("GET", "/api/system")
        if not isinstance(payload, dict):
            raise MoonLightResponseError("/api/system returned JSON that is not an object")
        return payload

    async def async_get_state(self) -> dict[str, Any]:
        """`GET /api/state`, the module tree with its controls."""
        payload = await self._async_request("GET", "/api/state")
        modules = payload.get("modules") if isinstance(payload, dict) else None
        if not isinstance(modules, list) or not modules:
            raise MoonLightResponseError(
                "/api/state has no modules. The device answered, but not with a MoonLight tree."
            )
        return payload

    async def async_set_control(self, module: str, control: str, value: Any) -> None:
        """`POST /api/control`. Raises `MoonLightCommandError` with the device's reason."""
        await self._async_request(
            "POST",
            "/api/control",
            {"module": module, "control": control, "value": value},
        )

    async def async_apply_list_row(self, module: str, control: str, row: str) -> None:
        """`POST /api/list/<module>/<control>/<row>/apply`. `row` is the stable id or the name."""
        path = (
            f"/api/list/{quote(module, safe='')}/{quote(control, safe='')}/"
            f"{quote(row, safe='')}/apply"
        )
        await self._async_request("POST", path)

    async def ws_connect(self, *, heartbeat: float | None) -> aiohttp.ClientWebSocketResponse:
        """Open `/ws`. `heartbeat` is set only when this firmware answers a ping."""
        try:
            scheme = "wss" if self.tls else "ws"
            return await self._session.ws_connect(
                f"{scheme}://{host_for_url(self.host)}:{self.port}/ws",
                heartbeat=heartbeat,
                timeout=REQUEST_TIMEOUT,
                max_msg_size=WEBSOCKET_MAX_BYTES,
            )
        except TimeoutError as err:
            raise MoonLightConnectionError(
                f"WebSocket to {self.host}:{self.port} did not open within {REQUEST_TIMEOUT} seconds"
            ) from err
        except aiohttp.ClientError as err:
            raise MoonLightConnectionError(
                f"WebSocket to {self.host}:{self.port} did not open ({err})"
            ) from err
