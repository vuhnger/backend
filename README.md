
# vuhnger/backend

FastAPI backend for Strava activity tracking with OAuth, cached statistics, and encrypted token storage.

## Features

- OAuth 2.0 integration with automatic token refresh
- Hourly cached statistics (YTD, recent activities, monthly aggregates)
- Encrypted tokens at rest (Fernet AES-128)
- CSRF-protected OAuth flow (128-bit HMAC)
- Race-condition-free database operations
- CORS configured for frontend integration

## Quick Start

### Prerequisites

- **Docker & Docker Compose**: Version 24.0+ and 2.20+ respectively
- **Domain with SSL**: Required for production OAuth (Strava requires HTTPS callbacks)
- **Strava API Application**: Register at [https://www.strava.com/settings/api](https://www.strava.com/settings/api)

### Step 1: Create Strava Application

1. Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. Create a new application with these settings:
   - **Application Name**: Your app name (e.g., "My Activity Tracker")
   - **Category**: Choose appropriate category
   - **Website**: Your frontend URL (e.g., `https://yourdomain.com`)
   - **Authorization Callback Domain**: Your API domain (e.g., `api.yourdomain.com`)
     - For local development: `localhost`
3. Save the application and note your:
   - **Client ID** (visible on the page)
   - **Client Secret** (click "Show" to reveal)

### Step 2: Clone and Configure

```bash
git clone https://github.com/vuhnger/backend.git
cd backend
cp .env.example .env
```

### Step 3: Configure Environment Variables

Edit `.env` with your settings:

```env
# Environment Mode
ENVIRONMENT=production  # Use 'development' for local testing

# Database Configuration
# IMPORTANT: Generate a secure password (see command below)
POSTGRES_USER=backend_user
POSTGRES_PASSWORD=<GENERATE_SECURE_PASSWORD>
POSTGRES_DB=backend_db

# Security Keys (REQUIRED in production)
# These protect OAuth state, API access, and stored tokens
INTERNAL_API_KEY=<GENERATE_KEY>      # Protects /refresh-data endpoint
STATE_SECRET=<GENERATE_KEY>          # Signs OAuth state tokens (CSRF protection)
ENCRYPTION_KEY=<GENERATE_KEY>        # Encrypts stored OAuth tokens (AES-128)

# Strava OAuth Credentials (from Step 1)
STRAVA_CLIENT_ID=<your_client_id_from_strava>
STRAVA_CLIENT_SECRET=<your_client_secret_from_strava>
STRAVA_REDIRECT_URI=https://api.yourdomain.com/strava/callback
# For local dev: http://localhost:5001/strava/callback

# Frontend CORS (optional)
FRONTEND_URL=https://yourdomain.com
# For local dev: http://localhost:5173
```

**Generate secure keys** by running this command **4 times** (once for each secret):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use the output to replace:
- `<GENERATE_SECURE_PASSWORD>` → Database password
- `<GENERATE_KEY>` → INTERNAL_API_KEY
- `<GENERATE_KEY>` → STATE_SECRET
- `<GENERATE_KEY>` → ENCRYPTION_KEY

**Important**: Each key must be unique. Never reuse keys across variables or environments.

### Step 4: Production Server Setup (Skip for Local Development)

If deploying to production, set up your server first:

#### Domain and SSL Configuration

1. **DNS Setup**: Point your API subdomain to your server
   ```bash
   # Example DNS A record
   api.yourdomain.com → 123.45.67.89 (your server IP)
   ```

2. **SSL Certificate**: Install SSL on your server (required for OAuth)

   **Option A: Using Caddy (Recommended)**
   ```bash
   # Caddy automatically handles SSL with Let's Encrypt
   # Configure Caddyfile:
   api.yourdomain.com {
       reverse_proxy localhost:5001
   }
   ```

   **Option B: Using Nginx + Certbot**
   ```bash
   sudo apt update
   sudo apt install nginx certbot python3-certbot-nginx
   sudo certbot --nginx -d api.yourdomain.com
   ```

3. **Firewall**: Ensure ports 80 and 443 are open
   ```bash
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

#### Clone Repository on Server

```bash
ssh user@your-server
cd ~
git clone https://github.com/vuhnger/backend.git
cd backend
cp .env.example .env
nano .env  # Edit with your production values
```

### Step 5: Initialize Database and Start Services

This step creates the PostgreSQL database with your password for the first time.

```bash
# Start all services
docker compose up -d --build

# Wait ~10 seconds for database to initialize

# Verify database is running
docker compose exec db pg_isready -U backend_user
# Expected output: "db:5432 - accepting connections"

# Check API logs for errors
docker compose logs strava-api
# Look for: "Application startup complete"

# Verify services are up
docker compose ps
# All services should show "Up"
```

**Common startup issues**:
- If database fails to start, check `docker compose logs db`
- If API can't connect, verify `POSTGRES_PASSWORD` matches in `.env`
- If port conflicts, check nothing else is using port 5001

### Step 6: Complete OAuth Authorization

This exchanges your Strava credentials for access tokens.

1. **Navigate to authorization URL**:
   - Production: `https://api.yourdomain.com/strava/authorize`
   - Local dev: `http://localhost:5001/strava/authorize`

2. **Authorize the application** on Strava's page

3. **Verify success**:
   - You'll be redirected to your frontend with `?strava=success`
   - Check API logs: `docker compose logs strava-api --tail 20`
   - You should see: "All Strava data cached successfully"

4. **Test the API**:
   ```bash
   curl https://api.yourdomain.com/strava/health
   # Expected: {"status":"ok","service":"strava","database":"connected"}

   curl https://api.yourdomain.com/strava/stats/ytd
   # Expected: JSON with your year-to-date stats
   ```

### Step 7: Setup Automatic Data Refresh (Optional)

The API caches your Strava data to reduce API calls. Set up a cron job to refresh it hourly.

```bash
# Open crontab editor
crontab -e

# Add this line (runs every hour at :00)
0 * * * * docker exec backend-strava-api-1 python3 -m apps.strava.tasks >> /var/log/strava.log 2>&1
```

**What this does**:
- Fetches fresh data from Strava API every hour
- Updates cached YTD stats, recent activities, and monthly aggregates
- Logs output to `/var/log/strava.log` for debugging

**Alternative**: Manually refresh anytime:
```bash
curl -X POST https://api.yourdomain.com/strava/refresh-data \
  -H "X-API-Key: your-INTERNAL_API_KEY"
```

## Troubleshooting

### Password Authentication Failed

**Error**: `password authentication failed for user "backend_user"`

**Cause**: The database volume was created with a different password than what's currently in your `.env` file. This commonly happens when:
- You changed `POSTGRES_PASSWORD` after first run
- You copied `.env` from another environment
- The database volume persisted from a previous installation

**Fix** (⚠️ This deletes all data):
```bash
# Stop all services
docker compose down

# Remove the database volume (THIS DELETES ALL DATA)
docker volume rm backend_postgres_data

# Update .env with NEW password
nano .env  # Set POSTGRES_PASSWORD to a new secure value

# Recreate with new password
docker compose up -d --build

# Wait for startup, then re-authorize OAuth
# Visit: https://api.yourdomain.com/strava/authorize
```

**Preserve Data Fix** (if you have important data):
```bash
# Option 1: Keep using the old password
# Just revert POSTGRES_PASSWORD in .env to the original value

# Option 2: Change password inside running container
docker compose exec db psql -U backend_user -d postgres -c \
  "ALTER USER backend_user WITH PASSWORD 'your-new-password';"
# Then update .env to match and restart
docker compose restart strava-api
```

### Container Won't Start

**Symptoms**: `docker compose ps` shows container as "Exit 1" or constantly restarting

**Debug steps**:
```bash
# Check API logs for Python errors
docker compose logs strava-api --tail 100

# Check database logs
docker compose logs db --tail 50

# Verify database connection
docker compose exec db psql -U backend_user -d backend_db -c "SELECT 1"

# Check environment variables are loaded
docker compose exec strava-api env | grep STRAVA

# Verify database tables exist
docker compose exec db psql -U backend_user -d backend_db -c "\dt"
```

**Common causes**:
- Missing environment variables → Check all required vars in `.env`
- Database not ready → Wait 10-15 seconds after `docker compose up`
- Port conflict → Check if port 5001 is already in use
- Invalid encryption key → Must be valid base64 from `secrets.token_urlsafe(32)`

### OAuth Callback Fails

**Error**: "Invalid or expired state parameter" or redirect fails

**Fixes**:
1. **Verify redirect URI matches exactly**:
   ```bash
   # In .env
   STRAVA_REDIRECT_URI=https://api.yourdomain.com/strava/callback

   # Must match Strava app settings (including https://)
   # Go to: https://www.strava.com/settings/api
   # Authorization Callback Domain: api.yourdomain.com
   ```

2. **Check STATE_SECRET is set**:
   ```bash
   docker compose exec strava-api env | grep STATE_SECRET
   # Should output a long random string
   ```

3. **Clear browser cookies** and try authorization again

4. **Check logs** for detailed error:
   ```bash
   docker compose logs strava-api --tail 20
   ```

### No Data Returned from Stats Endpoints

**Error**: `{"detail": "YTD stats not cached yet. Try /strava/refresh-data"}`

**Cause**: OAuth completed but initial data fetch failed

**Fix**:
```bash
# Manually trigger data fetch
curl -X POST https://api.yourdomain.com/strava/refresh-data \
  -H "X-API-Key: your-INTERNAL_API_KEY"

# Check if it worked
curl https://api.yourdomain.com/strava/stats/ytd

# If still failing, check logs
docker compose logs strava-api --tail 50
```

### SSL/HTTPS Issues in Production

**Error**: OAuth redirect fails or shows "Not Secure" warning

**Fix**:
```bash
# Verify SSL certificate is installed
sudo certbot certificates

# Check Caddy/Nginx is proxying correctly
curl -I https://api.yourdomain.com/strava/health
# Should return: HTTP/2 200

# Verify Strava app uses HTTPS callback
# In Strava app settings:
# ✓ https://api.yourdomain.com/strava/callback
# ✗ http://api.yourdomain.com/strava/callback
```

### Database Volume Issues

**Reset everything** (⚠️ deletes all data):
```bash
docker compose down -v  # Removes all volumes
docker compose up -d --build
# Re-authorize OAuth
```

**List volumes**:
```bash
docker volume ls | grep backend
```

**Inspect volume**:
```bash
docker volume inspect backend_postgres_data
```

## How Data Caching Works

This API implements an **hourly cache layer** between your frontend and Strava's API to reduce rate limits and improve response times.

### Data Flow

```
Frontend Request → API Cache → Strava API (if cache expired)
                     ↓
                 Database
```

1. **Initial OAuth**: When you authorize, the API fetches and caches:
   - Year-to-date totals (runs + rides)
   - Last 30 activities
   - Monthly aggregates (12 months)

2. **Subsequent Requests**: Frontend gets instant responses from database cache

3. **Automatic Refresh**: Cron job updates cache every hour (optional, see Step 7)

4. **Manual Refresh**: Use `/strava/refresh-data` endpoint anytime

### Cache Expiration

- **Database storage**: Cached stats stored in `strava_stats` table
- **Refresh frequency**: Hourly (via cron) or manual
- **Token refresh**: Automatic when tokens expire (handled transparently)

### Why Caching?

- **Strava Rate Limits**: 100 requests per 15 minutes, 1000 per day
- **Response Speed**: Database queries are 10-100x faster than API calls
- **Offline Resilience**: Frontend works even if Strava API is down (serves last cached data)

## API Endpoints

All endpoints available at `https://api.yourdomain.com`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/strava/health` | GET | None | Health check endpoint |
| `/strava/authorize` | GET | None | Start OAuth flow (redirects to Strava) |
| `/strava/callback` | GET | None | OAuth callback (Strava redirects here) |
| `/strava/stats/ytd` | GET | None | Year-to-date run + ride totals |
| `/strava/stats/activities` | GET | None | Recent 30 activities with details |
| `/strava/stats/monthly` | GET | None | Monthly aggregates (last 12 months) |
| `/strava/refresh-data` | POST | API Key | Manually trigger data refresh from Strava |

**Interactive API Docs**: `https://api.yourdomain.com/docs` (Swagger UI)

### Response Format

All stats endpoints return:
```json
{
  "type": "ytd|recent_activities|monthly",
  "data": { /* stats data */ },
  "fetched_at": "2025-12-25T12:00:00+00:00"
}
```

**Units**: Distance (meters), Time (seconds), Elevation (meters)

### Example Responses

**YTD Stats** (`/strava/stats/ytd`):
```json
{
  "type": "ytd",
  "data": {
    "run": {
      "count": 42,
      "distance": 312500.0,
      "moving_time": 54000,
      "elevation_gain": 1250.0
    },
    "ride": {
      "count": 15,
      "distance": 450000.0,
      "moving_time": 72000,
      "elevation_gain": 2100.0
    }
  },
  "fetched_at": "2025-12-25T12:00:00+00:00"
}
```

**Recent Activities** (`/strava/stats/activities`):
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
      "start_date": "2025-12-25T08:00:00Z"
    }
  ],
  "fetched_at": "2025-12-25T12:00:00+00:00"
}
```

**Monthly Stats** (`/strava/stats/monthly`):
```json
{
  "type": "monthly",
  "data": {
    "2025-12": {
      "count": 12,
      "distance": 85000.0,
      "moving_time": 14400,
      "elevation_gain": 420.0
    },
    "2025-11": { /* ... */ }
  },
  "fetched_at": "2025-12-25T12:00:00+00:00"
}
```

## Frontend Integration

### Basic Fetch

```javascript
// Fetch YTD stats
const response = await fetch('https://api.yourdomain.com/strava/stats/ytd');
const { data, fetched_at } = await response.json();

console.log(`Runs: ${data.run.count}`);
console.log(`Distance: ${(data.run.distance / 1000).toFixed(2)} km`);
console.log(`Time: ${(data.run.moving_time / 3600).toFixed(1)} hours`);
```

### TypeScript Types

```typescript
interface StravaStats {
  count: number;
  distance: number;     // meters
  moving_time: number;  // seconds
  elevation_gain: number;
}

interface YTDResponse {
  type: 'ytd';
  data: { run: StravaStats; ride: StravaStats };
  fetched_at: string;
}
```

### React Hook Example

```typescript
function useStravaStats<T>(endpoint: string) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`https://api.yourdomain.com${endpoint}`)
      .then(res => res.json())
      .then(setData)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [endpoint]);

  return { data, loading, error };
}

// Usage
function YTDStats() {
  const { data, loading, error } = useStravaStats<YTDResponse>('/strava/stats/ytd');

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h2>This Year</h2>
      <p>Runs: {data.data.run.count}</p>
      <p>Distance: {(data.data.run.distance / 1000).toFixed(2)} km</p>
    </div>
  );
}
```

### CORS Configuration

The API accepts requests from:
- `https://vuhnger.dev`
- `https://vuhnger.github.io`
- `http://localhost:5173` (development)

Add more origins in `apps/strava/main.py`:
```python
origins = [
    "https://vuhnger.dev",
    "https://your-new-domain.com",
]
```

## Production Deployment Checklist

Before deploying to production, ensure you've completed all steps:

### Pre-Deployment

- [ ] **Server provisioned** with Docker 24.0+ and Docker Compose 2.20+
- [ ] **Domain configured** with DNS pointing to your server IP
- [ ] **SSL certificate** installed (Caddy or Certbot)
- [ ] **Firewall rules** set (ports 80, 443 open)
- [ ] **Strava app created** with correct callback domain
- [ ] **Environment variables** set in `.env` with production values:
  - [ ] All 4 security keys generated uniquely
  - [ ] `ENVIRONMENT=production`
  - [ ] `POSTGRES_PASSWORD` is cryptographically secure
  - [ ] `STRAVA_REDIRECT_URI` uses HTTPS
  - [ ] Strava credentials copied correctly

### Initial Deployment

```bash
# On your production server
cd ~
git clone https://github.com/vuhnger/backend.git
cd backend

# Configure environment
cp .env.example .env
nano .env  # Fill in all production values

# Start services
docker compose up -d --build

# Verify everything is running
docker compose ps
docker compose logs strava-api --tail 50

# Test health endpoint
curl https://api.yourdomain.com/strava/health
# Expected: {"status":"ok","service":"strava","database":"connected"}
```

### Post-Deployment

- [ ] **Complete OAuth flow** by visiting `/strava/authorize`
- [ ] **Verify data caching** - check `/strava/stats/ytd` returns data
- [ ] **Setup cron job** for hourly refreshes (Step 7)
- [ ] **Configure monitoring** (optional, see below)
- [ ] **Test frontend integration** with your actual frontend app
- [ ] **Setup database backups** (see Database Backup section)

### Monitoring (Recommended)

**Basic Monitoring**:
```bash
# Check service health
curl https://api.yourdomain.com/strava/health

# Monitor logs in real-time
docker compose logs -f strava-api

# Check resource usage
docker stats

# Database connections
docker compose exec db psql -U backend_user -d backend_db -c \
  "SELECT count(*) FROM pg_stat_activity WHERE datname='backend_db';"
```

**Log Rotation** (prevent disk space issues):
```bash
# Create logrotate config
sudo nano /etc/logrotate.d/strava-backend

# Add:
/var/log/strava.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

**Uptime Monitoring**:
- Use services like UptimeRobot, Pingdom, or StatusCake
- Monitor: `https://api.yourdomain.com/strava/health`
- Alert if status code ≠ 200 or response doesn't contain `"status":"ok"`

## Deployment Operations

### Update Production

```bash
# On your server
cd ~/backend
git pull origin main
docker compose up -d --build

# Verify deployment
docker compose ps
docker compose logs --tail 50 strava-api
curl https://api.yourdomain.com/strava/health

# Check data is still accessible
curl https://api.yourdomain.com/strava/stats/ytd
```

### Rollback to Previous Version

```bash
# View recent commits
git log --oneline -10

# Reset to previous working commit
git reset --hard <commit-hash>

# Rebuild and restart
docker compose up -d --build

# Verify rollback worked
curl https://api.yourdomain.com/strava/health
```

### Zero-Downtime Updates

For critical updates without downtime:

```bash
# Pull latest code
git pull origin main

# Build new image without stopping services
docker compose build

# Rolling restart (stops old, starts new)
docker compose up -d --no-deps --build strava-api

# Verify
curl https://api.yourdomain.com/strava/health
```

### Database Backup and Restore

**Backup** (run regularly, e.g., daily cron job):
```bash
# Create timestamped backup
docker compose exec db pg_dump -U backend_user backend_db \
  > backup-$(date +%Y%m%d-%H%M%S).sql

# Compress to save space
gzip backup-*.sql
```

**Restore** (in case of data loss):
```bash
# Stop API to prevent writes during restore
docker compose stop strava-api

# Restore from backup
cat backup-20251225-120000.sql | \
  docker compose exec -T db psql -U backend_user -d backend_db

# Restart API
docker compose start strava-api

# Re-authorize OAuth if tokens were affected
# Visit: https://api.yourdomain.com/strava/authorize
```

**Automated Daily Backups** (recommended):
```bash
# Create backup script
cat > ~/backup-strava.sh << 'EOF'
#!/bin/bash
cd ~/backend
mkdir -p ~/backups
docker compose exec db pg_dump -U backend_user backend_db \
  | gzip > ~/backups/strava-$(date +%Y%m%d).sql.gz

# Keep only last 30 days
find ~/backups -name "strava-*.sql.gz" -mtime +30 -delete
EOF

chmod +x ~/backup-strava.sh

# Add to crontab (runs daily at 3 AM)
crontab -e
# Add: 0 3 * * * ~/backup-strava.sh
```

## Architecture

```
┌─────────────┐
│   Caddy     │ HTTPS/SSL
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

## Security

- OAuth tokens encrypted at rest (Fernet AES-128)
- CSRF protection (128-bit HMAC-signed state tokens)
- API key auth for admin endpoints (constant-time comparison)
- Explicit database rollback on failures
- Race-condition-free atomic upserts
- CORS restricted to allowed origins
- Secrets required in production mode

## Environment Variables Reference

### Core Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | No | `development` | Runtime mode: `production` or `development`. Production enforces security key requirements. |

### Database Configuration

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `POSTGRES_USER` | Yes | `backend_user` | PostgreSQL username. Used by both API and database containers. |
| `POSTGRES_PASSWORD` | Yes | `<generated>` | PostgreSQL password. **CRITICAL**: Must be set before first `docker compose up`. Generate with `secrets.token_urlsafe(32)`. Changing this after database creation requires volume deletion (see Troubleshooting). |
| `POSTGRES_DB` | Yes | `backend_db` | PostgreSQL database name. Created automatically on first startup. |

**Internal Connection String** (automatically constructed):
```
postgresql://backend_user:<POSTGRES_PASSWORD>@db:5432/backend_db
```

### Security Keys

All security keys must be cryptographically secure random strings. Generate each with:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

| Variable | Required | Length | Description |
|----------|----------|--------|-------------|
| `INTERNAL_API_KEY` | Yes* | 32+ bytes | Protects admin endpoints (e.g., `/strava/refresh-data`). Include in requests as `X-API-Key` header. Uses constant-time comparison to prevent timing attacks. |
| `STATE_SECRET` | Yes* | 32+ bytes | HMAC signing key for OAuth state tokens. Prevents CSRF attacks by signing per-request state parameters with 128-bit HMAC. State tokens expire after 10 minutes. |
| `ENCRYPTION_KEY` | Yes* | 32+ bytes | Fernet (AES-128-CBC) encryption key for OAuth tokens at rest. Tokens are encrypted before database storage and decrypted on read. **Never rotate this key** without migrating existing tokens or you'll lose access. |

\* Required when `ENVIRONMENT=production`. Optional in development (but recommended).

**Security Notes**:
- Each key must be unique (never reuse keys)
- Store keys securely (use environment variables, never commit to git)
- Rotation requires data migration (tokens encrypted with old keys become unreadable)
- Keys use URL-safe base64 encoding (A-Z, a-z, 0-9, -, _)

### Strava OAuth Configuration

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `STRAVA_CLIENT_ID` | Yes | `161983` | Strava application client ID. Get from [https://www.strava.com/settings/api](https://www.strava.com/settings/api) after creating your app. |
| `STRAVA_CLIENT_SECRET` | Yes | `a1b2c3d4...` | Strava application client secret. Click "Show" on Strava settings page to reveal. **Keep secret** - never expose in frontend code. |
| `STRAVA_REDIRECT_URI` | Yes | `https://api.yourdomain.com/strava/callback` | OAuth callback URL. Must exactly match "Authorization Callback Domain" in Strava app settings. For local dev: `http://localhost:5001/strava/callback`. **Must use HTTPS in production** (Strava requirement). |

**OAuth Flow**:
1. User visits `/strava/authorize`
2. Redirected to Strava with `client_id` and `redirect_uri`
3. User authorizes app
4. Strava redirects back to `STRAVA_REDIRECT_URI` with authorization code
5. API exchanges code for access/refresh tokens using `client_secret`
6. Tokens encrypted with `ENCRYPTION_KEY` and stored in database

### Frontend Integration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `FRONTEND_URL` | No | `https://vuhnger.dev` | Frontend origin for CORS. After OAuth, users are redirected to `{FRONTEND_URL}/?strava=success`. Also added to CORS allowed origins. For local dev: `http://localhost:5173`. Multiple origins must be configured in code (see apps/strava/main.py:34). |

### Development vs Production

**Development** (`ENVIRONMENT=development`):
```env
ENVIRONMENT=development
POSTGRES_PASSWORD=devpass123  # Simple password OK for local
# Security keys optional (but recommended for testing OAuth)
STRAVA_REDIRECT_URI=http://localhost:5001/strava/callback
FRONTEND_URL=http://localhost:5173
```

**Production** (`ENVIRONMENT=production`):
```env
ENVIRONMENT=production
POSTGRES_PASSWORD=<32-byte-random-string>
INTERNAL_API_KEY=<32-byte-random-string>  # REQUIRED
STATE_SECRET=<32-byte-random-string>       # REQUIRED
ENCRYPTION_KEY=<32-byte-random-string>     # REQUIRED
STRAVA_REDIRECT_URI=https://api.yourdomain.com/strava/callback  # MUST be HTTPS
FRONTEND_URL=https://yourdomain.com
```

## Common Commands

```bash
# View logs
docker compose logs -f strava-api

# Manual data refresh
docker compose exec strava-api python3 -m apps.strava.tasks

# Database shell
docker compose exec db psql -U backend_user -d backend_db

# Restart API
docker compose restart strava-api

# Clean rebuild
docker compose down
docker compose up -d --build

# Check resource usage
docker stats
```

## Development

### Local Setup (without Docker)

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Setup local PostgreSQL
createdb backend_db
psql backend_db < schema.sql

# Run locally
uvicorn apps.strava.main:app --reload --port 5001
```

### Run Tests

```bash
pytest
flake8 apps/ --max-line-length=120
mypy apps/ --ignore-missing-imports
```

## License

MIT

## Resources

- [Strava API Docs](https://developers.strava.com/docs/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Docker Compose Docs](https://docs.docker.com/compose/)
