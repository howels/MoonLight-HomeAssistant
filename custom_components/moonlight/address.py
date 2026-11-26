"""Turn what the user typed into a host and a port.

MoonLight has no TLS listener. An address is a name or an IP, plus the port field, or an
`http://` URL whose port overrides the field.
"""

from __future__ import annotations

from urllib.parse import urlparse


def parse_address(host: str, port: int) -> tuple[str, int] | str:
    """Return `(host, port)` or a config-flow error key.

    `host` is the name or address, without a scheme and without brackets.
    """
    text = host.strip()
    if not text:
        return "invalid_host"
    if "://" in text:
        parsed = urlparse(text)
        if parsed.scheme in {"https", "wss"}:
            return "tls_unsupported"
        if parsed.scheme not in {"http", "ws"}:
            return "invalid_host"
        if parsed.hostname is None or parsed.path not in {"", "/"} or parsed.params or parsed.query:
            return "invalid_host"
        try:
            chosen = parsed.port if parsed.port is not None else port
        except ValueError:
            return "invalid_port"
        name = parsed.hostname
    else:
        if any(mark in text for mark in " /?#[]"):
            return "invalid_host"
        chosen = port
        name = text
    if isinstance(chosen, bool) or not isinstance(chosen, int) or not 1 <= chosen <= 65535:
        return "invalid_port"
    return name, chosen
