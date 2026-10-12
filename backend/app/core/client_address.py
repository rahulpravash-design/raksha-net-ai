"""The address of the person making a request, behind a known number of proxies.

On a host such as Render every request arrives from the platform's proxy, so the
connecting address is the proxy's: one shared rate-limit bucket for everyone (the
sign-in limit included) and proxy addresses in the audit trail.

``X-Forwarded-For`` carries the real address, but its left-most entries are whatever
the client sent and cannot be trusted. Each proxy *appends* the address it received
the request from, so with ``N`` trusted proxies in front of the application the
client is the ``N``-th entry from the right. Nothing to the left of that is read.

``RAKSHA_TRUSTED_PROXY_HOPS`` is that ``N``. It defaults to ``0``: the connecting
address, which is right whenever nothing sits in front of the application. Set it only
when *every* request passes through those proxies: a client that could reach the
application directly could write the header itself. (On Render a web service is reachable
only through the platform's proxy.)
"""

from __future__ import annotations

import ipaddress

from starlette.requests import Request


def _as_ip(value: str | None) -> str | None:
    """Only a real IP address: the audit columns are ``INET``, and a label such as
    ``testclient`` must become NULL rather than fail the request."""
    if not value:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_address(request: Request, trusted_proxy_hops: int) -> str | None:
    if trusted_proxy_hops > 0:
        entries = [
            part.strip()
            for header in request.headers.getlist("x-forwarded-for")
            for part in header.split(",")
            if part.strip()
        ]
        if len(entries) >= trusted_proxy_hops:
            return _as_ip(entries[-trusted_proxy_hops])
        # Fewer entries than trusted proxies: the request did not come through them
        # (or a proxy dropped the header). The connection is the only fact left.
    return _as_ip(request.client.host if request.client else None)
