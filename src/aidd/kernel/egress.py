"""Egress: the one way aidd fetches a URL, refused for any address that is not public."""

from __future__ import annotations

import ipaddress
import socket
import urllib.parse
import urllib.request

from aidd.kernel import http


def host_and_port(url: str) -> tuple[str, int]:
    """The host and port a URL names, even when its port is malformed (then the default)."""
    parsed = urllib.parse.urlsplit(url)
    try:
        return parsed.hostname or "", parsed.port or 443
    except ValueError:
        netloc = parsed.netloc.split("@")[-1]
        if netloc.startswith("["):  # an IPv6 literal: [addr]:port
            return netloc[1:].split("]", 1)[0], 443
        return netloc.split(":", 1)[0], 443


_SHARED = ipaddress.ip_network("100.64.0.0/10")  # carrier-grade NAT: not global, and not flagged private by Python


# Checked in order; the first match names the refusal.
_REFUSED = (
    ("loopback", lambda ip: ip.is_loopback),
    ("link-local", lambda ip: ip.is_link_local),
    ("shared (CGNAT)", lambda ip: ip.version == 4 and ip in _SHARED),
    ("private", lambda ip: ip.is_private),
    ("reserved", lambda ip: ip.is_reserved),
    ("unspecified", lambda ip: ip.is_unspecified),
    ("multicast", lambda ip: ip.is_multicast),
    ("non-global", lambda ip: not ip.is_global),
)


def check_public_address(host: str, port: int = 443) -> str:
    """The first address `host` resolves to, after checking that every one of them is public; otherwise HttpError."""
    try:
        addrs = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise http.HttpError(0, host, f"cannot resolve host {host!r}: {exc}") from exc
    vetted: list[str] = []
    for _family, _, _, _, sockaddr in addrs:
        ip_str = str(sockaddr[0])
        try:
            ip: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # ::ffff:10.0.0.1 is 10.0.0.1
        addr_class = next((name for name, refused in _REFUSED if refused(ip)), None)
        if addr_class:
            raise http.HttpError(0, host, f"refusing to reach {ip_str}: {addr_class} address class")
        vetted.append(ip_str)
    if not vetted:
        raise http.HttpError(0, host, f"host {host!r} resolves to no usable address")
    return vetted[0]


def fetch_text(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() != "https":
        raise http.HttpError(0, url, f"refusing scheme {parsed.scheme!r}; only https is permitted")
    host, port = host_and_port(url)
    ip = check_public_address(host, port)
    # The connection goes to the address just vetted, so a DNS answer that changes in between (rebinding) cannot
    # redirect it; no redirect is followed either. Behind a configured proxy the proxy picks the address. (The
    # sha256 pin on every extends URL is the real guarantee; this keeps the fetch from reaching internal hosts.)
    proxied = bool(urllib.request.getproxies().get("https")) and not urllib.request.proxy_bypass(host)
    return http.get_bytes(url, follow_redirects=False, pinned_ip=None if proxied else ip).decode("utf-8")
