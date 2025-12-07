from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Strava Service", version="1.0.0")

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
router = APIRouter(prefix="/strava")

@router.get("/health")
def health():
    """Health check endpoint - returns service status"""
    return {"status": "ok", "service": "strava"}

# Future strava endpoints will be added here
# Example structure:
# @router.get("/activities")
# @router.get("/stats")
# etc.

app.include_router(router)
