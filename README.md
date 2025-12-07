# vuhnger/backend

A lightweight backend built with **FastAPI** and **Docker**, designed to run multiple small services (e.g., calendar, blog, Strava tracking).
The project is fully portable — it can run on NREC, local Docker, or any cloud provider that supports containers.

## 🚀 Features

- **FastAPI** with automatic OpenAPI documentation
- **Fully containerized** with Docker (Caddy + services)
- **PostgreSQL** database with persistent storage
- **Caddy** reverse proxy with automatic HTTPS
- **API key authentication** middleware
- **CORS** configured for production and development
- **Isolated Docker network** for inter-service communication
- **Multi-service architecture** ready for scaling

---

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

---

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

---

## 🛠 Initial Setup (First Time)

### Prerequisites

**On Your Local Machine:**
- Git installed
- SSH key configured for GitHub

**On Your Server (DigitalOcean):**
- Ubuntu 22.04+ droplet running
- Domain `api.vuhnger.dev` pointing to droplet IP
- Docker and Docker Compose installed
- SSH access configured

### Step 1: Clone Repository

**On the server:**

```bash
cd ~
git clone https://github.com/vuhnger/backend.git
cd backend
```

### Step 2: Configure Environment Variables

```bash
# Copy template
cp .env.example .env

# Edit with your values
nano .env
```

**Required configuration in `.env`:**

```env
# Database Configuration
POSTGRES_USER=backend_user
POSTGRES_PASSWORD=CHANGE_THIS_TO_SECURE_PASSWORD
POSTGRES_DB=backend_db

# API Security
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
INTERNAL_API_KEY=CHANGE_THIS_TO_RANDOM_KEY
```

**Generate secure values:**

```bash
# Generate secure password for database
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate API key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the generated values into your `.env` file.

### Step 3: Stop Existing Caddy (if running on host)

```bash
# Check if Caddy is running
sudo systemctl status caddy

# If running, stop and disable it
sudo systemctl stop caddy
sudo systemctl disable caddy
```

### Step 4: Start the Backend

```bash
# Build and start all services
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

**Expected output:**

```
NAME                COMMAND                  SERVICE       STATUS
backend-caddy-1     "caddy run --config …"   caddy         Up
backend-calendar-1  "uvicorn apps.calen…"    calendar-api  Up (healthy)
backend-db-1        "docker-entrypoint.s…"   db            Up (healthy)
```

### Step 5: Test the Deployment

```bash
# Test health endpoint
curl https://api.vuhnger.dev/calendar/health

# Expected output:
# {"status":"ok","service":"calendar","database":"connected"}

# Test API documentation
curl https://api.vuhnger.dev/docs
# Should return HTML
```

### Step 6: Configure Security

Follow the [SECURITY.md](SECURITY.md) guide to:

1. **SSH Hardening:**
   - Disable password authentication
   - Configure key-only access

2. **Firewall Setup:**
   - Create DigitalOcean firewall
   - Allow SSH from your home IP only
   - Allow HTTP/HTTPS from everywhere

3. **Backups:**
   - Enable DigitalOcean droplet backups
   - Configure database backups

### Step 7: Configure Frontend (Optional)

If you have a frontend application:

1. Copy example files from `frontend-examples/` to your frontend repo
2. Create `.env` in your frontend:

```env
VITE_API_BASE_URL=https://api.vuhnger.dev
VITE_API_KEY=your_api_key_from_backend_env
```

3. See [frontend-examples/README.md](frontend-examples/README.md) for integration instructions

---

## 🔄 Common Operations

### Deploy Code Updates

```bash
# On the server
cd ~/backend
git pull
docker-compose up -d --build
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f calendar-api

# Last 100 lines
docker-compose logs --tail=100 calendar-api
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart calendar-api

# Restart just Caddy (for config changes)
docker-compose restart caddy
```

### Database Operations

```bash
# Access PostgreSQL shell
docker-compose exec db psql -U backend_user -d backend_db

# Create database backup
docker-compose exec db pg_dump -U backend_user backend_db > backup_$(date +%Y%m%d).sql

# Restore from backup
cat backup_20251207.sql | docker-compose exec -T db psql -U backend_user -d backend_db
```

### Monitor Resource Usage

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Clean up unused images/containers
docker system prune -a
```

### Stop All Services

```bash
# Stop but keep data
docker-compose down

# Stop and remove all data (CAREFUL!)
docker-compose down -v
```

---

## 🏗️ Architecture

### Current Setup (Single Service)

```
Internet (HTTPS)
    ↓
Caddy (ports 80/443)
    ↓
calendar-api (port 5001) → PostgreSQL (port 5432)
```

### Components

| Component | Description | Exposed Ports |
|-----------|-------------|---------------|
| **caddy** | Reverse proxy with automatic HTTPS | 80, 443 |
| **calendar-api** | FastAPI service for calendar endpoints | None (internal) |
| **db** | PostgreSQL 16 database | None (internal) |

### Networking

- All services communicate via Docker network `backend`
- Only Caddy is exposed to the internet
- Services use Docker service names (e.g., `calendar-api:5001`, `db:5432`)
- SSL certificates managed automatically by Caddy

### Data Persistence

Volumes persist data across container restarts:

- `caddy_data` - SSL certificates
- `caddy_config` - Caddy configuration
- `postgres_data` - Database files

---

## 🚀 Scaling to Multiple Services

When ready to add more services (blog, strava):

### 1. Switch to Multi-Service Configuration

```bash
# Use the multi-service docker-compose
docker-compose -f docker-compose.multi.yml up -d --build

# Update Caddyfile
cp Caddyfile.multi Caddyfile
docker-compose restart caddy
```

### 2. Access Different Services

- Calendar: `https://api.vuhnger.dev/calendar/*`
- Blog: `https://api.vuhnger.dev/blog/*`
- Strava: `https://api.vuhnger.dev/strava/*`

See [ARCHITECTURE.md](ARCHITECTURE.md) for complete multi-service guide.

---

## 🧪 Local Development

### Running Locally

```bash
# Clone repo
git clone https://github.com/vuhnger/backend.git
cd backend

# Create .env (optional for local)
cp .env.example .env

# Start services
docker-compose up -d --build

# Access locally
curl http://localhost/calendar/health

# View docs
open http://localhost/docs
```

### Development Workflow

1. Make code changes
2. Rebuild: `docker-compose up -d --build`
3. Check logs: `docker-compose logs -f`
4. Test: `curl http://localhost/calendar/health`
5. Commit and push

---

## 🔐 Security

### Current Security Features

✅ **HTTPS** - Automatic via Caddy
✅ **API Key Authentication** - Optional middleware
✅ **CORS** - Configured for allowed origins
✅ **Isolated Network** - Services not exposed directly
✅ **Health Checks** - Database connection monitoring

### Recommended Security Steps

See [SECURITY.md](SECURITY.md) for:

- SSH hardening (key-only access)
- Firewall configuration (DigitalOcean)
- Automatic security updates
- Database backups
- Monitoring and logging

---

## 📝 Environment Variables Reference

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `POSTGRES_USER` | Database username | `backend_user` | Yes |
| `POSTGRES_PASSWORD` | Database password | `secure_random_password` | Yes |
| `POSTGRES_DB` | Database name | `backend_db` | Yes |
| `INTERNAL_API_KEY` | API authentication key | `random_api_key` | Optional |

**Security Note:** Never commit `.env` files to Git. Always use `.env.example` as a template.

---

## 🔧 Troubleshooting

### Services Won't Start

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs

# If Caddy is missing, ensure ports 80/443 are free (stop host caddy/nginx)
sudo systemctl status caddy

# Start just Caddy and watch for bind errors
docker-compose up -d caddy
docker-compose logs --tail=50 caddy

# Rebuild from scratch
docker-compose down -v
docker-compose up -d --build
```

### Database Connection Issues

```bash
# Check database is healthy
docker-compose ps db

# Access database directly
docker-compose exec db psql -U backend_user -d backend_db

# Check connection from calendar-api
docker-compose exec calendar-api python -c "from apps.shared.database import check_db_connection; print(check_db_connection())"

# If tables are missing, create them from inside the app container
docker-compose exec -T calendar-api python - <<'PY'
from apps.shared.database import Base, engine
from apps.calendar.models import CalendarDay
from sqlalchemy import inspect
Base.metadata.create_all(engine)
print("tables:", inspect(engine).get_table_names())
PY

# Verify tables in Postgres
docker-compose exec db psql -U backend_user -d backend_db -c "\dt"
```

### Caddy SSL Issues

```bash
# Check Caddy logs
docker-compose logs caddy

# Verify domain DNS
dig api.vuhnger.dev

# Restart Caddy
docker-compose restart caddy
```

### API Not Accessible

```bash
# Check firewall allows ports 80/443
sudo ufw status

# Check Caddy is running
docker-compose ps caddy
docker-compose logs --tail=50 caddy

# Test from server
curl http://localhost/calendar/health

# Check DNS
nslookup api.vuhnger.dev
```

### Out of Disk Space

```bash
# Check usage
df -h

# Clean Docker
docker system prune -a

# Remove old images
docker image prune -a
```

---

## 📊 Monitoring

### Health Endpoints

- Calendar: `https://api.vuhnger.dev/calendar/health`
- Returns: `{"status":"ok","service":"calendar","database":"connected"}`

### Check Service Status

```bash
# Container status
docker-compose ps

# Resource usage
docker stats

# Logs
docker-compose logs --tail=50
```

### Set Up Monitoring (Optional)

Consider adding:
- **Uptime monitoring** - UptimeRobot, Healthchecks.io
- **Error tracking** - Sentry
- **Logging** - Papertrail, Loggly
- **Metrics** - Prometheus + Grafana

---

## 🔗 Useful Commands Cheatsheet

```bash
# === Deployment ===
git pull && docker-compose up -d --build    # Deploy updates
docker-compose restart calendar-api         # Restart service
docker-compose logs -f calendar-api         # View logs

# === Database ===
docker-compose exec db psql -U backend_user -d backend_db  # DB shell
docker-compose exec db pg_dump -U backend_user backend_db > backup.sql  # Backup
docker-compose exec -T calendar-api python - <<'PY'        # Create tables from app container
from apps.shared.database import Base, engine
from apps.calendar.models import CalendarDay
Base.metadata.create_all(engine)
print("tables created")
PY

# === Monitoring ===
docker-compose ps                           # Service status
docker stats                                # Resource usage
docker-compose logs --tail=100 -f          # Recent logs

# === Maintenance ===
docker-compose down                         # Stop all
docker system prune -a                      # Clean up
docker-compose up -d --build                # Rebuild all

# === Seeding (if curl not installed in app container) ===
docker-compose exec -T calendar-api python - <<'PY'
import json
from apps.shared.database import SessionLocal, Base, engine
from apps.calendar.models import CalendarDay
from sqlalchemy import inspect

Base.metadata.create_all(engine)
with open("/app/calendar-data.json") as f:
    payload = json.load(f)

db = SessionLocal()
count = 0
for day_str, day_data in payload.items():
    day_number = int(day_str)
    day_type = day_data["type"]
    data = {k: v for k, v in day_data.items() if k != "type"}
    existing = db.query(CalendarDay).filter_by(day=day_number).first()
    if existing:
        existing.type = day_type
        existing.data = data
    else:
        db.add(CalendarDay(day=day_number, type=day_type, data=data))
    count += 1
db.commit()
db.close()
print(f"Seeded {count} days; tables: {inspect(engine).get_table_names()}")
PY
```

---

## 🎯 Next Steps

- [ ] Complete initial deployment following setup steps
- [ ] Configure security (SSH, firewall, backups)
- [ ] Test health endpoint: `https://api.vuhnger.dev/calendar/health`
- [ ] Test API docs: `https://api.vuhnger.dev/docs`
- [ ] Implement calendar business logic (when ready)
- [ ] Add blog service (when ready)
- [ ] Add strava service (when ready)
- [ ] Set up monitoring and alerts

---

## 📞 Support

**Documentation:**
- [ARCHITECTURE.md](ARCHITECTURE.md) - Multi-service design
- [SECURITY.md](SECURITY.md) - Security hardening
- [API_KEY_USAGE.md](API_KEY_USAGE.md) - Authentication

**Resources:**
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
- [Caddy Docs](https://caddyserver.com/docs/)
- [DigitalOcean Docs](https://docs.digitalocean.com/)

---

**Last updated:** 2025-12-07
**Domain:** api.vuhnger.dev
**Repository:** https://github.com/vuhnger/backend
