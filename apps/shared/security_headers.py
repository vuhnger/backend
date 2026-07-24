"""Sikkerhetsheaders for API-tjenester.

Samler alle sikkerhetsrelaterte HTTP-headere i én middleware. Dette er en
tverrgående policy (CSP, clickjacking, MIME-sniffing, HSTS) som hører hjemme
ett sted, i stedet for å spres over flere middleware-lag.

Konsoliderer issues #25 (CSP), #26 (X-Frame-Options), #29 (HSTS) og
#30 (X-Content-Type-Options).
"""

from fastapi import FastAPI, Request
from fastapi.responses import Response

# Content-Security-Policy.
#
# 'unsafe-inline' for script/style kreves av Swagger UI (inline init-script og
# injiserte stiler). Assets serveres lokalt fra /static (se swagger_ui.py), så
# vi trenger ikke å whiteliste noen ekstern CDN. img/font tillater data: og
# https: for Swagger sine ikoner/favicon.
DEFAULT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data: https:; "
    "script-src 'self' 'unsafe-inline'; "
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
