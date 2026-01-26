"""
n8n Health Check Service

Provides a health check endpoint that verifies n8n.vuhnger.dev is operational.
"""

import logging
import httpx
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_oauth2_redirect_html

from apps.shared.cors import setup_cors
from apps.shared.swagger_ui import render_swagger_ui_html

logger = logging.getLogger(__name__)

app = FastAPI(
    title="n8n Health Check Service",
    version="1.0.0",
    description="Health check proxy for n8n automation platform",
    docs_url=None,
    openapi_url="/n8n/openapi.json",
)

# Setup CORS from shared configuration
setup_cors(app)
app.mount("/static", StaticFiles(directory="static"), name="static")

router = APIRouter(prefix="/n8n", tags=["n8n"])


@app.get("/n8n/docs", include_in_schema=False)
def swagger_ui_html():
    return render_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title,
        oauth2_redirect_url="/n8n/docs/oauth2-redirect",
    )


@app.get("/n8n/docs/oauth2-redirect", include_in_schema=False)
def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


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
