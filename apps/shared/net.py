"""Client network identity behind the reverse proxy.

Every service runs behind caddy, so ``request.client.host`` is the proxy, not the
caller. Two modules used to carry their own copy of this logic (rate limiting and
the visit beacon); it lives here now so the per-IP identity that rate limits and
visitor geo both depend on can only ever be defined once.

Trust model: caddy overwrites ``X-Forwarded-For`` with the real peer address
rather than appending to a client-supplied value (its default when no
``trusted_proxies`` is configured), so the first hop is authoritative and not
spoofable from the internet. The container ports are additionally bound to
127.0.0.1, so nothing but caddy can reach them.
"""

from starlette.requests import Request

UNKNOWN_IP = "unknown"


def client_ip(request: Request) -> str:
    """The real caller's IP, honouring the reverse proxy's X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first_hop = forwarded.split(",")[0].strip()
        if first_hop:
            return first_hop
    return request.client.host if request.client else UNKNOWN_IP
