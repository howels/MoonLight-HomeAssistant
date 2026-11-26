# MoonLight for Home Assistant

A Home Assistant integration for [MoonLight](https://github.com/MoonModules/MoonLight). It speaks MoonLight's HTTP API and WebSocket, and lays the device out the way the MoonLight web interface does.

One config entry is one MoonLight endpoint. The endpoint is a device, named as the status bar names it. Each side-nav entry is a device under it: Control, then the light pipeline (Layouts, Effects, Drivers), then the device pages (System, File Manager, Network, Devices, Services, Firmware). A root the nav does not name is still a device, after those. A nested card is not its own device. Its controls are entities on the side-nav device, and the entity name is the path of cards: on Effects, Pulse's speed is `Layer · Pulse · Speed`.

## What you can control

| Web UI | Home Assistant |
|---|---|
| Side-nav entry | Child device of the endpoint |
| Card inside that page | The start of the entity name |
| Control on the card | Switch, number, select, text, button or sensor, from the control's type |
| Drivers `on` and `brightness` | The Light on the Drivers device |
| Drivers palette | A select on the Drivers device |
| Control presets that are effect looks | The Look select on Control, and the light's effect list |
| Enabled toggle on a card | An Enabled switch on that card's path |
| Status line | A diagnostic sensor |
| WebSocket dot | The Connected sensor on the endpoint |

A control the firmware marks expert or developer is created and left disabled, as the web interface hides it until that mode. Enable it from the device page.

## Install

Through [HACS](https://hacs.xyz):

1. HACS, then Custom repositories. Add `https://github.com/MoonModules/MoonLight-HomeAssistant`, category Integration.
2. Download MoonLight, then restart Home Assistant.

By hand: copy `custom_components/moonlight/` into `config/custom_components/` and restart.

## Add a device

Home Assistant discovers a board that advertises `_http._tcp` with `mm=1`.

To add one by address: Settings, Devices & services, Add integration, MoonLight. A board listens on port 80. MoonLight running on a computer listens on port 8080. An `https://` address is rejected. MoonLight has no TLS listener.

The MAC address identifies the device. A later discovery at a new address updates the existing entry.

The WLED integration also discovers a MoonLight board, through `_wled._tcp`, and it exposes one light. Use one integration for a given device. The two together list it twice.

## How it stays in step

Setup reads `GET /api/system` and `GET /api/state`. The integration then opens `/ws`. Current firmware is sent `{"subscribe":["*"]}` and then the patches. Older firmware sends the tree on connect, without that subscription. Home Assistant keeps every page, because every card can be an entity at once.

A dropped socket marks the entities unavailable and reconnects. The delay doubles from 1 second to 30 seconds. The Connected sensor reads off while the socket is down, and it stays available so the off state is visible.

On current firmware a change is sent on the WebSocket when it is open. Older firmware ignores that frame, so the change goes over HTTP. The same checks the device makes are applied first, and the phrases match `POST /api/control`: `value out of range`, `value malformed`, `control is read-only`. When the socket cannot take the write, the change is repeated over HTTP, which is where a refusal the local check cannot see comes back.

## Errors

- The host did not answer. The address or the port is wrong, or the device is off.
- The host answered, but not with MoonLight's API. The usual cause is the port.
- An `https://` address is rejected.
- A refused control shows the device's reason.
- While the WebSocket is down, a write fails and the entities are unavailable.

## What is not an entity

Passwords are not entities. The API returns them obfuscated, and a text field would write that obfuscation back. Lists other than effect looks are not entities. A list is edited on the device. An unknown control type is skipped and logged once, so a newer firmware does not stop the integration loading.

A preset whose role is drivers or layouts is not a look. Applying it would rewire pins or geometry.

## Actions

`moonlight.set_control` writes one control. The value is JSON: `40`, `true`, or `"Rainbow"`. `moonlight.apply_look` applies one effect look by name. Both take a MoonLight device.

## Contributing

Issues and pull requests are welcome. CI runs hassfest, the HACS validator, ruff, and the test suite. The protocol and the device layout are described in [docs/integration.md](docs/integration.md).

The API is documented in MoonLight's repository: [the HTTP and WebSocket API](https://moonmodules.org/MoonLight/reference/api.html).

## License

[GPL-3.0](LICENSE), as MoonLight.
