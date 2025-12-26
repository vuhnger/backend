"""
n8n Health Check Service

Provides a health check endpoint that verifies n8n.vuhnger.dev is operational.
"""
import logging
import httpx
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(
    title="n8n Health Check Service",
    version="1.0.0",
    description="Health check proxy for n8n automation platform",
    docs_url="/n8n/docs",
    openapi_url="/n8n/openapi.json"
)

# CORS Configuration
origins = [
    "https://vuhnger.dev",
    "https://www.vuhnger.dev",
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/n8n", tags=["n8n"])

@router.get("/health")
async def health():
    """Health check endpoint - verifies n8n.vuhnger.dev is reachable"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("https://n8n.vuhnger.dev")

            if response.status_code == 200:
                return {
                    "status": "ok",
                    "service": "n8n",
                    "url": "n8n.vuhnger.dev"
                }
            else:
                return {
                    "status": "degraded",
                    "service": "n8n",
                    "url": "n8n.vuhnger.dev",
                    "http_status": response.status_code
                }
    except Exception as e:
        logger.error(f"n8n health check failed: {str(e)}")
        return {
            "status": "error",
            "service": "n8n",
            "url": "n8n.vuhnger.dev",
            "error": "unreachable"
        }

app.include_router(router)
