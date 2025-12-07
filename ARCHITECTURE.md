# Multi-Service Backend Architecture

This document describes the multi-service architecture design for scaling the backend.

## Overview

The backend is designed to run multiple independent services (calendar, blog, strava, etc.) that share common infrastructure (database, authentication) but remain isolated.

---

## Current Architecture (Single Service)

```
┌─────────────────────────────────────────────┐
│              Internet (HTTPS)               │
└──────────────────┬──────────────────────────┘
                   │
            ┌──────▼──────┐
            │    Caddy    │  (Port 80/443)
            │   Reverse   │
            │    Proxy    │
            └──────┬──────┘
                   │
       ┌───────────┴───────────┐
       │                       │
┌──────▼──────┐         ┌──────▼──────┐
│ calendar-api│         │     db      │
│  (Port 5001)│────────▶│ PostgreSQL  │
└─────────────┘         └─────────────┘
```

### Current Routing

- `https://api.vuhnger.dev/calendar/*` → calendar-api:5001
- `https://api.vuhnger.dev/docs` → calendar-api:5001

---

## Future Architecture (Multi-Service)

```
┌─────────────────────────────────────────────┐
│              Internet (HTTPS)               │
└──────────────────┬──────────────────────────┘
                   │
            ┌──────▼──────┐
            │    Caddy    │  (Port 80/443)
            │   Reverse   │
            │    Proxy    │
            └──────┬──────┘
                   │
       ┌───────────┼───────────┐
       │           │           │
┌──────▼──────┐ ┌─▼─────┐ ┌───▼────┐
│ calendar-api│ │blog-api│ │strava  │
│  (5001)     │ │ (5002) │ │  (5003)│
└──────┬──────┘ └────┬───┘ └────┬───┘
       │             │           │
       └─────────────┴───────────┘
                   │
            ┌──────▼──────┐
            │     db      │
            │ PostgreSQL  │
            └─────────────┘
```

### Multi-Service Routing

- `https://api.vuhnger.dev/calendar/*` → calendar-api:5001
- `https://api.vuhnger.dev/blog/*` → blog-api:5002
- `https://api.vuhnger.dev/strava/*` → strava-api:5003
- `https://api.vuhnger.dev/docs` → Gateway (future: aggregated docs)

---

## Implementation Options

### Option 1: Separate Containers (Current Pattern)

Each service runs in its own container with its own FastAPI app.

**Pros:**
- Complete isolation
- Independent scaling
- Independent deployment
- Different Python dependencies per service
- Easier to debug

**Cons:**
- More containers to manage
- More memory usage
- Slightly more complex deployment

**When to use:** When services have different dependencies or scale requirements.

### Option 2: Single Container, Multiple Routers

One FastAPI app mounts all service routers.

**Pros:**
- Simpler deployment (one container)
- Lower memory usage
- Shared dependencies

**Cons:**
- Tight coupling
- Must restart all services to update one
- Single point of failure

**When to use:** For small projects or tightly coupled services.

---

## Recommended: Option 1 (Separate Containers)

### Directory Structure

```
backend/
├── apps/
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── database.py      # Shared DB connection
│   │   └── auth.py          # Shared auth middleware
│   ├── calendar/
│   │   ├── __init__.py
│   │   ├── main.py          # Calendar FastAPI app
│   │   └── Dockerfile       # (optional) service-specific build
│   ├── blog/
│   │   ├── __init__.py
│   │   ├── main.py          # Blog FastAPI app
│   │   └── Dockerfile       # (optional)
│   └── strava/
│       ├── __init__.py
│       ├── main.py          # Strava FastAPI app
│       └── Dockerfile       # (optional)
├── docker-compose.yml       # Orchestrates all services
├── Caddyfile                # Routes to all services
└── Dockerfile               # Default build (used by all services if no custom Dockerfile)
```

### docker-compose.yml (Multi-Service)

```yaml
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - backend

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-backend_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-changeme}
      POSTGRES_DB: ${POSTGRES_DB:-backend_db}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - backend
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-backend_user}"]
      interval: 10s
      timeout: 5s
      retries: 5

  calendar-api:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["uvicorn", "apps.calendar.main:app", "--host", "0.0.0.0", "--port", "5001"]
    restart: unless-stopped
    expose:
      - "5001"
    environment:
      DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER:-backend_user}:${POSTGRES_PASSWORD:-changeme}@db:5432/${POSTGRES_DB:-backend_db}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend

  blog-api:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["uvicorn", "apps.blog.main:app", "--host", "0.0.0.0", "--port", "5002"]
    restart: unless-stopped
    expose:
      - "5002"
    environment:
      DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER:-backend_user}:${POSTGRES_PASSWORD:-changeme}@db:5432/${POSTGRES_DB:-backend_db}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend

  strava-api:
    build:
      context: .
      dockerfile: Dockerfile
    command: ["uvicorn", "apps.strava.main:app", "--host", "0.0.0.0", "--port", "5003"]
    restart: unless-stopped
    expose:
      - "5003"
    environment:
      DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER:-backend_user}:${POSTGRES_PASSWORD:-changeme}@db:5432/${POSTGRES_DB:-backend_db}
      INTERNAL_API_KEY: ${INTERNAL_API_KEY}
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend

networks:
  backend:

volumes:
  caddy_data:
  caddy_config:
  postgres_data:
```

### Caddyfile (Multi-Service)

```
api.vuhnger.dev {
    # Calendar service
    reverse_proxy /calendar/* calendar-api:5001

    # Blog service
    reverse_proxy /blog/* blog-api:5002

    # Strava service
    reverse_proxy /strava/* strava-api:5003

    # API Documentation
    # Route /docs to calendar for now
    # Future: could serve aggregated docs
    reverse_proxy /docs calendar-api:5001
    reverse_proxy /redoc calendar-api:5001
    reverse_proxy /openapi.json calendar-api:5001
}
```

---

## Service Independence

Each service:
- Has its own FastAPI app instance
- Shares the database (different tables/schemas)
- Shares authentication middleware
- Has its own health endpoint
- Can be deployed/restarted independently

### Shared Code Pattern

```python
# apps/calendar/main.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.database import get_db, check_db_connection
from shared.auth import get_api_key

# Service-specific code
app = FastAPI(title="Calendar Service")
```

---

## Deployment

### Start All Services

```bash
docker-compose up -d --build
```

### Start Single Service

```bash
docker-compose up -d calendar-api
```

### Restart Single Service

```bash
docker-compose restart blog-api
```

### View Logs for Single Service

```bash
docker-compose logs -f strava-api
```

### Scale Services Independently

```bash
# Scale calendar to 3 instances
docker-compose up -d --scale calendar-api=3

# Requires load balancing in Caddy
```

---

## Database Schema Isolation

Each service should use its own schema or table prefix:

```python
# apps/calendar/models.py
class Event(Base):
    __tablename__ = "calendar_events"
    # ...

# apps/blog/models.py
class Post(Base):
    __tablename__ = "blog_posts"
    # ...
```

Or use PostgreSQL schemas:

```python
# apps/calendar/models.py
class Event(Base):
    __tablename__ = "events"
    __table_args__ = {"schema": "calendar"}
```

---

## API Documentation Strategy

### Option A: Separate Docs Per Service

- `https://api.vuhnger.dev/calendar/docs` → Calendar docs
- `https://api.vuhnger.dev/blog/docs` → Blog docs

Configure each service:

```python
app = FastAPI(
    docs_url="/calendar/docs",
    redoc_url="/calendar/redoc",
    openapi_url="/calendar/openapi.json"
)
```

### Option B: Aggregated Docs (Future)

Create a gateway service that aggregates all OpenAPI specs:

```python
# apps/gateway/main.py
# Combines openapi.json from all services
```

---

## Migration Path

### Phase 1: Single Service (Current)

- ✅ Calendar service running
- Blog and Strava placeholder files exist

### Phase 2: Add Second Service

1. Implement blog service endpoints
2. Update docker-compose to add blog-api
3. Update Caddyfile with blog routing
4. Deploy: `docker-compose up -d --build`

### Phase 3: Add Third Service

1. Implement strava service endpoints
2. Update docker-compose to add strava-api
3. Update Caddyfile with strava routing
4. Deploy: `docker-compose up -d --build`

### Phase 4: Optimization (Optional)

- Add load balancing
- Add service monitoring
- Add centralized logging
- Consider API gateway pattern

---

## Monitoring

### Health Checks

Each service should have:

```python
@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "service-name",
        "database": "connected" if check_db_connection() else "disconnected"
    }
```

Access via:
- `https://api.vuhnger.dev/calendar/health`
- `https://api.vuhnger.dev/blog/health`
- `https://api.vuhnger.dev/strava/health`

### Container Health

```bash
docker-compose ps
```

---

**Last updated:** 2025-12-07
