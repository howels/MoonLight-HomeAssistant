"""The address field, before any network call."""

from custom_components.moonlight.address import parse_address


def test_plain_host_uses_the_port_field() -> None:
    """A name keeps the port the user typed. A blank port is 80."""
    assert parse_address("moonlight.local", 8080) == ("moonlight.local", 8080, False)
    assert parse_address("moonlight.local", None) == ("moonlight.local", 80, False)


def test_http_url_defaults_to_port_80() -> None:
    """An http URL with no port is port 80, and the connection stays on http."""
    assert parse_address("http://moonlight.local", None) == ("moonlight.local", 80, False)
    assert parse_address("http://moonlight.local/", None) == ("moonlight.local", 80, False)


def test_https_url_defaults_to_port_443() -> None:
    """An https URL with no port is port 443, and the connection uses TLS."""
    assert parse_address("https://moonlight.local", None) == ("moonlight.local", 443, True)


def test_a_port_in_the_url_is_kept_when_the_field_is_blank() -> None:
    """The URL's own port is the address when the port field is empty."""
    assert parse_address("http://192.0.2.10:8080", None) == ("192.0.2.10", 8080, False)
    assert parse_address("https://192.0.2.10:8443", None) == ("192.0.2.10", 8443, True)


def test_the_port_field_replaces_the_url_port() -> None:
    """A number in the port field wins over the scheme and over a port written in the URL."""
    assert parse_address("https://moonlight.local", 8443) == ("moonlight.local", 8443, True)
    assert parse_address("http://192.0.2.10:8080", 80) == ("192.0.2.10", 80, False)


def test_a_path_is_rejected() -> None:
    """The address is the device, not one of its routes."""
    assert parse_address("http://192.0.2.10/api", None) == "invalid_host"


def test_empty_host_is_rejected() -> None:
    """A blank field is not a host."""
    assert parse_address("  ", None) == "invalid_host"


def test_port_out_of_range_is_rejected() -> None:
    """The port field is a TCP port."""
    assert parse_address("192.0.2.10", 0) == "invalid_port"
    assert parse_address("http://192.0.2.10:99999", None) == "invalid_port"
