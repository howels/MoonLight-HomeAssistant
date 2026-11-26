# The MoonLight integration

One Home Assistant config entry is one MoonLight endpoint. The code is in `custom_components/moonlight/`. This page is the map of that code onto MoonLight's web interface and its API.

## Devices follow the side nav

The web interface lists root modules in `NAV_GROUPS` (`src/ui/app.js`). That order is what a person looks for. It is not the order the modules run in.

`const.py` keeps the same groups:

1. Control
2. Layouts, Effects, Drivers
3. System, File Manager, Network, Devices, Services, Firmware

A root the list does not name is still a device, after those, in the order the state document lists the roots.

The endpoint device is the status bar: the device name from `GET /api/system`, the firmware version, and the Connected sensor. Every side-nav entry is a child device of that endpoint. Home Assistant has no nested card, so a child module is not a device. Its controls are entities on the root, and the entity name is the path of cards joined by ` · `. On the Effects device, the Pulse effect's speed is `Layer · Pulse · Speed`.

The unique id does not use that path. It is `{mac}_{module}_{control}`, and module names are unique across the tree, so a renamed parent does not orphan the entity. The displayed name is rebuilt when a full state document arrives.

## Control types

`models.entity_platform` is the one map from a MoonLight control type to a Home Assistant platform.

| Type | Entity |
|---|---|
| `bool` | switch, or a binary sensor when read-only |
| `uint8`, `uint16`, `int16`, `int32` | number, slider unless `numberField` is set |
| `pin` | number, a box, configuration category |
| `select`, `palette` | select. An index is shown as the option name and written back as the index. A stored name is written back as the name |
| `text`, `textarea`, `filepath`, `ipv4` | text |
| `button` | button. The write is `1`, which is the press |
| `display`, `display-int`, `progress` | sensor |
| read-only of any writable type | sensor or binary sensor |
| `password`, `list` | not an entity |
| anything else | skipped, and the type is logged once |

`enabled` is a pseudo-control. The state document puts it on the module header, and a module with `respectsEnabled` not false gets an Enabled switch even when the controls array has no such row.

`minMode` 1 and 2 start disabled. That is the web interface hiding a control until expert or developer mode.

Drivers `on` and Drivers `brightness` are not also a switch and a number. They are the Light on the Drivers device. Brightness is already 0 to 255. The light has no colour mode. A palette is the select on that same device, because a colour written to MoonLight snaps to a palette.

## Looks

The `presets` list on the module named `Control` is the preset list. A row whose `roles` is exactly `["effects"]` is a look. Any other role is left out, because a Drivers or Layouts preset rewires pins or geometry.

The Look select on the Control device applies a look, which is where the web interface keeps presets. The light's effect list is the same set, so an automation can apply one. Both call `POST /api/list/Control/presets/<id>/apply`.

## Connect, then the socket

`client.MoonLightClient` is the only place that builds a URL.

Setup calls `GET /api/system` and `GET /api/state`. A connection failure and a body that is not MoonLight's API are different errors, and the config flow shows a different sentence for each. The MAC from `/api/system` is the config entry's unique id, formatted by Home Assistant.

The background task then opens `ws://<host>:<port>/ws` and sends `{"subscribe":["*"]}`. The web interface subscribes to the page on screen. Home Assistant subscribes to the whole tree, because every card can be an entity at once. A frame that is `{state, info}` is the WLED shim, sent to a client that has not subscribed, and it is ignored.

A document with `modules` replaces the tree. Entities that appeared are added. Entities whose control disappeared are removed. A side-nav device whose root disappeared can be deleted from the device registry. The endpoint device cannot.

A `patch` list updates values in place. A patch that names a module or a control the tree does not have asks for the document again with `{"resync": n}`.

The socket is the command path when it is open: `{"module", "control", "value"}`. `rejection` checks the value first and uses the phrases `POST /api/control` returns, so the user sees the same sentence either way. When the socket cannot take the write, the client repeats it with `POST /api/control`. Applying a look is HTTP only. The socket has no apply frame. After a look is applied the integration asks for a fresh document.

A dropped socket sets `connected` false, logs the reason once per outage, and retries. The delay starts at 1 second and doubles up to 30 seconds. `async_shutdown` closes the socket so unload does not wait out that delay.

## Files

| File | Responsibility |
|---|---|
| `address.py` | What the user typed, as a host and a port |
| `client.py` | HTTP and the WebSocket |
| `models.py` | The tree, the nav order, and the control-to-entity map |
| `coordinator.py` | The live tree, the socket task, and the devices |
| `entity.py` | Identity, availability, and adding or removing entities |
| `config_flow.py` | User, zeroconf, reconfigure |
| platform modules | One Home Assistant platform each |
| `services.py` | `set_control` and `apply_look` |
| `diagnostics.py` | The tree shape for a bug report |
| `system_health.py` | Whether each socket is up |

A new control type is one branch in `entity_platform`. The rest of the integration does not name effect types or driver types.
