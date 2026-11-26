"""Shared fixtures. The socket is fake. HTTP is mocked per test."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from custom_components.moonlight.client import MoonLightClient

from .fake_ws import FakeWebSocket

pytest_plugins = "pytest_homeassistant_custom_component"


MAC = "aa:bb:cc:dd:ee:ff"
HOST = "192.0.2.10"
PORT = 80


def system() -> dict[str, Any]:
    """`GET /api/system` for the fixture device."""
    return {
        "name": "MM-abcd",
        "mac": MAC,
        "version": "7.1.0-dev",
        "board": "esp32",
        "chip": "esp32",
        "firmware": "firmware-esp32",
    }


def state() -> dict[str, Any]:
    """A small tree in side-nav order: Control, Layouts, Effects, Drivers, System."""
    return {
        "modules": [
            {
                "name": "Control",
                "type": "ControlModule",
                "role": "generic",
                "enabled": True,
                "controls": [
                    {
                        "name": "presets",
                        "type": "list",
                        "value": [
                            {"id": 1, "name": "Rainbow", "roles": ["effects"], "active": True},
                            {"id": 2, "name": "Pins", "roles": ["driver"], "active": False},
                        ],
                    }
                ],
            },
            {
                "name": "Layouts",
                "type": "Layouts",
                "role": "generic",
                "enabled": True,
                "children": [
                    {
                        "name": "Grid",
                        "type": "GridLayout",
                        "role": "layout",
                        "enabled": True,
                        "controls": [
                            {"name": "width", "type": "uint16", "value": 16, "min": 1, "max": 128}
                        ],
                    }
                ],
            },
            {
                "name": "Effects",
                "type": "Effects",
                "role": "generic",
                "enabled": True,
                "children": [
                    {
                        "name": "Layer",
                        "type": "Layer",
                        "role": "layer",
                        "enabled": True,
                        "status": "running",
                        "severity": "status",
                        "controls": [
                            {"name": "opacity", "type": "uint8", "value": 200, "min": 0, "max": 255}
                        ],
                        "children": [
                            {
                                "name": "Pulse",
                                "type": "PulseEffect",
                                "role": "effect",
                                "enabled": True,
                                "controls": [
                                    {"name": "speed", "type": "uint8", "value": 60, "min": 1, "max": 255},
                                    {"name": "mirror", "type": "bool", "value": False},
                                    {"name": "waveform", "type": "select", "value": 0, "options": ["sin", "tri"]},
                                    {"name": "note", "type": "text", "value": "hello"},
                                    {"name": "identify", "type": "button", "value": 0},
                                    {"name": "secret", "type": "password", "value": "aa"},
                                    {"name": "future", "type": "future-widget", "value": 1},
                                    {
                                        "name": "advanced",
                                        "type": "uint8",
                                        "value": 1,
                                        "min": 0,
                                        "max": 10,
                                        "minMode": 1,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "name": "Drivers",
                "type": "Drivers",
                "role": "generic",
                "enabled": True,
                "controls": [
                    {"name": "on", "type": "bool", "value": True},
                    {"name": "brightness", "type": "uint8", "value": 128, "min": 0, "max": 255},
                    {
                        "name": "palette",
                        "type": "palette",
                        "value": "Rainbow",
                        "options": [{"name": "Rainbow"}, {"name": "Party"}],
                    },
                ],
            },
            {
                "name": "System",
                "type": "SystemModule",
                "role": "generic",
                "enabled": True,
                "respectsEnabled": False,
                "controls": [
                    {"name": "deviceName", "type": "text", "value": "MM-abcd"},
                    {"name": "rssi", "type": "display-int", "value": -60, "unit": "dBm", "readonly": True},
                ],
            },
        ]
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the integration from this repository."""
    yield


@pytest.fixture
def moonlight_ws() -> FakeWebSocket:
    """The socket the coordinator's client opens."""
    return FakeWebSocket()


@pytest.fixture(autouse=True)
def patch_websocket(monkeypatch: pytest.MonkeyPatch, moonlight_ws: FakeWebSocket):
    """Every client opens the fake socket."""

    async def _connect(self: MoonLightClient, *, heartbeat: float | None = None) -> FakeWebSocket:
        moonlight_ws.heartbeat = heartbeat
        return moonlight_ws

    monkeypatch.setattr(MoonLightClient, "ws_connect", _connect)


def mock_device(aioclient_mock, *, host: str = HOST, port: int = PORT, system_body: dict | None = None, state_body: dict | None = None) -> None:
    """Stub the two reads setup performs."""
    base = f"http://{host}:{port}"
    aioclient_mock.get(f"{base}/api/system", json=deepcopy(system_body if system_body is not None else system()))
    aioclient_mock.get(f"{base}/api/state", json=deepcopy(state_body if state_body is not None else state()))
