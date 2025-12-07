# vuhnger/backend

A lightweight backend built with **FastAPI** and **Docker**, designed to run multiple small services (e.g., calendar, blog, Strava tracking).
The project is fully portable — it can run on NREC, local Docker, or any cloud provider that supports containers.

## 🚀 Features

- **FastAPI** with automatic OpenAPI documentation
- **Fully containerized** with Docker (Caddy + services)
- **Modular architecture** (`apps/<service>/main.py`)
- **Caddy** reverse proxy with automatic HTTPS
- **CORS** configured for production and development
- **Isolated Docker network** for inter-service communication
- Easy to extend with new services  

## 📦 Repository Structure

```
backend/
├── apps/
│   ├── shared/
│   │   ├── database.py          # Database connection & session management
│   │   └── auth.py              # API key authentication middleware
│   ├── calendar/
│   │   └── main.py              # Calendar service API
│   ├── blog/
│   │   └── main.py              # Blog service API (placeholder)
│   └── strava/
│       └── main.py              # Strava service API (placeholder)
├── frontend-examples/            # Frontend integration examples
│   ├── src/api/                 # TypeScript API client
│   └── src/components/          # React component examples
├── Caddyfile                    # Reverse proxy configuration (single service)
├── Caddyfile.multi              # Reverse proxy for all services
├── docker-compose.yml           # Single service orchestration
├── docker-compose.multi.yml     # Multi-service orchestration
├── Dockerfile                   # Container image definition
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variables template
├── ARCHITECTURE.md              # Multi-service architecture guide
├── SECURITY.md                  # Server security hardening guide
└── API_KEY_USAGE.md             # API authentication guide
```

## 📚 Documentation

### API Documentation

Live OpenAPI documentation is available at:

- **Swagger UI**: [https://api.vuhnger.dev/docs](https://api.vuhnger.dev/docs)
- **ReDoc**: [https://api.vuhnger.dev/redoc](https://api.vuhnger.dev/redoc)
- **OpenAPI JSON**: [https://api.vuhnger.dev/openapi.json](https://api.vuhnger.dev/openapi.json)

### Guides

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Multi-service architecture design and scaling guide
- **[SECURITY.md](SECURITY.md)** - Server security hardening (SSH, firewall, backups)
- **[API_KEY_USAGE.md](API_KEY_USAGE.md)** - API authentication setup and usage
- **[frontend-examples/](frontend-examples/)** - Frontend integration examples (React/TypeScript)

## 🛠 Requirements

You need **Docker** and **Docker Compose**.

### On macOS  
Docker Desktop includes everything:  
https://www.docker.com/products/docker-desktop/

### On Linux  
Install Docker + the Compose plugin using your package manager.

## ▶️ Running the Backend

### Local Development

Clone the repo:

```bash
git clone https://github.com/vuhnger/backend.git
cd backend
```

Start all services (Caddy + backend):

```bash
docker-compose up -d --build
```

Check that it works:

```bash
curl http://localhost/calendar/health
```

Expected output:

```json
{"status": "ok", "service": "calendar"}
```

View logs:

```bash
docker-compose logs -f
```

Stop all services:

```bash
docker-compose down
```

### Architecture

The setup includes:
- **Caddy** (ports 80/443): Reverse proxy with automatic HTTPS
- **calendar-api** (internal port 5001): FastAPI service
- **backend network**: Isolated Docker network for inter-service communication

Services communicate via Docker service names (`calendar-api:5001`), not localhost.

## 🧱 Adding New Services

To add another microservice:

1. Create a folder such as:
```
apps/blog/main.py
```
2. Implement FastAPI routes there.  
3. Update `Caddyfile` if you want it exposed publicly.  
4. Rebuild:

```bash
docker compose up -d --build
```

## 🌍 Deployment

### DigitalOcean / NREC

**Initial setup** (if migrating from host-based Caddy):

```bash
# Stop any existing Caddy service on the host
sudo systemctl stop caddy
sudo systemctl disable caddy

# Pull the repo
git pull

# Start containerized stack
docker-compose up -d --build
```

**Deploy updates**:

```bash
git pull
docker-compose up -d --build
```

**Restart individual services**:

```bash
# Restart just the calendar service
docker-compose restart calendar-api

# Restart just Caddy
docker-compose restart caddy
```

**View logs**:

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f calendar-api
```

### Other Platforms

This backend is portable to any Docker-friendly platform (Fly.io, Railway, Vultr, DigitalOcean, etc).

The containerized Caddy setup works anywhere Docker runs. SSL certificates are persisted in Docker volumes.

