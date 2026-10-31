"""SSRF protection for the browser agents.

On a public server, a visitor must not be able to point Crowdpod's browsers at the server's own
network: localhost, private ranges, link-local (including cloud metadata at 169.254.169.254),
or non-web ports. `check_url` validates an address before visiting, and `guard_page` checks every
request the page makes (redirects, scripts, images), re-resolving each host so DNS rebinding can't
slip a private address in after the first check.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urlparse

BLOCKED_NAMES = ("localhost", ".localhost", ".local", ".internal", ".lan", ".home", ".arpa")
WEB_PORTS = {80, 443}


class BlockedURL(ValueError):
    pass


def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not (addr.is_multicast or addr.is_reserved or addr.is_link_local)


_cache: dict[str, tuple[float, bool]] = {}


def _host_is_public(host: str) -> bool:
    now = time.monotonic()
    hit = _cache.get(host)
    if hit and now - hit[0] < 30:
        return hit[1]
    try:
        infos = socket.getaddrinfo(host, None)
        ok = bool(infos) and all(_ip_is_public(info[4][0]) for info in infos)
    except (socket.gaierror, ValueError):
        ok = False
    _cache[host] = (now, ok)
    return ok


def check_url(url: str, *, allow_private: bool) -> str:
    """Return the URL if a browser agent may visit it, else raise BlockedURL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise BlockedURL("only http:// and https:// web addresses can be visited")
    if parsed.username or parsed.password:
        raise BlockedURL("addresses with a user name or password aren't allowed")
    if allow_private:
        return url.strip()
    host = parsed.hostname.lower().rstrip(".")
    if host.endswith(BLOCKED_NAMES) or host in {n.lstrip(".") for n in BLOCKED_NAMES}:
        raise BlockedURL("local and internal addresses can't be visited")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in WEB_PORTS:
        raise BlockedURL("only the standard web ports (80, 443) can be visited")
    if not _host_is_public(host):
        raise BlockedURL("that address points to a private or reserved network")
    return url.strip()


async def guard_page(context, *, allow_private: bool, on_block=None) -> None:  # noqa: ANN001
    """Abort any request from this browser context that check_url would refuse."""
    if allow_private:
        return

    async def handle(route) -> None:  # noqa: ANN001
        url = route.request.url
        if route.request.method not in ("GET", "HEAD", "OPTIONS"):
            await route.abort("blockedbyclient")  # read-only browsing (analytics beacons end up here too)
            return
        if url.startswith(("data:", "blob:", "about:")):
            await route.continue_()
            return
        try:
            check_url(url, allow_private=False)
        except BlockedURL as e:
            if on_block:
                on_block(url, str(e))
            await route.abort("blockedbyclient")
            return
        await route.continue_()

    await context.route("**/*", handle)
    # WebSockets aren't covered by routes; refuse them outright on a public server
    await context.add_init_script("window.WebSocket = undefined; window.RTCPeerConnection = undefined;")
