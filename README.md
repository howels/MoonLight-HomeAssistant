# MoonLight for Home Assistant

A Home Assistant integration for [MoonLight](https://github.com/MoonModules/MoonLight). It speaks MoonLight's HTTP API and WebSocket, and lays the device out the way the MoonLight web interface does.

One config entry is one MoonLight endpoint. The endpoint is a device, named as the status bar names it. Control is shown on its own. The other side-nav pages stay hidden until the integration options turn them on: the light pipeline (Layouts, Effects, Drivers), then the device pages (System, File Manager, Network, Devices, Services, Firmware). System includes factory reset and the settings that can take the device off the network. A root the nav does not name waits for Other modules. A nested card is not its own device. Its controls are entities on the side-nav device, and the entity name is the path of cards: on Effects, Pulse's speed is `Layer · Pulse · Speed`. On the Control desk, a slot is named by its bank, its channel and what it drives: `2 Encoder 2 · Font`. Home Assistant sorts a device page by name, so those banks stay in the order the card draws: switches, encoders, faders, then the preset pads.

## What you can control

| Web UI | Home Assistant |
|---|---|
| Side-nav entry | Child device of the endpoint |
| Card inside that page | The start of the entity name |
| Control on the card | Switch, number, select, text, button or sensor, from the control's type |
| Desk `switch1`, `fader1`, `encoder1` | The Light on the Control device: power, brightness, palette |
| Control presets that are effect looks | The Look select on Control, and one button per pad |
| Enabled toggle on a card | An Enabled switch on that card's path. On Control it turns that module on or off, and it does not turn the lights off |
| Status line | A diagnostic sensor |
| WebSocket dot | The Connected sensor on the endpoint |

A control the firmware marks expert or developer is created and left disabled, as the web interface hides it until that mode. Enable it from the device page.

Factory reset and formatting the SD card take two steps. Turn on Expert mode in the integration options. Then enable the button on the device page. Until both are done, the press is refused, including from an action.

## Install

Through [HACS](https://hacs.xyz):

1. HACS, then Custom repositories. Add `https://github.com/MoonModules/MoonLight-HomeAssistant`, category Integration.
2. Download MoonLight, then restart Home Assistant.

By hand: copy `custom_components/moonlight/` into `config/custom_components/` and restart.

## Add a device

Home Assistant discovers a board that advertises `_http._tcp` with `mm=1`.

To add one by address: Settings, Devices & services, Add integration, MoonLight. The host is a name, an address, or an `http://` or `https://` URL with no path. Leave the port blank to use 80, or 443 when the URL is https. A number in the port field replaces that port. A board listens on port 80. MoonLight running on a computer listens on port 8080. An https address is contacted with TLS.

The MAC address identifies the device. A later discovery at a new address updates the existing entry.

A board also advertises `_wled._tcp`. Home Assistant's WLED integration discovers that announcement and would add a second light for the same device. When a WLED entry already has this host or MAC, the MoonLight config flow says so before the entry is created. Ignore that WLED discovery, or remove the WLED entry, when the device should be MoonLight only.

## How it stays in step

Setup reads `GET /api/system` and `GET /api/state`. The MAC and the firmware version come from `/api/system` when it carries them, and from the System and Firmware cards when it does not. The integration then opens `/ws` and subscribes to Control, to Drivers alone, and to each page the options have turned on. The socket carries that view. A control write is `POST /api/control` on every version. The socket accepts the same object and does not say whether the device applied it, so that frame is not the command path. A document that still has the value from before the write does not move the entity for two seconds. After that, the value the device keeps stands. Only Control is created until an option turns another page on. Changing an option reloads the entry.

A dropped socket marks the entities unavailable and reconnects. The delay doubles from 1 second to 30 seconds. The Connected sensor reads off while the socket is down, and it stays available so the off state is visible. The same checks the device makes are applied before the POST, and the phrases match that route: `value out of range`, `value malformed`, `control is read-only`.

## Errors

- The host did not answer. The address or the port is wrong, or the device is off.
- The host answered, but not with MoonLight's API. The usual cause is the port.
- A refused control shows the device's reason.
- While the WebSocket is down, the entities are unavailable.

## What is not an entity

Passwords are not entities. The API returns them obfuscated, and a text field would write that obfuscation back. Lists other than effect looks are not entities. A list is edited on the device. An unknown control type is skipped and logged once, so a newer firmware does not stop the integration loading.

A preset whose role is drivers or layouts is not a look. Applying it would rewire pins or geometry.

## Cards

The integration registers two Lovelace cards. The visual editor lists MoonLight lights only, one for each device. The card reads the display, the other channels, the looks and the pads from that light's device. How it matches them is in [docs/integration.md](docs/integration.md).

Basic, `custom:moonlight-basic-card`, is power, a brightness slider, the palette list and the effect looks.

Pro, `custom:moonlight-pro-card`, is the Control desk. The display strip sits over eight channels. Each channel is a switch, an encoder and a fader. The preset pads sit under the faders.

```yaml
type: custom:moonlight-basic-card
entity: light.moonlight_light
```

```yaml
type: custom:moonlight-pro-card
entity: light.moonlight_light
```

## Actions

`moonlight.set_control` writes one control. The value is JSON: `40`, `true`, or `"Rainbow"`. `moonlight.apply_look` applies one effect look by name. Both take a MoonLight device.

## Contributing

The build, the test commands and the pinned device API are in [docs/build.md](docs/build.md). `MOONLIGHT_API_VERSION` in `custom_components/moonlight/const.py` is the MoonLight OpenAPI version the integration is written against.

CI checks out MoonLight and fails when that document's version, a route the client calls, or a WebSocket frame the client uses has moved. hassfest and the HACS validator run there too.

The protocol and the device layout are in [docs/integration.md](docs/integration.md). MoonLight's HTTP API is [the reference](https://moonmodules.org/MoonLight/reference/api.html).

## License

[GPL-3.0](LICENSE), as MoonLight.
