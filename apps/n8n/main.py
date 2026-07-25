"""
n8n Health Check Service

Provides a health check endpoint that verifies n8n.vuhnger.dev is operational.
"""

import logging

import httpx
from fastapi import APIRouter, Response, status

from apps.shared.app_factory import create_app, include_versioned
from apps.shared.config import settings

logger = logging.getLogger(__name__)

app = create_app(
    title="n8n Health Check Service",
    url_prefix="n8n",
    description="Health check proxy for n8n automation platform",
)

router = APIRouter(prefix="/n8n", tags=["n8n"])


@router.get("/health")
def health():
    """This service's own liveness — deliberately independent of the upstream.

    The container healthcheck polls this, and autoheal restarts anything that
    reports unhealthy. Reporting the *upstream's* state here would therefore make
    a down n8n restart this container in a loop. See /upstream for that.
    """
    return {"status": "ok", "service": "n8n"}


@router.get("/upstream")
async def upstream(response: Response):
    """Whether the configured n8n instance is reachable.

    Answers 503 when it isn't. This used to return HTTP 200 with a
    ``{"status": "error"}`` body, which no monitor treats as a failure — so the
    endpoint reported an outage that nothing could act on.
    """
    url = settings.n8n_url
    if not url:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unconfigured", "service": "n8n"}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            upstream_response = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning("n8n upstream unreachable: %s", type(e).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unreachable", "service": "n8n", "url": url}

    if upstream_response.status_code != 200:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "degraded",
            "service": "n8n",
            "url": url,
            "http_status": upstream_response.status_code,
        }

    return {"status": "ok", "service": "n8n", "url": url}


include_versioned(app, router)
