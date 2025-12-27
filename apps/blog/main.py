from fastapi import FastAPI, APIRouter

from apps.shared.cors import setup_cors

app = FastAPI(title="Blog Service", version="1.0.0")

# Setup CORS from shared configuration
setup_cors(app)

# Router setup
router = APIRouter(prefix="/blog")


@router.get("/health")
def health():
    """Health check endpoint - returns service status"""
    return {"status": "ok", "service": "blog"}

# Future blog endpoints will be added here
# Example structure:
# @router.get("/posts")
# @router.post("/posts")
# @router.get("/posts/{post_id}")
# etc.


app.include_router(router)
