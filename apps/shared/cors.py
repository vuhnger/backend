"""Sentralisert CORS-konfigurasjon for alle backend-tjenester."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.shared.config import settings

# Produksjons-origins (alltid tillatt)
PRODUCTION_ORIGINS = [
    "https://vuhnger.dev",
    "https://www.vuhnger.dev",
    "https://nettside-pearl.vercel.app",
]

# Development origins (kun i dev-miljø)
DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "https://localhost:3000",
]

# Ekstra origins (GitHub Pages osv)
EXTRA_ORIGINS = [
    "https://vuhnger.github.io",
]


def get_allowed_origins() -> list[str]:
    """Hent liste over tillatte CORS origins basert på miljø."""
    origins = list(PRODUCTION_ORIGINS)

    # Legg til FRONTEND_URL fra env hvis satt
    frontend_url = settings.frontend_url
    if frontend_url:
        clean_url = frontend_url.rstrip("/")
        if clean_url not in origins:
            origins.append(clean_url)

    # Localhost-origins kun utenfor produksjon. I prod har de ingenting å gjøre
    # (med allow_credentials=True er en localhost-origin en unødvendig åpning).
    if not settings.is_production:
        origins.extend(DEV_ORIGINS)

    # Legg til ekstra origins
    origins.extend(EXTRA_ORIGINS)

    return origins


def is_allowed_origin(origin: str | None) -> bool:
    """Om en Origin-header skal slippe til på en WebSocket.

    WebSocket-handshaken er *unntatt* same-origin policy: browseren sender
    Origin, men håndhever ingenting selv, og `CORSMiddleware` slipper gjennom
    alt som ikke har `scope["type"] == "http"`. Uten denne sjekken kan en
    hvilken som helst nettside åpne en kanal mot oss på besøkendes vegne.

    Origin-listen er den samme som for HTTP, med vilje: to lister som kan drifte
    fra hverandre er akkurat den slags forskjell ingen oppdager før den utnyttes.

    En request helt uten Origin er ikke en browser (curl, en helsesjekk, en
    test). I produksjon avvises den — det finnes ingen legitim ikke-browser-
    klient for denne kanalen — mens den slippes gjennom lokalt der wscat og
    TestClient er hvordan man faktisk feilsøker.
    """
    if origin is None:
        return not settings.is_production
    return origin.rstrip("/") in get_allowed_origins()


def setup_cors(app: FastAPI) -> None:
    """Legg til CORS-middleware på en FastAPI-app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
