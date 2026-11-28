"""The socket names the pages the entry shows, not the whole tree."""

from custom_components.moonlight.const import SUBSCRIPTION_NAMES
from custom_components.moonlight.models import subscription_frame


def test_default_names_control_and_drivers_alone() -> None:
    """Control with its children, and Drivers' own controls for the light's palette."""
    assert subscription_frame({}) == {"subscribe": ["Control"], "only": ["Drivers"]}


def test_a_shown_page_is_named_with_its_children() -> None:
    """Drivers joins the subscribe list once its page is on, in side-nav order after Control."""
    frame = subscription_frame(
        {"show_layouts": True, "show_effects": True, "show_drivers": True, "show_system": True}
    )
    assert frame == {"subscribe": ["Control", "Drivers", "Layouts", "Effects", "System"]}


def test_other_modules_are_named_after_the_pages() -> None:
    """A root the nav does not list is subscribed when Other modules is on."""
    frame = subscription_frame({"show_other": True}, ["MoonCloud", "Control", "Layouts"])
    assert frame["subscribe"] == ["Control", "MoonCloud"]
    assert frame["only"] == ["Drivers"]


def test_every_page_on_is_past_the_firmware_name_table() -> None:
    """Control plus every page is more than the eight names this firmware keeps."""
    options = {key: True for key in (
        "show_layouts",
        "show_effects",
        "show_drivers",
        "show_system",
        "show_files",
        "show_network",
        "show_devices",
        "show_services",
        "show_firmware",
    )}
    frame = subscription_frame(options)
    assert frame["subscribe"][0] == "Control"
    assert frame["subscribe"][1] == "Drivers"
    assert "only" not in frame
    assert len(frame["subscribe"]) > SUBSCRIPTION_NAMES
