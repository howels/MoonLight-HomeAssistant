"""Live wiring against one MoonLight device.

Set ``MOONLIGHT_URL`` to an origin such as ``http://moonlight.local``. The test
skips when it is unset, so CI does not need a device. It reads the tree through
``MoonLightClient``, maps every control with the same functions the entities use,
posts one reversible desk write and the Control enabled flag, and checks the
socket echoes each. Both values are restored before the test returns.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
from collections import Counter

import aiohttp
import pytest
import pytest_socket
from aiohttp import WSMsgType
from custom_components.moonlight.address import parse_address
from custom_components.moonlight.client import MoonLightClient
from custom_components.moonlight.const import HEARTBEAT_SECONDS, LIGHT_CONTROLS
from custom_components.moonlight.models import (
    entity_name,
    entity_platform,
    parse_tree,
    uses_socket_commands,
)
from pytest_homeassistant_custom_component.plugins import _real_getaddrinfo

# Captured before the suite's autouse fixture replaces it with the fake socket.
_REAL_WS_CONNECT = MoonLightClient.ws_connect

_ECHO_SECONDS = 8.0


def test_live_device_wiring() -> None:
    """The device, the parser and a restored write. Skipped without ``MOONLIGHT_URL``."""
    url = os.environ.get("MOONLIGHT_URL")
    if not url:
        pytest.skip("Set MOONLIGHT_URL to an http or https MoonLight origin. docs/build.md has the command.")
    parsed = parse_address(url, None)
    if isinstance(parsed, str):
        pytest.fail(f"MOONLIGHT_URL is not an origin ({parsed})")
    # The Home Assistant test plugin blocks sockets, connect and DNS. This test is the exception.
    pytest_socket._remove_restrictions()
    socket.getaddrinfo = _real_getaddrinfo
    MoonLightClient.ws_connect = _REAL_WS_CONNECT
    asyncio.run(_run(*parsed))


async def _run(host: str, port: int, tls: bool) -> None:
    lines: list[str] = []
    async with aiohttp.ClientSession() as session:
        client = MoonLightClient(session, host, port, tls=tls)
        system = await client.async_get_system()
        version = system.get("version")
        mac = system.get("mac")
        lines.append(f"system version={version} mac={mac}")
        assert isinstance(mac, str) and mac, "GET /api/system did not report a mac"
        assert isinstance(version, str) and version, "GET /api/system did not report a version"
        state = await client.async_get_state()
        parsed = parse_tree(state)
        assert parsed is not None, "GET /api/state did not parse"
        modules, controls, looks, unknown = parsed
        _report_tree(lines, modules, controls, looks, unknown)
        for key in LIGHT_CONTROLS:
            assert key in controls, f"the light channel {key[1]} is missing"
        heartbeat = HEARTBEAT_SECONDS if uses_socket_commands(version) else None
        async with await client.ws_connect(heartbeat=heartbeat) as socket:
            await socket.send_json({"subscribe": ["*"]})
            first = await _next_tree(socket, _ECHO_SECONDS)
            assert first == "modules", "the socket did not send a module tree after subscribe"
            lines.append("socket subscribed")
            desk = _desk_switch(controls)
            assert desk is not None, "no assigned Control switch to write and restore"
            new = not desk.value
            await _round_trip(client, socket, desk.module, desk.name, desk.value, new, lines)
            enabled = controls.get(("Control", "enabled"))
            assert enabled is not None and isinstance(enabled.value, bool), "Control.enabled is missing"
            await _round_trip(client, socket, "Control", "enabled", enabled.value, not enabled.value, lines)
    print("\n".join(lines))


def _report_tree(lines: list[str], modules, controls, looks, unknown) -> None:
    counts: Counter[str] = Counter()
    skipped = 0
    for control in controls.values():
        entity_name(modules, control)
        platform = entity_platform(control)
        if platform is None:
            skipped += 1
        else:
            counts[platform] += 1
    mapped = " ".join(f"{name}={counts[name]}" for name in sorted(counts))
    lines.append(
        f"modules={len(modules)} controls={len(controls)} looks={len(looks)} "
        f"mapped {mapped} skipped={skipped} unknown={','.join(sorted(unknown)) or 'none'}"
    )


def _desk_switch(controls):
    """An assigned desk switch that is not the light's power channel."""
    for index in range(2, 9):
        control = controls.get(("Control", f"switch{index}"))
        if control is None or control.type != "bool" or not isinstance(control.value, bool):
            continue
        if not control.assigned:
            continue
        return control
    return None


async def _round_trip(client, socket, module: str, control: str, previous, new, lines: list[str]) -> None:
    changed = False
    try:
        await client.async_set_control(module, control, new)
        changed = True
        live = await _read_value(client, module, control)
        assert live == new, f"POST {module}.{control} left {live}, expected {new}"
        echo = await _echo(socket, module, control, new)
        lines.append(f"write {module}.{control} {previous!r} -> {new!r} echoed by {echo}")
    finally:
        if changed:
            await client.async_set_control(module, control, previous)
            restored = await _read_value(client, module, control)
            assert restored == previous, f"did not restore {module}.{control} to {previous!r}, it is {restored!r}"
            lines.append(f"restored {module}.{control} to {previous!r}")


async def _read_value(client, module: str, control: str):
    state = await client.async_get_state()
    parsed = parse_tree(state)
    assert parsed is not None
    live = parsed[1].get((module, control))
    assert live is not None, f"{module}.{control} left the tree"
    return live.value


async def _echo(socket, module: str, control: str, value) -> str:
    """The frame that carries the written value: a patch, or a full tree after enabled."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _ECHO_SECONDS
    while loop.time() < deadline:
        message = await asyncio.wait_for(socket.receive(), timeout=deadline - loop.time())
        if message.type != WSMsgType.TEXT:
            continue
        try:
            payload = json.loads(message.data)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        patch = payload.get("patch")
        if isinstance(patch, list):
            path = f"{module}/{control}"
            if any(isinstance(item, dict) and item.get("path") == path and item.get("value") == value for item in patch):
                return "patch"
        if isinstance(payload.get("modules"), list):
            parsed = parse_tree(payload)
            if parsed is not None:
                live = parsed[1].get((module, control))
                if live is not None and live.value == value:
                    return "modules"
    raise AssertionError(f"the socket did not echo {module}.{control}={value!r}")


async def _next_tree(socket, timeout: float) -> str:
    """The first full tree, or the kind of frame that arrived instead."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        message = await asyncio.wait_for(socket.receive(), timeout=deadline - loop.time())
        if message.type != WSMsgType.TEXT:
            continue
        try:
            payload = json.loads(message.data)
        except ValueError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("modules"), list):
            return "modules"
    return "none"
