"""Constants for the MoonLight integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "moonlight"
MANUFACTURER: Final = "MoonModules"

# A board serves the UI and the API on port 80. MoonLight running on a computer uses 8080.
DEFAULT_PORT: Final = 80
# An https URL with no port uses 443. The port field replaces either default.
HTTPS_PORT: Final = 443

# True when the address the user entered was https or wss. Absent on an older entry, which stays on http.
CONF_TLS: Final = "tls"

# How long one HTTP call may take. A live WebSocket is the steady state; this bounds connect and a command.
REQUEST_TIMEOUT: Final = 10

# aiohttp pings at this interval. Current firmware answers. v6.0.0 ignores the ping and the socket would drop, so that generation connects without a heartbeat.
HEARTBEAT_SECONDS: Final = 20.0

# `info.version` of MoonLight's docs/reference/openapi.yaml. The API tests refuse a tree
# whose document carries another version. Bump this when that document moves.
MOONLIGHT_API_VERSION: Final = "7.1.0-dev"

# Socket control writes, list apply and resync shipped in the v7.0.0 release. A 7.0.0-dev build compares below this and stays on HTTP.
SOCKET_COMMANDS_VERSION: Final = "7.0.0"

# Firmware Subscription::kMaxModules. A subscribe frame can name this many modules; the rest are ignored.
SUBSCRIPTION_NAMES: Final = 8

# Reconnect delay doubles from this floor up to the ceiling.
RETRY_MIN_SECONDS: Final = 1.0
RETRY_MAX_SECONDS: Final = 30.0

# GET /api/state is the whole interface schema. A large tree is well under this; the cap is so a runaway frame fails visibly.
WEBSOCKET_MAX_BYTES: Final = 8 * 1024 * 1024

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

# The side nav in MoonLight's src/ui/app.js (NAV_GROUPS). It is the order a person looks in,
# which is not the order the modules run in. A root the list does not name still appears, after these.
NAV_GROUPS: Final[tuple[tuple[str, ...], ...]] = (
    ("Control",),
    ("Layouts", "Effects", "Drivers"),
    ("System", "File Manager", "Network", "Devices", "Services", "Firmware"),
)

# Joins a nested card's path. "Layer · Pulse · Speed" is the Effects page, the Layer card, the Pulse card.
PATH_MARK: Final = " · "

# The light owns the desk's first channel. switch1 is power, fader1 is brightness, encoder1 is the palette.
# They are not also a switch, a number and a number.
LIGHT_CONTROLS: Final = frozenset(
    {("Control", "switch1"), ("Control", "fader1"), ("Control", "encoder1")}
)

# Off until the options flow turns a page on. Control is always shown and is not in this map.
CONF_SHOW_LAYOUTS: Final = "show_layouts"
CONF_SHOW_EFFECTS: Final = "show_effects"
CONF_SHOW_DRIVERS: Final = "show_drivers"
CONF_SHOW_SYSTEM: Final = "show_system"
CONF_SHOW_FILES: Final = "show_files"
CONF_SHOW_NETWORK: Final = "show_network"
CONF_SHOW_DEVICES: Final = "show_devices"
CONF_SHOW_SERVICES: Final = "show_services"
CONF_SHOW_FIRMWARE: Final = "show_firmware"
CONF_SHOW_OTHER: Final = "show_other"

SECTION_OPTIONS: Final[dict[str, str]] = {
    "Layouts": CONF_SHOW_LAYOUTS,
    "Effects": CONF_SHOW_EFFECTS,
    "Drivers": CONF_SHOW_DRIVERS,
    "System": CONF_SHOW_SYSTEM,
    "File Manager": CONF_SHOW_FILES,
    "Network": CONF_SHOW_NETWORK,
    "Devices": CONF_SHOW_DEVICES,
    "Services": CONF_SHOW_SERVICES,
    "Firmware": CONF_SHOW_FIRMWARE,
}

# The preset list that holds looks. Rows whose only role is effects become the light's effect list.
PRESET_MODULE: Final = "Control"
PRESET_CONTROL: Final = "presets"

NUMBER_TYPES: Final = frozenset({"uint8", "uint16", "int16", "int32", "pin"})
TEXT_TYPES: Final = frozenset({"text", "textarea", "ipv4", "filepath"})
SENSOR_TYPES: Final = frozenset({"display", "display-int", "progress"})
# Password values are obfuscated on the wire. A list is edited on the device, not as one entity.
SKIP_TYPES: Final = frozenset({"password", "list"})

SERVICE_SET_CONTROL: Final = "set_control"
SERVICE_APPLY_LOOK: Final = "apply_look"
SERVICE_ADD_MODULE: Final = "add_module"
SERVICE_REMOVE_MODULE: Final = "remove_module"
SERVICE_REPLACE_MODULE: Final = "replace_module"
SERVICE_CLEAR_CHILDREN: Final = "clear_children"

# Off unless the user turns it on. Factory reset and SD card format also stay disabled entities.
CONF_EXPERT_MODE: Final = "expert_mode"

ATTR_MODULE: Final = "module"
ATTR_CONTROL: Final = "control"
ATTR_VALUE: Final = "value"
ATTR_LOOK: Final = "look"
ATTR_TYPE: Final = "type"
ATTR_PARENT: Final = "parent"
