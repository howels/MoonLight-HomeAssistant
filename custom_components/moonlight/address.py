"""Turn what the user typed into a host, a port and whether the connection uses TLS.

The host field is a name, an address, or an `http://` or `https://` URL with no path.
`ws://` and `wss://` are the same addresses. A URL with no port uses 80, or 443 for
https and wss. A number in the port field replaces that port, including a port written
in the URL.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .const import DEFAULT_PORT, HTTPS_PORT

_HTTP = frozenset({"http", "ws"})
_HTTPS = frozenset({"https", "wss"})


def parse_address(host: str, port: int | None) -> tuple[str, int, bool] | str:
    """Return `(host, port, tls)` or a config-flow error key.

    `host` is the name or address, without a scheme and without brackets.
    `port` is the port field. `None` means the field was left blank.
    `tls` is true when the URL scheme is `https` or `wss`.
    """
    text = host.strip()
    if not text:
        return "invalid_host"
    if "://" not in text:
        if any(mark in text for mark in " /?#[]"):
            return "invalid_host"
        chosen = DEFAULT_PORT if port is None else port
        if not _valid_port(chosen):
            return "invalid_port"
        return text, chosen, False
    parsed = urlparse(text)
    if parsed.scheme not in _HTTP | _HTTPS:
        return "invalid_host"
    if (
        parsed.hostname is None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return "invalid_host"
    try:
        url_port = parsed.port
    except ValueError:
        return "invalid_port"
    tls = parsed.scheme in _HTTPS
    if port is not None:
        chosen = port
    elif url_port is not None:
        chosen = url_port
    else:
        chosen = HTTPS_PORT if tls else DEFAULT_PORT
    if not _valid_port(chosen):
        return "invalid_port"
    return parsed.hostname, chosen, tls


def _valid_port(port: object) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535
