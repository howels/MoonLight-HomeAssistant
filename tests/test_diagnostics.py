"""Diagnostics name the tree and omit control values."""

from .test_init import _setup


async def test_diagnostics_list_roots_in_nav_order(hass, aioclient_mock) -> None:
    """The download follows the side nav and does not dump control values."""
    entry = await _setup(hass, aioclient_mock)
    from custom_components.moonlight.diagnostics import async_get_config_entry_diagnostics

    data = await async_get_config_entry_diagnostics(hass, entry)
    assert data["roots"] == ["Control", "Layouts", "Effects", "Drivers", "System"]
    assert data["connected"] is True
    assert data["looks"] == [{"name": "Rainbow", "active": True}]
    assert "future-widget" in data["unknown_types"]
    assert all("value" not in control for control in data["controls"])
