# The MoonLight integration

One Home Assistant config entry is one MoonLight endpoint. The code is in `custom_components/moonlight/`. This page is the map of that code onto MoonLight's web interface and its API.

`MOONLIGHT_API_VERSION` in `const.py` is `info.version` of MoonLight's OpenAPI document. The tests in `tests/test_api.py` read that document from a MoonLight checkout and fail when the version, a client route, or a socket frame has moved. How to run them, and how to move the constant, is [the build](build.md).

## Devices follow the side nav

The web interface lists root modules in `NAV_GROUPS` (`src/ui/app.js`). That order is what a person looks for. It is not the order the modules run in.

`const.py` keeps the same groups:

1. Control
2. Layouts, Effects, Drivers
3. System, File Manager, Network, Devices, Services, Firmware

A root the list does not name is a device only when Other modules is on, after those, in the order the state document lists the roots.

Control is created with the entry. Layouts, Effects, Drivers, System, File Manager, Network, Devices, Services and Firmware wait for the matching option. System is the page that holds factory reset and the settings that can take the device off the network. The options description says so, and the System toggle repeats it. Turning an option on reloads the entry, which adds or removes that child device and its entities. The socket names Control, Drivers alone, and each page that is on. Drivers alone carries the palette, so the light can read it while that page is hidden. A hidden page arrives as an outline, without its controls.

The endpoint device is the status bar: the device name, the firmware version, and the Connected sensor. The name and version come from `GET /api/system` when that document has them. v6.0.0 and the v7.0.0 release omit both, and the integration reads `System.mac`, `System.deviceName` and `Firmware.version` from `GET /api/state` instead. A shown side-nav entry is a child device of that endpoint. Home Assistant has no nested card, so a child module is not a device. Its controls are entities on the root, and the entity name is the path of cards joined by ` · `. On the Effects device, the Pulse effect's speed is `Layer · Pulse · Speed`.

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

`enabled` is a pseudo-control. The state document puts it on the module header, and a module with `respectsEnabled` not false gets an Enabled switch even when the controls array has no such row. The Enabled switch on Control turns that module on or off. It does not turn the lights off. The light entity drives `switch1`, which the desk forwards to `Drivers.on`.

`minMode` 1 and 2 start disabled. That is the web interface hiding a control until expert or developer mode.

A button the firmware marks `confirm`, and a control named `factory reset` or `format`, is a destructive action. It is created disabled. The integration options add a second gate, Expert mode, which is off until the user turns it on. A press is refused while Expert mode is off, including `moonlight.set_control`. Enabling the entity and turning Expert mode on are both required.

`switch1`, `fader1` and `encoder1` are not also a switch and two numbers. They are the Light on the Control device. `switch1` is power. `fader1` is brightness, already 0 to 255. `encoder1` selects the palette, which is the light's effect list, because a colour written to MoonLight snaps to a palette. A desk slot with no `target` is created and left unavailable. Its unique id stays `{mac}_Control_{slot}`.

Home Assistant lists the entities of one device by name. A desk slot's name starts with the bank the Control card draws, then the channel, then the control that slot drives: `2 Encoder 2 · Font`. An empty slot is `2 Encoder 3`. The banks are `1 Switch`, `2 Encoder` and `3 Fader`, which is the order of those strips on the card. The display strip is a sensor, so it stays on the Sensors list.

## Looks

The `presets` list on the module named `Control` is the preset list. A row whose `roles` is exactly `["effects"]` is a look. Any other role is left out, because a Drivers or Layouts preset rewires pins or geometry.

The Look select on the Control device applies a look, which is where the web interface keeps presets. Each filled effect pad is also a button, unique id `{mac}_pad_{slot}`, so a renamed look keeps the entity. The button's name is `4 Preset 1 · Rainbow`: the same bank number as the desk, the pad's place in the preset list, and the name on the pad. A driver or layout preset is not in that list, so its place is skipped. On v7.0.0 and later both call `POST /api/list/Control/presets/<id>/apply`. On older firmware both send `{"ps": slot}` on the socket, the 1-based place of that row in the full preset list.

## Lovelace cards

`www/moonlight-cards.js` is the file Home Assistant loads, from `/moonlight/moonlight-cards.js`. Both cards are given the Control light. The visual editor is the built-in form. Its entity field is labelled MoonLight light and lists only lights from this integration, one per device. The cards read the rest of that light's device from state attributes. Home Assistant's entity registry does not include the unique id.

| Surface | How the card finds it | Write |
|---|---|---|
| Power, channel 1 | the configured light | `light.turn_on` and `light.turn_off` |
| Brightness, channel 1 | the light's `brightness`, or `level` when that is null because the light is off | `moonlight.set_control` on `Control` / `fader1` |
| Palette, channel 1 | the light's effect list | `set_control` on `encoder1`, value the palette index |
| Switch, encoder or fader 2 to 8 | `module` `Control` and `control` `switchN`, `encoderN` or `faderN` | `set_control` on that control |
| Display strip | `control` `display` | none |
| Effect list on Basic | attribute `moonlight` `look` | `select.select_option` |
| Preset pads | attribute `moonlight` `pad`, ordered by `slot` | `button.press` |

`set_control` sends the value as a JSON string. `services.py` decodes that string, so `40`, `true` and `"Rainbow"` stay distinct. The device id is one string in that data. The action also accepts the one-item list Home Assistant substitutes when the same field arrives as a service target.

Channel 1 is the light, so that column is always present. A later channel with no entity stays in the row and ignores the pointer, which keeps switch N over encoder N over fader N. An unavailable entity publishes no attributes, so the card treats that slot the same way.

A pointer held on a dial, a fader or the brightness slider sets `_gesture`. The card skips `hass` updates until the pointer is up. Rebuilding the tree during the gesture would replace the control under the finger. When the pointer is up, the card replaces the tree only when the markup changed, so a state update elsewhere in Home Assistant does not redraw the dials.

The dial and the sixteen-segment glyphs follow `buildKnob` and `SEG16` in MoonLight's `src/ui/app.js`. A column is 52px and a name is 11px, so Brightness fits the column. The panel is limited to the card width. The desk strip scrolls horizontally and keeps the scrollbar's space, so the card height does not jump and a vertical bar does not take the width. A 500px editor preview fits the eight columns. Basic takes six columns of a section. The Pro card takes the full width. The colours are MoonLight's `:root` tokens. A name on the desk is the control the slot drives. An empty slot keeps `Switch 2`. Preset pads sit under the desk and wrap.

## Connect, then the socket

`client.MoonLightClient` is the only place that builds a URL. An `http` address uses `http` and `ws`. An `https` address uses `https` and `wss`. An entry saved before that flag exists stays on `http`.

Setup calls `GET /api/system` and `GET /api/state`. A connection failure and a body that is not MoonLight's API are different errors, and the config flow shows a different sentence for each. The MAC, from `/api/system` or from `System.mac`, is the config entry's unique id, formatted by Home Assistant.

The background task reads the version again, then opens `ws://<host>:<port>/ws` and sends the subscribe frame on every connection. Control is named with its children. Drivers is named in `only`, so its own controls arrive and its driver cards do not, until the Drivers option names it with its children. Each other page that is on is named with its children. Other modules are added when that option is on and a document has listed them. The current firmware keeps eight names and ignores the rest, so Control and Drivers are named first. v6 ignores the frame and still pushes the tree, because a new socket calls `requestFullResync`. Current firmware sends the tree only after the subscription, and until then it sends a `{state, info}` compatibility frame, which is ignored. The generation is the version, not the first frame. `AwesomeVersion` compares it with `7.0.0`. A `7.0.0-dev` build compares below that release. v7.0.0 and `7.1.0-dev` answer a ping and `{"resync": n}`.

v6 does not answer a WebSocket ping. The client sets aiohttp's heartbeat only when the version is v7.0.0 or later. There is no timed read of the first frame: cancelling `receive()` marks the socket closed.

A document with `modules` replaces the tree. Entities that appeared are added. Entities whose control disappeared are removed. The Look select is added when the Control card is present and removed when it is not. A side-nav device whose root disappeared can be deleted from the device registry. The endpoint device cannot.

A `patch` list updates values in place. A patch that names a module or a control the tree does not have reads the tree again: `{"resync": n}` on v7.0.0 and later, `GET /api/state` on older firmware.

A control write is `POST /api/control` on every version. The web interface posts a toggle the same way. The socket accepts `{"module", "control", "value"}` and does not say whether the device applied it, so that frame is not the command path. `rejection` checks the value first and uses the phrases the POST returns. A numeric float is truncated to an integer before that check, and that integer is what is sent. A document that still carries the value from before the write does not move the entity for two seconds. After that, the value the device keeps stands. Applying a look on v7.0.0 and later is `POST /api/list/Control/presets/<id>/apply`, then `{"resync": n}`. On older firmware it is `{"ps": slot}` and then `GET /api/state`. A down socket does not fall through to the apply route, which v6 does not have. A response that is not a command refusal and not a connection failure is reported as its own error.

A dropped socket sets `connected` false, logs the reason once per outage, and retries. The delay starts at 1 second and doubles up to 30 seconds. `async_shutdown` closes the socket so unload does not wait out that delay.

## Files

| File | Responsibility |
|---|---|
| `brand/icon.png` | Momo, the MoonLight icon, from MoonLight's `src/ui/momo.png`. Home Assistant serves it as the integration icon, and as the logo when no separate logo is present |
| `const.py` | Domain, platforms, nav order, timeouts, and `MOONLIGHT_API_VERSION` |
| `address.py` | What the user typed, as a host and a port |
| `client.py` | HTTP and the WebSocket |
| `models.py` | The tree, the nav order, and the control-to-entity map |
| `coordinator.py` | The live tree, the socket task, and the devices |
| `entity.py` | Identity, availability, and adding or removing entities |
| `config_flow.py` | User, zeroconf, reconfigure, page options, Expert mode. The WLED step runs only when that integration already has this host or MAC, because the board advertises `_wled._tcp` |
| `www/moonlight-cards.js` | The Basic and Pro Lovelace cards. The attributes they match are under Lovelace cards |
| platform modules | One Home Assistant platform each |
| `services.py` | `set_control` and `apply_look` |
| `diagnostics.py` | The tree shape for a bug report |
| `system_health.py` | Whether each socket is up |

A new control type is one branch in `entity_platform`. The rest of the integration does not name effect types or driver types.
