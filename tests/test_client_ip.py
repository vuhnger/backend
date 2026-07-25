"""Client IP resolution behind the reverse proxy.

This one helper decides both the rate-limit bucket and the visitor geo lookup, so
getting it wrong either puts every visitor in one bucket (a single caller could
rate-limit the whole site) or reports the proxy's own address as the visitor.
"""

from starlette.requests import Request

from apps.shared.net import UNKNOWN_IP, client_ip


def _request(headers: dict[str, str] | None = None, peer: str | None = "127.0.0.1") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    if peer is not None:
        scope["client"] = (peer, 12345)
    return Request(scope)


def test_prefers_forwarded_for_over_the_proxy_peer():
    req = _request({"x-forwarded-for": "203.0.113.9"}, peer="127.0.0.1")
    assert client_ip(req) == "203.0.113.9"


def test_takes_the_last_hop_because_earlier_ones_are_client_controlled():
    # A caller forging "X-Forwarded-For: 1.2.3.4" only prepends to its own real
    # address, so the entry caddy appended last is the trustworthy one. Reading
    # the first hop would let anyone choose their own rate-limit bucket.
    req = _request({"x-forwarded-for": "1.2.3.4, 203.0.113.9"})
    assert client_ip(req) == "203.0.113.9"


def test_single_hop_is_used_as_is():
    assert client_ip(_request({"x-forwarded-for": "203.0.113.9"})) == "203.0.113.9"


def test_falls_back_to_the_peer_without_the_header():
    assert client_ip(_request(peer="198.51.100.4")) == "198.51.100.4"


def test_blank_forwarded_for_falls_back_instead_of_returning_empty():
    # An empty bucket key would silently merge every such caller into one bucket.
    req = _request({"x-forwarded-for": "   "}, peer="198.51.100.4")
    assert client_ip(req) == "198.51.100.4"


def test_no_peer_at_all_is_reported_explicitly():
    assert client_ip(_request(peer=None)) == UNKNOWN_IP
