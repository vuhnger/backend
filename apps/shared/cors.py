"""Sentralisert CORS-konfigurasjon for alle backend-tjenester."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


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
    frontend_url = os.getenv("FRONTEND_URL")
    if frontend_url:
        clean_url = frontend_url.rstrip("/")
        if clean_url not in origins:
            origins.append(clean_url)

    # Legg til dev-origins hvis ikke i produksjon
    env = os.getenv("ENVIRONMENT", "development")
    if env != "production":
        origins.extend(DEV_ORIGINS)

    # Legg til ekstra origins
    origins.extend(EXTRA_ORIGINS)

    return origins


def setup_cors(app: FastAPI) -> None:
    """Legg til CORS-middleware på en FastAPI-app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
