"""The integration against the MoonLight device API.

`MOONLIGHT_API_VERSION` is `info.version` in `docs/reference/openapi.yaml`.
The test reads that document, and the WebSocket dispatch, from a MoonLight checkout.
`MOONLIGHT_ROOT` selects the checkout. Otherwise the sibling directory `../MoonLight` is used.
A version move, a removed route, or a renamed socket frame fails here.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from custom_components.moonlight.const import MOONLIGHT_API_VERSION

# operationId, HTTP method, path. These are the routes the client calls.
_OPERATIONS = (
    ("getSystem", "get", "/api/system"),
    ("getState", "get", "/api/state"),
    ("setControl", "post", "/api/control"),
    ("applyListRow", "post", "/api/list/{module}/{control}/{row}/apply"),
)

# Fields the integration reads. A later document may add fields. It may not drop these.
_SYSTEM_FIELDS = frozenset({"version", "build", "firmware", "mac", "name", "board", "chip", "mode"})
_MODULE_FIELDS = frozenset(
    {"name", "type", "role", "enabled", "respectsEnabled", "status", "severity", "controls", "children"}
)
_CONTROL_FIELDS = frozenset({"name", "type", "value", "readonly", "hidden"})

# Desk flags ride as extra control properties. The schema must still allow them.
_CONTROL_EXTRAS = frozenset(
    {"min", "max", "options", "minMode", "numberField", "confirm", "unit", "total", "target", "fader", "encoder", "switchRow"}
)


def moonlight_root() -> Path:
    """The MoonLight checkout whose API this run checks."""
    chosen = os.environ.get("MOONLIGHT_ROOT")
    if chosen:
        root = Path(chosen)
    else:
        root = Path(__file__).resolve().parents[2] / "MoonLight"
    spec = root / "docs" / "reference" / "openapi.yaml"
    if not spec.is_file():
        pytest.fail(
            "MoonLight API tree not found at "
            f"{root}. Set MOONLIGHT_ROOT to a checkout whose docs/reference/openapi.yaml "
            f"info.version is {MOONLIGHT_API_VERSION}. The build document is docs/build.md."
        )
    return root


@pytest.fixture(scope="module")
def api_spec() -> dict:
    """The OpenAPI document for the targeted MoonLight version."""
    path = moonlight_root() / "docs" / "reference" / "openapi.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_openapi_document_is_the_targeted_version(api_spec: dict) -> None:
    """`info.version` is the constant. A MoonLight bump fails until the constant moves."""
    assert api_spec["openapi"].startswith("3.1.")
    found = api_spec["info"]["version"]
    assert found == MOONLIGHT_API_VERSION, (
        f"MoonLight openapi.yaml is {found}. This integration targets {MOONLIGHT_API_VERSION}. "
        "Read the API diff, change the client if a route it uses moved, then set "
        "MOONLIGHT_API_VERSION. docs/build.md has the steps."
    )


def test_the_client_routes_are_in_the_document(api_spec: dict) -> None:
    """Every HTTP call the client makes is an operation in the document, on that method."""
    paths = api_spec["paths"]
    for operation, method, path in _OPERATIONS:
        assert path in paths, path
        entry = paths[path].get(method)
        assert entry is not None, f"{method.upper()} {path}"
        assert entry["operationId"] == operation


def test_set_control_requires_module_control_and_value(api_spec: dict) -> None:
    """The POST body the client sends is the body the document requires."""
    schema = api_spec["paths"]["/api/control"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert set(schema["required"]) >= {"module", "control", "value"}
    error = api_spec["components"]["responses"]["Error"]["content"]["application/json"]["schema"]
    assert "error" in error["properties"]
    ok = api_spec["components"]["responses"]["Ok"]["content"]["application/json"]["schema"]
    assert "ok" in ok["properties"]


def test_state_is_a_module_list(api_spec: dict) -> None:
    """GET /api/state answers an object whose `modules` array is the tree."""
    response = api_spec["paths"]["/api/state"]["get"]["responses"]["200"]
    schema = response["content"]["application/json"]["schema"]
    assert "modules" in schema["properties"]
    assert schema["properties"]["modules"]["type"] == "array"


def test_system_module_and_control_keep_the_fields_the_parser_reads(api_spec: dict) -> None:
    """A field the parser reads is still on its schema."""
    schemas = api_spec["components"]["schemas"]
    assert _SYSTEM_FIELDS <= set(schemas["System"]["properties"])
    assert _MODULE_FIELDS <= set(schemas["Module"]["properties"])
    control = schemas["Control"]
    assert set(control["required"]) >= {"name", "type", "value"}
    assert _CONTROL_FIELDS <= set(control["properties"])
    # Extras such as `target` and `fader` are not all named. The schema must still accept them.
    assert control.get("additionalProperties") is not False
    named = set(control["properties"])
    if control.get("additionalProperties") is not True:
        assert _CONTROL_EXTRAS <= named


def test_apply_names_the_list_row_in_the_path(api_spec: dict) -> None:
    """The apply route takes the module, the control and the row, which is what the client quotes."""
    parameters = api_spec["paths"]["/api/list/{module}/{control}/{row}/apply"]["parameters"]
    names = []
    for parameter in parameters:
        if "$ref" in parameter:
            ref = parameter["$ref"].rsplit("/", 1)[-1]
            names.append(api_spec["components"]["parameters"][ref]["name"])
        else:
            names.append(parameter["name"])
    assert names == ["module", "control", "row"]


def test_the_socket_still_speaks_subscribe_resync_and_patch() -> None:
    """The frames the client sends and reads are still the server's frames.

    OpenAPI describes `/ws` in prose. The dispatch is the check that a renamed frame fails.
    """
    root = moonlight_root()
    module = (root / "src/core/system/HttpServerModule.cpp").read_text(encoding="utf-8")
    state = (root / "src/core/system/HttpServerState.cpp").read_text(encoding="utf-8")
    assert 'hasKey(body, "subscribe")' in module
    assert 'hasKey(body, "resync")' in module
    # The wire frame is {"patch":[ . The quotes are escaped in the C++ string.
    assert r'out.append("{\"patch\":[");' in state
