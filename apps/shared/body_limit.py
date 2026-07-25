"""Reject oversized request bodies before anything reads them.

FastAPI parses the whole multipart body — spooling file parts to disk without a
cap — *before* it resolves dependencies. So the upload endpoint's own size and
API-key checks both run after an attacker's bytes have already landed: an
unauthenticated 25 MB POST is fully written to the host before the 401 is
returned. On a 19 GB box that has filled up once already, concurrent uploads are
a cheap way to take the whole stack down.

This runs as raw ASGI middleware rather than ``@app.middleware("http")`` so it
sees the request before any body parsing happens.

Limitation: a request that omits ``Content-Length`` (chunked transfer-encoding)
can't be judged up front. Caddy is the backstop for that case — see the
``request_body max_size`` directive documented in .github/DEPLOYMENT.md.
"""

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

_TOO_LARGE_BODY = b'{"detail":"Request body too large"}'


class BodySizeLimitMiddleware:
    """Answer 413 to any request that declares a body larger than ``max_bytes``."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        await self.app(scope, receive, send)

    async def _reject(self, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_TOO_LARGE_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})
