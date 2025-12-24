# vuhnger/backend

A lightweight FastAPI backend designed to run multiple small services. Built with Docker for easy deployment anywhere.

## Features

- FastAPI with automatic OpenAPI documentation
- Fully containerized with Docker Compose
- PostgreSQL database with persistent storage
- Caddy reverse proxy with automatic HTTPS
- API key authentication
- CORS support
- Isolated Docker network

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A domain pointed to your server (for HTTPS in production)

### Setup

Clone the repository:

```bash
git clone https://github.com/vuhnger/backend.git
cd backend
```

Create your environment file:

```bash
cp .env.example .env
```

Generate secure credentials and add them to `.env`:

```bash
python3 -c "import secrets; print('Database password:', secrets.token_urlsafe(32))"
python3 -c "import secrets; print('API key:', secrets.token_urlsafe(32))"
```

Update the `Caddyfile` with your domain (or use `localhost` for local development).

Start the services:

```bash
docker-compose up -d --build
```

Check that everything is running:

```bash
docker-compose ps
```

Test the API:

```bash
curl http://localhost/calendar/health
```

You should see: `{"status":"ok","service":"calendar","database":"connected"}`

## Common Operations

### Deploying Updates

```bash
git pull
docker-compose up -d --build
```

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f calendar-api
```

### Database Access

```bash
# Connect to PostgreSQL
docker-compose exec db psql -U backend_user -d backend_db

# Create a backup
docker-compose exec db pg_dump -U backend_user backend_db > backup.sql

# Restore from backup
cat backup.sql | docker-compose exec -T db psql -U backend_user -d backend_db
```

### Restarting Services

```bash
# Restart everything
docker-compose restart

# Restart a specific service
docker-compose restart calendar-api
```

### Stopping Services

```bash
# Stop but keep data
docker-compose down

# Stop and remove all data
docker-compose down -v
```

## Architecture

The setup uses three main containers:

- **Caddy**: Reverse proxy that handles HTTPS and routes requests
- **calendar-api**: FastAPI service running on port 5001
- **db**: PostgreSQL 16 database

All services communicate through an isolated Docker network. Only Caddy is exposed to the internet (ports 80 and 443). SSL certificates are managed automatically by Caddy.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_USER` | Database username | Yes |
| `POSTGRES_PASSWORD` | Database password | Yes |
| `POSTGRES_DB` | Database name | Yes |
| `INTERNAL_API_KEY` | API authentication key | Optional |

Never commit your `.env` file. Use `.env.example` as a template.

## Troubleshooting

### Services won't start

Check the logs to see what's wrong:

```bash
docker-compose logs
```

Make sure ports 80 and 443 aren't being used by another service:

```bash
sudo lsof -i :80
sudo lsof -i :443
```

If you need to start fresh:

```bash
docker-compose down -v
docker-compose up -d --build
```

### Database connection issues

Check if the database is healthy:

```bash
docker-compose ps db
```

Create tables if they're missing:

```bash
docker-compose exec -T calendar-api python - <<'PY'
from apps.shared.database import Base, engine
from apps.calendar.models import CalendarDay
Base.metadata.create_all(engine)
print("Tables created")
PY
```

Verify tables exist:

```bash
docker-compose exec db psql -U backend_user -d backend_db -c "\dt"
```

### Can't access the API

Make sure Caddy is running:

```bash
docker-compose ps caddy
docker-compose logs caddy
```

Test locally from the server:

```bash
curl http://localhost/calendar/health
```

Check your DNS is pointing to the server:

```bash
dig your-domain.com
```

## Monitoring

Check the health endpoint:

```bash
curl http://localhost/calendar/health
```

Monitor resource usage:

```bash
docker stats
docker system df
```

## Documentation

When running, API documentation is available at:

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI spec: `/openapi.json`

## Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Caddy Documentation](https://caddyserver.com/docs/)
