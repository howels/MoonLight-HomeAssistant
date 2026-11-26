"""The address field, before any network call."""

from custom_components.moonlight.address import parse_address


def test_plain_host_keeps_the_port_field() -> None:
    """A name and the port field."""
    assert parse_address("moonlight.local", 80) == ("moonlight.local", 80)


def test_url_port_overrides_the_field() -> None:
    """An http URL may carry the port."""
    assert parse_address("http://192.0.2.10:8080", 80) == ("192.0.2.10", 8080)


def test_https_is_rejected() -> None:
    """MoonLight has no TLS listener."""
    assert parse_address("https://192.0.2.10", 80) == "tls_unsupported"


def test_a_path_is_rejected() -> None:
    """The address is the device, not one of its routes."""
    assert parse_address("http://192.0.2.10/api", 80) == "invalid_host"


def test_empty_host_is_rejected() -> None:
    """A blank field is not a host."""
    assert parse_address("  ", 80) == "invalid_host"


def test_port_out_of_range_is_rejected() -> None:
    """The port field is a TCP port."""
    assert parse_address("192.0.2.10", 0) == "invalid_port"
    assert parse_address("http://192.0.2.10:99999", 80) == "invalid_port"
