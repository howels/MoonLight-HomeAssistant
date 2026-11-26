# MoonLight for Home Assistant

A [Home Assistant](https://www.home-assistant.io) integration for [MoonLight](https://github.com/MoonModules/MoonLight), MoonModules' firmware for large LED installations and DMX fixtures. It talks to a MoonLight device over MoonLight's own HTTP and WebSocket API, so Home Assistant sees MoonLight as it is: its layers, effects, palettes and every control.

**Status: a skeleton.** It finds MoonLight devices on the network and adds each to Home Assistant's device registry. Entities come next.

## Three ways to reach Home Assistant

MoonLight reaches Home Assistant three ways, and this integration is the third:

1. **MQTT discovery**, built into MoonLight's MQTT module: every control becomes an entity, pushed through your MQTT broker.
2. **WLED emulation**: Home Assistant's WLED integration finds a MoonLight device by itself and controls it as a WLED device (on/off, brightness, color, palette).
3. **This integration**: found by itself as WLED emulation is, with MoonLight's full model as MQTT discovery gives it, and no broker needed.

## Install

Through [HACS](https://hacs.xyz):

1. HACS → ⋮ → **Custom repositories**: add `https://github.com/MoonModules/MoonLight-HomeAssistant`, category **Integration**.
2. Download **MoonLight**, then restart Home Assistant.

By hand: copy `custom_components/moonlight/` into your Home Assistant's `config/custom_components/` and restart.

## Add a device

- **Found by itself**: a MoonLight board announces itself on the network (`_http._tcp` with `mm=1`), and Home Assistant offers it under **Settings → Devices & services → Discovered**.
- **By address**: **Add integration → MoonLight**, then the device's address and port: 80 for a board, 8080 for MoonLight running on a computer.

The device's MAC identifies it, so a new IP address updates the existing entry.

## Contributing

Issues and pull requests are welcome. Each change keeps the two checks green that CI runs on every push: `hassfest`, Home Assistant's own integration validator, and the HACS validator.

The API this integration reads is documented in MoonLight's repository: [the HTTP and WebSocket API](https://moonmodules.org/MoonLight/reference/api.html), with its [OpenAPI description](https://github.com/MoonModules/MoonLight/blob/main/docs/reference/openapi.yaml).

## License

[GPL-3.0](LICENSE), as MoonLight.
