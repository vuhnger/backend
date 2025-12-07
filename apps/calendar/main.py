from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Calendar Service",
    version="1.0.0",
    description="API for managing calendar events and scheduling",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Configuration
origins = [
    "https://vuhnger.dev",
    "https://vuhnger.github.io",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router setup
router = APIRouter(prefix="/calendar")

@router.get("/health")
def health():
    """Health check endpoint - returns service status"""
    return {"status": "ok", "service": "calendar"}

# Future calendar endpoints will be added here
# Example structure:
# @router.get("/events")
# @router.post("/events")
# @router.get("/events/{event_id}")
# etc.

app.include_router(router)
