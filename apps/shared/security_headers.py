"""Sikkerhetsheaders for API-tjenester.

Samler alle sikkerhetsrelaterte HTTP-headere i én middleware. Dette er en
tverrgående policy (CSP, clickjacking, MIME-sniffing, HSTS) som hører hjemme
ett sted, i stedet for å spres over flere middleware-lag.

Konsoliderer issues #25 (CSP), #26 (X-Frame-Options), #29 (HSTS) og
#30 (X-Content-Type-Options).
"""

from fastapi import FastAPI, Request
from fastapi.responses import Response

# Content-Security-Policy (streng, global default).
#
# script-src holdes på 'self' uten 'unsafe-inline' slik at inline JavaScript
# ikke kan kjøre på API- og landingssidene — dette er den viktigste XSS-
# beskyttelsen. Swagger UI trenger inline-script og setter derfor sin egen,
# løsere CSP kun på docs-responsen (se swagger_ui.py); siden middleware bruker
# setdefault overstyres ikke den route-spesifikke verdien.
#
# style-src beholder 'unsafe-inline' (inline-stiler er lav risiko og brukes av
# landingssidene). Alle assets serveres lokalt, så ingen ekstern CDN whitelistes.
DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)

# 1 år, inkluder subdomener, klar for HSTS preload-listen.
DEFAULT_HSTS = "max-age=31536000; includeSubDomains; preload"


def setup_security_headers(app: FastAPI) -> None:
    """Legg til sikkerhetsheadere på alle responser.

    Bruker setdefault slik at en endpoint som eksplisitt setter en egen verdi
    (f.eks. en løsere CSP for en spesifikk route) ikke blir overstyrt.
    """

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", DEFAULT_CSP)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Strict-Transport-Security", DEFAULT_HSTS)
        return response
