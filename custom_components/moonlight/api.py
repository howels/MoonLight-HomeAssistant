"""The one place that talks to a MoonLight device over its HTTP API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import REQUEST_TIMEOUT, SYSTEM_PATH


class MoonLightError(Exception):
    """The device did not answer, or answered with something other than MoonLight's API."""


async def fetch_system(session: aiohttp.ClientSession, host: str, port: int) -> dict[str, Any]:
    """Read the device's /api/system: its name, MAC, version, board and modules."""
    url = f"http://{host}:{port}{SYSTEM_PATH}"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise MoonLightError(f"{url}: {err}") from err
    if not isinstance(data, dict) or "mac" not in data or "version" not in data:
        raise MoonLightError(f"{url}: not a MoonLight device")
    return data
