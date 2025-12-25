# vuhnger/backend

A lightweight FastAPI backend for Strava activity tracking and statistics. Built with Docker for easy deployment.

## Features

- **Strava OAuth Integration**: Complete OAuth 2.0 flow with automatic token refresh
- **Cached Statistics**: Hourly data refresh to minimize API calls and avoid rate limits
- **FastAPI**: Automatic OpenAPI documentation at `/docs`
- **PostgreSQL**: Persistent storage for OAuth tokens and cached stats
- **Docker**: Fully containerized for consistent deployment
- **API Key Authentication**: Protected admin endpoints
- **CORS**: Configured for frontend integration

## Quick Start

### Prerequisites

#### System Requirements

- **Docker**: 24.0.0 or higher
- **Docker Compose**: 2.20.0 or higher (included with Docker Desktop)
- **Git**: 2.30.0 or higher

**For local development without Docker (optional):**
- **Python**: 3.11.x
- **PostgreSQL**: 16.x

#### External Services

- **Strava API credentials** ([create app](https://www.strava.com/settings/api))
- **Server with domain** pointed to it (for OAuth callback in production)

**Check your versions:**
```bash
docker --version          # Should be 24.0.0+
docker compose version    # Should be 2.20.0+
python3 --version         # Should be 3.11.x (if not using Docker)
git --version             # Should be 2.30.0+
```

#### Python Dependencies

All Python dependencies are pinned to specific versions in `requirements.txt` for reproducible builds:

- **FastAPI**: 0.109.0
- **Uvicorn**: 0.27.0
- **SQLAlchemy**: 2.0.25
- **psycopg2-binary**: 2.9.9
- **stravalib**: 1.6.0
- **requests**: 2.31.0
- **cryptography**: 42.0.0

These are automatically installed when building the Docker image. For local development:
```bash
pip install -r requirements.txt
```

### Setup

1. Clone the repository:

```bash
git clone https://github.com/vuhnger/backend.git
cd backend
```

2. Create environment file:

```bash
cp .env.example .env
```

3. Configure `.env` with your credentials:

```env
# Database
POSTGRES_USER=backend_user
POSTGRES_PASSWORD=<generate_secure_password>
POSTGRES_DB=backend_db

# API Security
INTERNAL_API_KEY=<generate_secure_key>

# Strava OAuth
STRAVA_CLIENT_ID=<your_strava_client_id>
STRAVA_CLIENT_SECRET=<your_strava_client_secret>
STRAVA_REDIRECT_URI=https://api.yourdomain.com/strava/callback
```

Generate secure credentials:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

4. Start services:

```bash
docker compose up -d --build
```

5. Complete OAuth flow:

Navigate to `https://api.yourdomain.com/strava/authorize` to authenticate with Strava.

6. Set up automatic data refresh (cron):

```bash
crontab -e
```

Add this line to refresh data every hour:
```
0 * * * * docker exec backend-strava-api-1 python3 -m apps.strava.tasks
```

## API Endpoints

### Public Endpoints (no auth required)

#### `GET /strava/health`
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "service": "strava",
  "database": "connected"
}
```

#### `GET /strava/authorize`
Initiates OAuth flow. Redirects to Strava authorization page.

#### `GET /strava/callback`
OAuth callback endpoint. Strava redirects here after authorization.

**Query Parameters:**
- `code`: Authorization code from Strava
- `state`: CSRF protection token

#### `GET /strava/stats/ytd`
Returns cached year-to-date statistics.

**Response:**
```json
{
  "type": "ytd",
  "data": {
    "run": {
      "count": 193,
      "distance": 1594164.0,
      "moving_time": 547092,
      "elevation_gain": 12158.3
    },
    "ride": {
      "count": 47,
      "distance": 586384.0,
      "moving_time": 93970,
      "elevation_gain": 5344.0
    }
  },
  "fetched_at": "2025-12-24T14:26:11.661401+00:00"
}
```

**Units:**
- `distance`: meters
- `moving_time`: seconds
- `elevation_gain`: meters

#### `GET /strava/stats/activities`
Returns cached recent activities (last 30).

**Response:**
```json
{
  "type": "recent_activities",
  "data": [
    {
      "id": 12345678,
      "name": "Morning Run",
      "type": "Run",
      "distance": 5000.0,
      "moving_time": 1800,
      "elevation_gain": 50.0,
      "start_date": "2025-12-24T06:30:00Z"
    }
  ],
  "fetched_at": "2025-12-24T14:26:11.661401+00:00"
}
```

#### `GET /strava/stats/monthly`
Returns monthly aggregated statistics (last 12 months).

**Response:**
```json
{
  "type": "monthly",
  "data": {
    "2025-12": {
      "count": 15,
      "distance": 75000.0,
      "moving_time": 18000,
      "elevation_gain": 500.0
    },
    "2025-11": {
      "count": 20,
      "distance": 100000.0,
      "moving_time": 25000,
      "elevation_gain": 750.0
    }
  },
  "fetched_at": "2025-12-24T14:26:11.661401+00:00"
}
```

### Protected Endpoints (requires API key)

#### `POST /strava/refresh-data`
Manually trigger data refresh from Strava.

**Headers:**
- `X-API-Key`: Your internal API key

**Response:**
```json
{
  "status": "success",
  "message": "Data refreshed successfully"
}
```

## Frontend Integration

### CORS Configuration

The API is configured to accept requests from:
- `https://vuhnger.dev`
- `https://vuhnger.github.io`
- `http://localhost:5173` (for local development)

To add more origins, update `apps/strava/main.py`:

```python
origins = [
    "https://vuhnger.dev",
    "https://your-new-domain.com",
]
```

### Example: Fetch YTD Stats

```javascript
// Fetch year-to-date statistics
async function getYTDStats() {
  const response = await fetch('https://api.vuhnger.dev/strava/stats/ytd');
  const data = await response.json();

  console.log(`Runs this year: ${data.data.run.count}`);
  console.log(`Distance: ${(data.data.run.distance / 1000).toFixed(2)} km`);
  console.log(`Time: ${(data.data.run.moving_time / 3600).toFixed(1)} hours`);
}
```

### Example: Display Recent Activities

```javascript
async function getRecentActivities() {
  const response = await fetch('https://api.vuhnger.dev/strava/stats/activities');
  const data = await response.json();

  data.data.forEach(activity => {
    console.log(`${activity.name}: ${(activity.distance / 1000).toFixed(2)} km`);
  });
}
```

### Data Freshness

- Stats are cached and updated hourly (via cron job)
- Check the `fetched_at` timestamp to see when data was last updated
- OAuth tokens are automatically refreshed before each API call (expires after 6 hours)

## Architecture

```
┌─────────────┐
│   Caddy     │ (System service, HTTPS/SSL)
│   :443      │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│ strava-api  │────▶│  PostgreSQL  │
│   :5001     │     │    :5432     │
└─────────────┘     └──────────────┘
       │
       ▼
┌─────────────┐
│  Strava API │
│  (OAuth)    │
└─────────────┘
```

- **Caddy**: System-level reverse proxy (not in Docker)
- **strava-api**: FastAPI service, exposed on `127.0.0.1:5001`
- **PostgreSQL**: Database for tokens and cached stats
- Services communicate through Docker network `backend`

## Environment Variables

| Variable | Description | Required | Example |
|----------|-------------|----------|---------|
| `POSTGRES_USER` | Database username | Yes | `backend_user` |
| `POSTGRES_PASSWORD` | Database password | Yes | `K8mNpQrStUvWxYz...` |
| `POSTGRES_DB` | Database name | Yes | `backend_db` |
| `INTERNAL_API_KEY` | API authentication key | Yes* | `dhjklA79S...` |
| `STRAVA_CLIENT_ID` | Strava app client ID | Yes | `161983` |
| `STRAVA_CLIENT_SECRET` | Strava app client secret | Yes | `605d038931717...` |
| `STRAVA_REDIRECT_URI` | OAuth callback URL | Yes | `https://api.vuhnger.dev/strava/callback` |

*Required in production, optional in development

**Never commit your `.env` file.** Use `.env.example` as a template.

## Common Operations

### Deploying Updates

```bash
git pull
docker compose up -d --build
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Strava API only
docker compose logs -f strava-api

# Last 50 lines
docker compose logs --tail 50 strava-api
```

### Manual Data Refresh

```bash
# From inside the container
docker compose exec strava-api python3 -m apps.strava.tasks

# Via API endpoint (requires API key)
curl -X POST https://api.vuhnger.dev/strava/refresh-data \
  -H "X-API-Key: your_api_key_here"
```

### Database Access

```bash
# Connect to PostgreSQL
docker compose exec db psql -U backend_user -d backend_db

# View tables
docker compose exec db psql -U backend_user -d backend_db -c "\dt"

# Check cached stats
docker compose exec db psql -U backend_user -d backend_db \
  -c "SELECT stats_type, fetched_at FROM strava_stats;"

# Backup database
docker compose exec db pg_dump -U backend_user backend_db > backup.sql

# Restore from backup
cat backup.sql | docker compose exec -T db psql -U backend_user -d backend_db
```

### Restarting Services

```bash
# Restart everything
docker compose restart

# Restart API only
docker compose restart strava-api

# Stop and start (recreates containers)
docker compose down
docker compose up -d
```

## OAuth Flow

1. **User initiates**: Frontend redirects to `GET /strava/authorize`
2. **Strava auth**: User authorizes app on Strava's website
3. **Callback**: Strava redirects to `/strava/callback` with authorization code
4. **Token exchange**: Backend exchanges code for access + refresh tokens
5. **Store tokens**: Tokens stored in PostgreSQL (table: `strava_auth`)
6. **Initial fetch**: Backend fetches initial stats from Strava
7. **Redirect**: User redirected to frontend with `?strava=success`
8. **Auto-refresh**: Tokens automatically refreshed when they expire (< 1 hour remaining)

## Token Management

- **Access tokens** expire after 6 hours
- **Refresh tokens** are long-lived (used to get new access tokens)
- Token refresh happens automatically before each Strava API call
- No manual intervention needed

## Troubleshooting

### OAuth callback fails

Check that `STRAVA_REDIRECT_URI` in `.env` matches the redirect URI in your Strava app settings exactly.

```bash
# Check environment variable
docker compose exec strava-api env | grep STRAVA_REDIRECT_URI
```

### No stats available

Manually trigger data fetch:

```bash
docker compose exec strava-api python3 -m apps.strava.tasks
```

Check logs for errors:

```bash
docker compose logs strava-api | grep -i error
```

### Database connection issues

Verify database is healthy:

```bash
docker compose ps db
```

Test connection:

```bash
docker compose exec db pg_isready -U backend_user
```

Reset database (destroys all data):

```bash
docker compose down
docker volume rm backend_postgres_data
docker compose up -d
```

### Token refresh errors

Check stored token:

```bash
docker compose exec db psql -U backend_user -d backend_db \
  -c "SELECT athlete_id, expires_at, updated_at FROM strava_auth;"
```

Re-authenticate by visiting `/strava/authorize` again.

## Monitoring

### Health Check

```bash
curl https://api.vuhnger.dev/strava/health
```

### Resource Usage

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Volume size
docker volume inspect backend_postgres_data
```

### Check Cron Job

```bash
# List cron jobs
crontab -l

# Check cron logs (if available)
grep CRON /var/log/syslog
```

## API Documentation

Interactive API documentation is available when the service is running:

- **Swagger UI**: [https://api.vuhnger.dev/docs](https://api.vuhnger.dev/docs)
- **ReDoc**: [https://api.vuhnger.dev/redoc](https://api.vuhnger.dev/redoc)
- **OpenAPI Spec**: [https://api.vuhnger.dev/openapi.json](https://api.vuhnger.dev/openapi.json)

## Security

- OAuth tokens encrypted at rest using Fernet (AES-128-CBC)
- OAuth tokens encrypted in transit (HTTPS)
- API key required for admin endpoints
- CSRF protection in OAuth flow (128-bit HMAC-signed, time-bound state tokens per OWASP standards)
- CORS restricted to specific origins
- Constant-time API key comparison to prevent timing attacks
- Production environment enforcement for required secrets
- Database transactions with explicit rollback on failures
- Race-condition-free atomic upsert operations using PostgreSQL ON CONFLICT

## Development & Deployment Workflow

This project follows a Git-based deployment workflow: **develop locally → push to GitHub → deploy from nrec server**.

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/vuhnger/backend.git
   cd backend
   ```

2. **Create local environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Configure `.env` for local development:**
   ```env
   # Environment
   ENVIRONMENT=development

   # Database
   POSTGRES_USER=backend_user
   POSTGRES_PASSWORD=local_dev_password
   POSTGRES_DB=backend_db

   # API Security (optional for local dev)
   INTERNAL_API_KEY=dev_key_12345
   STATE_SECRET=dev_state_secret
   ENCRYPTION_KEY=dev_encryption_key

   # Strava OAuth (use test credentials)
   STRAVA_CLIENT_ID=your_dev_client_id
   STRAVA_CLIENT_SECRET=your_dev_client_secret
   STRAVA_REDIRECT_URI=http://localhost:5001/strava/callback

   # Frontend (for CORS)
   FRONTEND_URL=http://localhost:5173
   ```

4. **Start local development environment:**
   ```bash
   docker compose up -d --build
   ```

5. **View logs:**
   ```bash
   docker compose logs -f strava-api
   ```

6. **Access the API:**
   - API: http://localhost:5001
   - Docs: http://localhost:5001/docs
   - Health: http://localhost:5001/strava/health

### GitHub Workflow

1. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes and test locally:**
   ```bash
   # Make code changes
   docker compose up -d --build  # Rebuild if code changed
   docker compose restart strava-api  # Restart if only config changed
   ```

3. **Commit and push to GitHub:**
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin feature/your-feature-name
   ```

4. **Create pull request on GitHub** (optional, for review)

5. **Merge to main:**
   ```bash
   git checkout main
   git merge feature/your-feature-name
   git push origin main
   ```

### Initial Server Setup (One-Time)

**On nrec server:**

1. **SSH to server:**
   ```bash
   ssh nrec
   ```

2. **Clone repository:**
   ```bash
   cd ~
   git clone https://github.com/vuhnger/backend.git
   cd backend
   ```

3. **Create production environment file:**
   ```bash
   cp .env.example .env
   nano .env  # or vim .env
   ```

4. **Configure production `.env`:**
   ```env
   # Environment
   ENVIRONMENT=production

   # Database
   POSTGRES_USER=backend_user
   POSTGRES_PASSWORD=<generate_secure_password>
   POSTGRES_DB=backend_db

   # API Security - MUST be set in production
   INTERNAL_API_KEY=<generate_secure_key>
   STATE_SECRET=<generate_secure_key>
   ENCRYPTION_KEY=<generate_secure_key>

   # Strava OAuth
   STRAVA_CLIENT_ID=<production_client_id>
   STRAVA_CLIENT_SECRET=<production_client_secret>
   STRAVA_REDIRECT_URI=https://api.vuhnger.dev/strava/callback

   # Frontend
   FRONTEND_URL=https://vuhnger.dev
   ```

   Generate secure keys:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

5. **Start production services:**
   ```bash
   docker compose up -d --build
   ```

6. **Verify deployment:**
   ```bash
   # Check containers are running
   docker compose ps

   # Check logs
   docker compose logs -f strava-api

   # Test health endpoint
   curl https://api.vuhnger.dev/strava/health
   ```

7. **Complete OAuth authorization:**
   - Navigate to: https://api.vuhnger.dev/strava/authorize
   - Authorize with your Strava account

8. **Set up automatic data refresh:**
   ```bash
   crontab -e
   ```

   Add this line:
   ```
   0 * * * * docker exec backend-strava-api-1 python3 -m apps.strava.tasks >> /var/log/strava-fetch.log 2>&1
   ```

### Deployment Process (After Code Changes)

**Every time you make changes:**

1. **On local machine - push to GitHub:**
   ```bash
   git add .
   git commit -m "Your commit message"
   git push origin main
   ```

2. **On nrec server - deploy latest code:**
   ```bash
   ssh nrec
   cd ~/backend

   # Pull latest code from GitHub
   git pull origin main

   # Rebuild and restart containers
   docker compose up -d --build

   # Verify deployment
   docker compose ps
   docker compose logs --tail 50 strava-api
   curl https://api.vuhnger.dev/strava/health
   ```

### Quick Deployment Commands

**For code changes (requires rebuild):**
```bash
ssh nrec "cd ~/backend && git pull origin main && docker compose up -d --build"
```

**For config-only changes (faster, no rebuild):**
```bash
ssh nrec "cd ~/backend && git pull origin main && docker compose restart strava-api"
```

**View logs after deployment:**
```bash
ssh nrec "cd ~/backend && docker compose logs --tail 100 -f strava-api"
```

### Rollback Procedure

If deployment fails:

1. **Check what commit is currently deployed:**
   ```bash
   ssh nrec "cd ~/backend && git log -1 --oneline"
   ```

2. **Rollback to previous commit:**
   ```bash
   ssh nrec "cd ~/backend && git log --oneline -10"  # Find the commit hash
   ssh nrec "cd ~/backend && git reset --hard <previous-commit-hash> && docker compose up -d --build"
   ```

3. **Or rollback to a specific tag/release:**
   ```bash
   ssh nrec "cd ~/backend && git checkout v1.0.0 && docker compose up -d --build"
   ```

### Common Deployment Tasks

**Update environment variables (no code change):**
```bash
ssh nrec
cd ~/backend
nano .env  # Edit variables
docker compose restart strava-api  # Restart to load new env vars
```

**Database backup before deployment:**
```bash
ssh nrec "docker compose exec db pg_dump -U backend_user backend_db > ~/backup-$(date +%Y%m%d-%H%M%S).sql"
```

**Restore database:**
```bash
ssh nrec
cd ~/backend
cat backup-20251224-120000.sql | docker compose exec -T db psql -U backend_user -d backend_db
```

**View real-time logs:**
```bash
ssh nrec "cd ~/backend && docker compose logs -f strava-api"
```

**Restart specific service:**
```bash
ssh nrec "cd ~/backend && docker compose restart strava-api"
```

**Full system restart:**
```bash
ssh nrec "cd ~/backend && docker compose down && docker compose up -d"
```

**Check disk usage:**
```bash
ssh nrec "docker system df"
```

**Clean up old Docker images:**
```bash
ssh nrec "docker system prune -a"
```

### Deployment Checklist

Before deploying to production:

- [ ] All changes tested locally with `docker compose up`
- [ ] Code committed and pushed to GitHub main branch
- [ ] Database backup created (if schema changes)
- [ ] Environment variables updated on server (if needed)
- [ ] OAuth credentials configured (if new service)
- [ ] SSL certificates valid (check Caddy configuration)
- [ ] Health check passes after deployment
- [ ] Monitor logs for 5-10 minutes after deployment

### Troubleshooting Deployments

**Container won't start:**
```bash
ssh nrec "cd ~/backend && docker compose logs strava-api"
```

**Port conflicts:**
```bash
ssh nrec "sudo lsof -i :5001"  # Check what's using port 5001
```

**Database connection issues:**
```bash
ssh nrec "cd ~/backend && docker compose exec db pg_isready -U backend_user"
```

**Environment variable issues:**
```bash
ssh nrec "cd ~/backend && docker compose exec strava-api env | grep STRAVA"
```

**Force rebuild (if cached layers cause issues):**
```bash
ssh nrec "cd ~/backend && docker compose build --no-cache && docker compose up -d"
```

### Security Notes for Production Deployment

1. **Never commit `.env` file** - it's in `.gitignore` for a reason
2. **Use strong, unique keys** for all secret environment variables
3. **Set `ENVIRONMENT=production`** on nrec server
4. **Regularly backup the database** before deployments
5. **Monitor logs** after each deployment
6. **Keep dependencies updated** for security patches
7. **Review security audit** in `/plans/QA-REPORT.md` before major releases

## Resources

- [Strava API Documentation](https://developers.strava.com/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [stravalib Documentation](https://github.com/stravalib/stravalib)

## License

MIT
