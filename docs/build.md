# Build and test

The working directory for every command is the repository root.

## Prerequisites

Python 3.14, which is the version CI runs. A MoonLight checkout. The API tests read `docs/reference/openapi.yaml` and the WebSocket dispatch under `src/core/system/` in that checkout.

The checkout is the sibling directory `../MoonLight` when `MOONLIGHT_ROOT` is unset. Set `MOONLIGHT_ROOT` to the checkout root when it lives somewhere else.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
```

`.venv` is gitignored. The requirements file installs Home Assistant's test harness, pytest-cov and ruff. The integration itself has no pip requirements.

## The API version

`MOONLIGHT_API_VERSION` in `custom_components/moonlight/const.py` is the MoonLight device API this integration is written against. It is `info.version` in MoonLight's `docs/reference/openapi.yaml`.

`SOCKET_COMMANDS_VERSION` is `7.0.0`. That is the release where a control write, a list apply and a resync go over the WebSocket. It is a behaviour cut inside the API, not a second document. A firmware version below it still speaks the HTTP routes.

Diagnostics and system health report `MOONLIGHT_API_VERSION` as `api_version`, next to the version the device reported.

## Checks

Ruff, then the tests:

```sh
.venv/bin/ruff check custom_components tests
.venv/bin/pytest
```

`tests/test_api.py` loads the OpenAPI document and fails when any of these move:

- `info.version` is not `MOONLIGHT_API_VERSION`.
- `GET /api/system`, `GET /api/state`, `POST /api/control` or `POST /api/list/{module}/{control}/{row}/apply` is missing, or its `operationId` changed.
- `POST /api/control` no longer requires `module`, `control` and `value`, or an error body no longer carries `error`.
- `GET /api/state` no longer answers a `modules` array.
- A System, Module or Control field the parser reads has left its schema. Control extras such as `target` and `fader` stay legal while `additionalProperties` is not false.
- The server no longer dispatches `subscribe` or `resync`, or no longer writes a `patch` frame.

Point the tests at a chosen checkout:

```sh
MOONLIGHT_ROOT=/path/to/MoonLight .venv/bin/pytest tests/test_api.py
```

## When the device API changes

1. Read the diff of `docs/reference/openapi.yaml` and of the WebSocket dispatch.
2. Change the client where a route, a field or a frame it uses has moved.
3. Set `MOONLIGHT_API_VERSION` to the new `info.version`.
4. Run pytest with `MOONLIGHT_ROOT` on that tree.

A MoonLight commit that only adds a field does not fail these tests. A commit that removes or renames one the integration reads does.

## CI

`.github/workflows/validate.yml` runs on every push and pull request.

1. Check out this repository and `MoonModules/MoonLight`.
2. Install `requirements_test.txt` on Python 3.14.
3. Ruff, then pytest with `MOONLIGHT_ROOT` set to the MoonLight checkout. Coverage is reported for `custom_components/moonlight`.
4. hassfest.
5. The HACS integration validator, ignoring brands, issues and topics.

A MoonLight `main` whose OpenAPI version is no longer `MOONLIGHT_API_VERSION` fails the test job. Update the constant in the same change that adopts the new API.
