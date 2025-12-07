# API Key Authentication Guide

This backend uses API key authentication to protect endpoints from unauthorized access.

## How It Works

The API checks for an `X-API-Key` header in requests and validates it against the `INTERNAL_API_KEY` environment variable.

---

## Setup

### 1. Generate a Secure API Key

```bash
# On your local machine or server
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example output: `xvQ9mKp3R7sN2tL4wE6gH8jY1bC5dF9a`

### 2. Configure on Server

```bash
# On the server
cp .env.example .env
nano .env

# Add the generated key:
INTERNAL_API_KEY=xvQ9mKp3R7sN2tL4wE6gH8jY1bC5dF9a
```

### 3. Restart Services

```bash
docker-compose down
docker-compose up -d --build
```

---

## Usage Examples

### cURL

```bash
# Without API key - fails
curl https://api.vuhnger.dev/calendar/health

# With API key - succeeds
curl -H "X-API-Key: your_api_key_here" \
     https://api.vuhnger.dev/calendar/health
```

### Frontend (JavaScript/TypeScript)

Update your frontend API client:

```typescript
// src/api/calendar.ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;
const API_KEY = import.meta.env.VITE_API_KEY;

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/calendar/health`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,  // Add this line
    },
  });

  if (!response.ok) {
    throw new Error(`Health check failed: ${response.statusText}`);
  }

  return response.json();
}
```

Frontend `.env`:

```env
VITE_API_BASE_URL=https://api.vuhnger.dev
VITE_API_KEY=your_api_key_here
```

### Python

```python
import requests

API_KEY = "your_api_key_here"

response = requests.get(
    "https://api.vuhnger.dev/calendar/health",
    headers={"X-API-Key": API_KEY}
)

print(response.json())
```

---

## Implementation Details

### Option 1: Middleware (Apply to All Routes)

```python
from shared.auth import APIKeyMiddleware

app.add_middleware(
    APIKeyMiddleware,
    exclude_paths=["/health", "/docs", "/redoc", "/openapi.json"]
)
```

This protects all endpoints except those in `exclude_paths`.

### Option 2: Dependency (Apply to Specific Routes)

```python
from fastapi import Depends
from shared.auth import get_api_key

@router.get("/protected")
def protected_endpoint(api_key: str = Depends(get_api_key)):
    return {"message": "This endpoint requires API key"}

@router.get("/public")
def public_endpoint():
    return {"message": "This endpoint is public"}
```

This gives fine-grained control over which endpoints require authentication.

---

## Current Status

**API key authentication is NOT currently enforced** to allow easy testing.

To enable it, update `apps/calendar/main.py`:

```python
from shared.auth import get_api_key
from fastapi import Depends

# Option 1: Protect specific endpoint
@router.get("/events")
def get_events(api_key: str = Depends(get_api_key)):
    return {"events": []}

# Option 2: Protect all endpoints (add middleware)
from shared.auth import APIKeyMiddleware
app.add_middleware(
    APIKeyMiddleware,
    exclude_paths=["/calendar/health", "/docs", "/redoc"]
)
```

---

## Security Notes

1. **Never commit `.env` files** with real API keys to Git
2. **Use different keys** for development and production
3. **Rotate keys** if they're compromised
4. **HTTPS only** - Never send API keys over HTTP
5. **Consider rate limiting** for production (e.g., using nginx/Caddy)

---

## Development Mode

If `INTERNAL_API_KEY` is not set in the environment, the middleware allows all requests (development mode).

This means:
- ✓ Local development works without API key
- ✓ Production enforces API key when configured

---

## Testing

```bash
# Test without API key (should fail in production)
curl https://api.vuhnger.dev/calendar/events

# Test with valid API key
curl -H "X-API-Key: your_key" \
     https://api.vuhnger.dev/calendar/events

# Test with invalid API key (should return 401)
curl -H "X-API-Key: wrong_key" \
     https://api.vuhnger.dev/calendar/events
```

Expected responses:
- No key / wrong key: `401 Unauthorized`
- Valid key: `200 OK` with data

---

**Last updated:** 2025-12-07
