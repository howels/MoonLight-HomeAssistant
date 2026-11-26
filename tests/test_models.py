"""The tree parser. No Home Assistant, so a mapping mistake fails here."""

import pytest
from custom_components.moonlight.exceptions import MoonLightResponseError
from custom_components.moonlight.models import (
    Control,
    apply_patch,
    coerce_value,
    entity_name,
    entity_platform,
    is_destructive,
    nav_roots,
    parse_looks,
    parse_tree,
    rejection,
    require_mac,
    supplement_system,
    uses_socket_commands,
)

from .conftest import state


def test_nav_order_is_the_web_ui_order() -> None:
    """Control, then the pipeline, then the device pages."""
    parsed = parse_tree(state())
    assert parsed is not None
    modules, _, _, _ = parsed
    assert [module.name for module in nav_roots(modules)] == [
        "Control",
        "Layouts",
        "Effects",
        "Drivers",
        "System",
    ]


def test_nested_card_name_includes_the_path() -> None:
    """Pulse's speed sits on the Effects device as Layer · Pulse · Speed."""
    parsed = parse_tree(state())
    assert parsed is not None
    modules, controls, _, _ = parsed
    speed = controls[("Pulse", "speed")]
    assert entity_name(modules, speed) == "Layer · Pulse · Speed"
    assert entity_platform(speed) == "number"


def test_drivers_on_is_not_its_own_switch() -> None:
    """The light owns Drivers on and brightness."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, controls, _, unknown = parsed
    assert entity_platform(controls[("Drivers", "on")]) is None
    assert entity_platform(controls[("Drivers", "brightness")]) is None
    assert "future-widget" in unknown


def test_only_effect_presets_are_looks() -> None:
    """A driver preset is not a look."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, _, looks, _ = parsed
    assert [look.name for look in looks] == ["Rainbow"]
    assert looks[0].active is True
    assert looks[0].row == "1"
    assert looks[0].slot == 1


def test_password_and_list_are_not_entities() -> None:
    """A password is obfuscated on the wire. A list is edited on the device."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, controls, _, _ = parsed
    assert entity_platform(controls[("Pulse", "secret")]) is None
    assert entity_platform(controls[("Control", "presets")]) is None


def test_out_of_range_uses_the_device_phrase() -> None:
    """The sentence matches POST /api/control."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, controls, _, _ = parsed
    assert rejection(controls[("Pulse", "speed")], 0) == "value out of range"
    assert rejection(controls[("Pulse", "speed")], 40) is None


def test_system_without_respects_enabled_has_no_enabled_switch() -> None:
    """A module that ignores enabled does not grow a switch that would do nothing."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, controls, _, _ = parsed
    assert ("System", "enabled") not in controls
    assert ("Pulse", "enabled") in controls


def test_patch_updates_a_value_and_a_missing_control_asks_for_resync() -> None:
    """A known leaf is patched. An unknown leaf means the tree must be read again."""
    parsed = parse_tree(state())
    assert parsed is not None
    modules, controls, looks, unknown = parsed
    from custom_components.moonlight.models import MoonLightData

    data = MoonLightData(system={}, modules=modules, controls=controls, looks=looks, unknown_types=unknown)
    assert apply_patch(data, [{"path": "Pulse/speed", "value": 90}]) is False
    assert data.controls[("Pulse", "speed")].value == 90
    assert apply_patch(data, [{"path": "Pulse/nope", "value": 1}]) is True


def test_looks_ignore_a_malformed_list() -> None:
    """A preset value that is not a list is no looks, not an exception."""
    assert parse_looks({"name": "Rainbow"}) == ()


def test_socket_commands_start_at_the_7_release() -> None:
    """7.0.0-dev compares below the release that shipped socket commands."""
    assert uses_socket_commands("6.0.0") is False
    assert uses_socket_commands("7.0.0-dev.83") is False
    assert uses_socket_commands("7.0.0") is True
    assert uses_socket_commands("7.1.0-dev") is True
    assert uses_socket_commands(None) is False
    assert uses_socket_commands("local") is False


def test_a_float_is_truncated_before_the_range_check() -> None:
    """The range check sees the integer that will be sent."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, controls, _, _ = parsed
    speed = controls[("Pulse", "speed")]
    assert coerce_value(speed, 10.9) == 10
    assert rejection(speed, coerce_value(speed, 0.9)) == "value out of range"


def test_a_missing_select_value_writes_an_index() -> None:
    """No stored name means the control holds an index."""
    parsed = parse_tree(state())
    assert parsed is not None
    _, controls, _, _ = parsed
    waveform = controls[("Pulse", "waveform")]
    waveform.value = None
    assert waveform.value_is_index is True
    assert controls[("Drivers", "palette")].value_is_index is False


def test_factory_reset_and_format_are_destructive() -> None:
    """Those two presses wipe the device or the card. Identify does not."""
    assert is_destructive(Control("System", "factory reset", "button", confirm=True))
    assert is_destructive(Control("SdCard", "format", "button"))
    assert not is_destructive(Control("Pulse", "identify", "button"))


def test_the_tree_supplies_identity_when_system_omits_it() -> None:
    """v6 and the v7.0.0 release keep the MAC and the version on the cards."""
    body = state()
    for module in body["modules"]:
        if module["name"] == "System":
            module["controls"].append({"name": "mac", "type": "text", "value": "aa:bb:cc:dd:ee:ff", "readonly": True})
            module["controls"].append({"name": "deviceName", "type": "text", "value": "Board"})
    body["modules"].append(
        {
            "name": "Firmware",
            "type": "FirmwareUpdateModule",
            "controls": [{"name": "version", "type": "text", "value": "6.0.0", "readonly": True}],
        }
    )
    merged = supplement_system({"fps": 40}, body)
    assert merged["mac"] == "aa:bb:cc:dd:ee:ff"
    assert merged["version"] == "6.0.0"
    assert merged["name"] == "Board"
    with pytest.raises(MoonLightResponseError):
        require_mac(supplement_system({"ok": True}, {"ok": True}))
