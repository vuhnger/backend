"""Client network identity behind the reverse proxy.

Every service runs behind caddy, so ``request.client.host`` is the proxy, not the
caller. Two modules used to carry their own copy of this logic (rate limiting and
the visit beacon); it lives here now so the per-IP identity that rate limits and
visitor geo both depend on can only ever be defined once.
"""

from starlette.requests import Request

UNKNOWN_IP = "unknown"


def client_ip(request: Request) -> str:
    """The real caller's IP, honouring the reverse proxy's X-Forwarded-For.

    Takes the *last* hop, not the first. With exactly one trusted proxy in front
    (caddy), the last entry is always the address caddy itself observed, so this
    is correct whether caddy replaces the header or appends to a client-supplied
    one — and a client that forges ``X-Forwarded-For: 1.2.3.4`` only ever prepends
    to its own real address. Reading the first hop instead would let any caller
    pick its own rate-limit bucket and its own reported location.

    Trusting the last hop assumes nothing but caddy can reach the app. That holds:
    the container ports are published on 127.0.0.1 only.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else UNKNOWN_IP
