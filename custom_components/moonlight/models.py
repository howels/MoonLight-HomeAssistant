"""The module tree, as Home Assistant needs it.

The wire format is MoonLight's `GET /api/state` document and the `/ws` patch list.
Parsing accepts a newer firmware: an unknown control type is skipped, a missing field
uses a default, and a malformed node is dropped rather than failing the whole tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .const import (
    LIGHT_CONTROLS,
    NAV_GROUPS,
    NUMBER_TYPES,
    PATH_MARK,
    PRESET_CONTROL,
    PRESET_MODULE,
    SENSOR_TYPES,
    SKIP_TYPES,
    TEXT_TYPES,
)

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_IPV4 = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


def humanise(name: str) -> str:
    """Turn a control name such as `multiplyX` into `Multiply X`."""
    if name.startswith("@") and len(name) > 1:
        name = name[1:]
    spaced = _CAMEL.sub(" ", name).replace("_", " ").strip()
    if not spaced:
        return name
    return spaced[0].upper() + spaced[1:]


@dataclass(slots=True)
class Control:
    """One control on one module. `value` changes in place as patches arrive."""

    module: str
    name: str
    type: str
    value: Any = None
    minimum: int | None = None
    maximum: int | None = None
    options: tuple[str, ...] = ()
    readonly: bool = False
    hidden: bool = False
    min_mode: int = 0
    unit: str | None = None
    total: int | None = None
    number_field: bool = False
    confirm: bool = False
    synthetic: bool = False

    @property
    def value_is_index(self) -> bool:
        """A select or palette stores an index unless the device sent the option's name."""
        return isinstance(self.value, int) and not isinstance(self.value, bool)

    @property
    def key(self) -> tuple[str, str]:
        """Module name and control name. Module names are unique across the tree."""
        return (self.module, self.name)


@dataclass(slots=True)
class Module:
    """One node of the module tree."""

    name: str
    type: str
    role: str
    enabled: bool
    respects_enabled: bool
    status: str | None = None
    severity: str | None = None
    parent: str | None = None
    ordinal: int = 0


@dataclass(frozen=True, slots=True)
class Look:
    """One effect preset. Applying it does not rewire pins or geometry.

    `row` is the id current firmware applies. `slot` is the 1-based place in the
    preset list, which is what older firmware applies with `{"ps": slot}`.
    """

    name: str
    row: str
    active: bool
    slot: int = 0


@dataclass(slots=True)
class MoonLightData:
    """Everything the entities read. Patches mutate this object; they do not replace it."""

    system: dict[str, Any]
    modules: dict[str, Module]
    controls: dict[tuple[str, str], Control]
    looks: tuple[Look, ...]
    connected: bool = False
    last_error: str | None = None
    unknown_types: set[str] = field(default_factory=set)


def entity_platform(control: Control) -> str | None:
    """The Home Assistant platform for this control, or None when it is not an entity."""
    if control.hidden or control.key in LIGHT_CONTROLS or control.type in SKIP_TYPES:
        return None
    if control.type == "bool":
        return "binary_sensor" if control.readonly else "switch"
    if control.type in NUMBER_TYPES:
        return "sensor" if control.readonly else "number"
    if control.type in {"select", "palette"}:
        return "sensor" if control.readonly else "select"
    if control.type in TEXT_TYPES:
        return "sensor" if control.readonly else "text"
    if control.type == "button":
        return None if control.readonly else "button"
    if control.type in SENSOR_TYPES:
        return "sensor"
    return None


def root_module(modules: dict[str, Module], name: str) -> Module | None:
    """The side-nav entry that contains this module. Child cards live on that device."""
    current = modules.get(name)
    seen: set[str] = set()
    while current is not None and current.parent is not None and current.name not in seen:
        seen.add(current.name)
        parent = modules.get(current.parent)
        if parent is None:
            break
        current = parent
    return current


def card_path(modules: dict[str, Module], name: str) -> tuple[str, ...]:
    """The nested cards above this module, not including the side-nav root.

    On the Effects page, Pulse's path is ``("Layer", "Pulse")``.
    """
    chain: list[str] = []
    current = modules.get(name)
    seen: set[str] = set()
    while current is not None and current.parent is not None and current.name not in seen:
        seen.add(current.name)
        chain.append(current.name)
        current = modules.get(current.parent)
    chain.reverse()
    return tuple(chain)


def entity_name(modules: dict[str, Module], control: Control) -> str:
    """The control's label, preceded by the nested cards it sits on."""
    label = humanise(control.name)
    path = card_path(modules, control.module)
    if not path:
        return label
    return PATH_MARK.join((*path, label))


def nav_roots(modules: dict[str, Module]) -> list[Module]:
    """Root modules in side-nav order. A root the nav does not name follows, in tree order."""
    roots = [module for module in modules.values() if module.parent is None]

    def sort_key(module: Module) -> tuple[int, int, int]:
        for group_index, group in enumerate(NAV_GROUPS):
            if module.name in group:
                return (group_index, group.index(module.name), module.ordinal)
        return (len(NAV_GROUPS), module.ordinal, 0)

    return sorted(roots, key=sort_key)


def coerce_value(control: Control, value: Any) -> Any:
    """Shape a value the way the control's type stores it.

    A whole float becomes an int. A select that stores an index accepts the option's name.
    """
    if control.type in NUMBER_TYPES and isinstance(value, float) and value.is_integer():
        return int(value)
    if (
        control.type in {"select", "palette"}
        and control.value_is_index
        and isinstance(value, str)
        and value in control.options
    ):
        return control.options.index(value)
    return value


def rejection(control: Control, value: Any) -> str | None:
    """The device's refusal text when the value cannot be that control, else None.

    The phrases match `POST /api/control`, so a check made here and a check the device
    makes over HTTP read the same to the user.
    """
    if control.readonly or control.type in SENSOR_TYPES:
        return "control is read-only"
    if control.type == "bool":
        if not isinstance(value, bool):
            return "value malformed"
        return None
    if control.type in NUMBER_TYPES:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return "value malformed"
        number = int(value)
        if control.minimum is not None and number < control.minimum:
            return "value out of range"
        if control.maximum is not None and number > control.maximum:
            return "value out of range"
        return None
    if control.type in {"select", "palette"}:
        if control.value_is_index:
            if isinstance(value, int) and not isinstance(value, bool):
                if value < 0 or (control.options and value >= len(control.options)):
                    return "value out of range"
                return None
            return "value malformed"
        if not isinstance(value, str):
            return "value malformed"
        if control.options and value not in control.options:
            return "value out of range"
        return None
    if control.type in TEXT_TYPES:
        if not isinstance(value, str):
            return "value malformed"
        if control.type == "ipv4" and _IPV4.match(value) is None:
            return "value malformed"
        return None
    if control.type == "button":
        return None
    return None


def option_names(raw: Any) -> tuple[str, ...]:
    """Names from a select's string list or a palette's `{name, colors}` objects."""
    if not isinstance(raw, list):
        return ()
    names: list[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return tuple(names)


def _optional_int(raw: Any) -> int | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    return int(raw)


def parse_control(module: str, raw: Any) -> Control | None:
    """One control object from the state document, or None when it has no name and type."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    ctype = raw.get("type")
    if not isinstance(name, str) or not name or not isinstance(ctype, str) or not ctype:
        return None
    return Control(
        module=module,
        name=name,
        type=ctype,
        value=raw.get("value"),
        minimum=_optional_int(raw.get("min")),
        maximum=_optional_int(raw.get("max")),
        options=option_names(raw.get("options")),
        readonly=raw.get("readonly") is True,
        hidden=raw.get("hidden") is True,
        min_mode=_optional_int(raw.get("minMode")) or 0,
        unit=raw.get("unit") if isinstance(raw.get("unit"), str) and raw.get("unit") else None,
        total=_optional_int(raw.get("total")),
        number_field=raw.get("numberField") is True,
        confirm=raw.get("confirm") is True,
    )


def parse_looks(value: Any) -> tuple[Look, ...]:
    """Effect looks from the `presets` list. Any other role is left out.

    A Drivers or Layouts preset rewires pins or geometry. Only a row whose single role
    is `effects` is a look.
    """
    if not isinstance(value, list):
        return ()
    looks: list[Look] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            continue
        roles = row.get("roles")
        if not isinstance(roles, list):
            roles = row.get("activeRoles")
        if roles != ["effects"]:
            continue
        name = row.get("name")
        if not isinstance(name, str) or not name:
            continue
        row_id = row.get("id", name)
        if isinstance(row_id, bool) or not isinstance(row_id, int | str):
            continue
        looks.append(
            Look(name=name, row=str(row_id), active=row.get("active") is True, slot=index + 1)
        )
    return tuple(looks)


def _known_type(control: Control) -> bool:
    return control.type in SKIP_TYPES | SENSOR_TYPES | NUMBER_TYPES | TEXT_TYPES | {
        "bool",
        "button",
        "select",
        "palette",
    }


def _walk(
    node: Any,
    parent: str | None,
    ordinal: int,
    modules: dict[str, Module],
    controls: dict[tuple[str, str], Control],
    unknown: set[str],
) -> None:
    if not isinstance(node, dict):
        return
    name = node.get("name")
    if not isinstance(name, str) or not name or name in modules:
        for index, child in enumerate(node.get("children") or []):
            _walk(child, parent, index, modules, controls, unknown)
        return
    role = node.get("role") if isinstance(node.get("role"), str) else "generic"
    respects = node.get("respectsEnabled") is not False
    status = node.get("status") if isinstance(node.get("status"), str) else None
    severity = node.get("severity") if isinstance(node.get("severity"), str) else None
    modules[name] = Module(
        name=name,
        type=node.get("type") if isinstance(node.get("type"), str) else name,
        role=role,
        enabled=node.get("enabled") is not False,
        respects_enabled=respects,
        status=status,
        severity=severity,
        parent=parent,
        ordinal=ordinal,
    )
    raw_controls = node.get("controls")
    if isinstance(raw_controls, list):
        for item in raw_controls:
            control = parse_control(name, item)
            if control is None:
                continue
            if not _known_type(control) and not control.hidden and control.key not in LIGHT_CONTROLS:
                unknown.add(control.type)
            controls[control.key] = control
    if respects and (name, "enabled") not in controls:
        controls[(name, "enabled")] = Control(
            module=name,
            name="enabled",
            type="bool",
            value=node.get("enabled") is not False,
            synthetic=True,
        )
    if status is not None:
        controls[(name, "@status")] = Control(
            module=name,
            name="@status",
            type="display",
            value=status,
            readonly=True,
        )
    for index, child in enumerate(node.get("children") or []):
        _walk(child, name, index, modules, controls, unknown)


def parse_tree(payload: Any) -> tuple[dict[str, Module], dict[tuple[str, str], Control], tuple[Look, ...], set[str]] | None:
    """Parse a full state document. None when `modules` is missing or empty."""
    if not isinstance(payload, dict):
        return None
    raw_modules = payload.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        return None
    modules: dict[str, Module] = {}
    controls: dict[tuple[str, str], Control] = {}
    unknown: set[str] = set()
    for index, node in enumerate(raw_modules):
        _walk(node, None, index, modules, controls, unknown)
    if not modules:
        return None
    presets = controls.get((PRESET_MODULE, PRESET_CONTROL))
    looks = parse_looks(presets.value if presets is not None else None)
    return modules, controls, looks, unknown


def apply_patch(data: MoonLightData, patch: Any) -> bool:
    """Apply one `/ws` patch list. Return True when the tree must be read again.

    A patch that names a module or a control the integration has not seen is a schema
    change. The device normally sends a full document for that. Asking again covers a
    patch that arrived first.
    """
    if not isinstance(patch, list):
        return True
    resync = False
    for entry in patch:
        if not isinstance(entry, dict):
            resync = True
            continue
        path = entry.get("path")
        if not isinstance(path, str) or "/" not in path:
            resync = True
            continue
        module_name, control_name = path.split("/", 1)
        module = data.modules.get(module_name)
        if module is None:
            resync = True
            continue
        value = entry.get("value")
        if control_name == "@status":
            module.status = value if isinstance(value, str) else None
            if module.status is None:
                data.controls.pop((module_name, "@status"), None)
            else:
                data.controls[(module_name, "@status")] = Control(
                    module=module_name,
                    name="@status",
                    type="display",
                    value=module.status,
                    readonly=True,
                )
            continue
        if control_name == "@severity":
            module.severity = value if isinstance(value, str) else None
            continue
        if control_name.startswith("@"):
            continue
        control = data.controls.get((module_name, control_name))
        if control is None:
            resync = True
            continue
        control.value = value
        if control_name == "enabled" and isinstance(value, bool):
            module.enabled = value
        if module_name == PRESET_MODULE and control_name == PRESET_CONTROL:
            data.looks = parse_looks(value)
    return resync
