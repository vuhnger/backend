"""
n8n Health Check Service

Provides a health check endpoint that verifies n8n.vuhnger.dev is operational.
"""

import logging

import httpx
from fastapi import APIRouter

from apps.shared.app_factory import create_app

logger = logging.getLogger(__name__)

app = create_app(
    title="n8n Health Check Service",
    url_prefix="n8n",
    description="Health check proxy for n8n automation platform",
)

router = APIRouter(prefix="/n8n", tags=["n8n"])


@router.get("/health")
async def health():
    """Health check endpoint - verifies n8n.vuhnger.dev is reachable"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("https://n8n.vuhnger.dev")

            if response.status_code == 200:
                return {"status": "ok", "service": "n8n", "url": "n8n.vuhnger.dev"}
            else:
                return {
                    "status": "degraded",
                    "service": "n8n",
                    "url": "n8n.vuhnger.dev",
                    "http_status": response.status_code,
                }
    except Exception as e:
        logger.error(f"n8n health check failed: {str(e)}")
        return {
            "status": "error",
            "service": "n8n",
            "url": "n8n.vuhnger.dev",
            "error": "unreachable",
        }


app.include_router(router)
