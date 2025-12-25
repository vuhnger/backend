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

- Docker 24.0+ and Docker Compose 2.20+
- Strava API credentials ([create app](https://www.strava.com/settings/api))
- Domain with SSL for production OAuth callback

### Setup

1. **Clone and configure**

```bash
git clone https://github.com/vuhnger/backend.git
cd backend
cp .env.example .env
```

2. **Edit `.env` file**

```env
# Environment
ENVIRONMENT=production  # or 'development' for local

# Database (IMPORTANT: Generate secure password below)
POSTGRES_USER=backend_user
POSTGRES_PASSWORD=<GENERATE_NEW_PASSWORD>
POSTGRES_DB=backend_db

# Security Keys (REQUIRED in production)
INTERNAL_API_KEY=<GENERATE_KEY>
STATE_SECRET=<GENERATE_KEY>
ENCRYPTION_KEY=<GENERATE_KEY>

# Strava OAuth
STRAVA_CLIENT_ID=<your_client_id>
STRAVA_CLIENT_SECRET=<your_client_secret>
STRAVA_REDIRECT_URI=https://api.yourdomain.com/strava/callback

# Frontend CORS (optional, defaults shown)
FRONTEND_URL=https://yourdomain.com
```

**Generate secure keys:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run this 3 times to generate unique values for PASSWORD, INTERNAL_API_KEY, STATE_SECRET, and ENCRYPTION_KEY.

3. **First-time database initialization**

```bash
# Start services (this creates the database with your password)
docker compose up -d --build

# Verify database is running
docker compose exec db pg_isready -U backend_user

# Check logs for errors
docker compose logs strava-api
```

4. **Complete OAuth**

Navigate to `https://api.yourdomain.com/strava/authorize` and authorize with Strava.

5. **Setup auto-refresh (optional)**

```bash
crontab -e
```

Add:
```
0 * * * * docker exec backend-strava-api-1 python3 -m apps.strava.tasks >> /var/log/strava.log 2>&1
```

## Troubleshooting

### Password Authentication Failed

If you get `password authentication failed for user "backend_user"`:

**Cause**: Database was created with a different password than what's in your `.env` file.

**Fix**:
```bash
# Stop all services
docker compose down

# Remove the database volume (THIS DELETES ALL DATA)
docker volume rm backend_postgres_data

# Update .env with NEW password
nano .env  # Set POSTGRES_PASSWORD to new value

# Recreate with new password
docker compose up -d --build

# Re-authorize OAuth
# Visit: https://api.yourdomain.com/strava/authorize
```

### Container Won't Start

```bash
# Check logs
docker compose logs strava-api

# Check database
docker compose exec db psql -U backend_user -d backend_db -c "SELECT 1"
```

### OAuth Callback Fails

Verify `STRAVA_REDIRECT_URI` in `.env` exactly matches your Strava app settings (including https://).

## API Endpoints

All endpoints available at `https://api.yourdomain.com`

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/strava/health` | GET | None | Health check |
| `/strava/authorize` | GET | None | Start OAuth flow |
| `/strava/callback` | GET | None | OAuth callback |
| `/strava/stats/ytd` | GET | None | Year-to-date stats |
| `/strava/stats/activities` | GET | None | Recent 30 activities |
| `/strava/stats/monthly` | GET | None | Monthly aggregates (12 months) |
| `/strava/refresh-data` | POST | API Key | Manual data refresh |

**API Docs**: `https://api.yourdomain.com/docs`

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

## Deployment

### Update Production

```bash
# On your server
cd ~/backend
git pull origin main
docker compose up -d --build

# Verify
docker compose ps
docker compose logs --tail 50 strava-api
curl https://api.yourdomain.com/strava/health
```

### Rollback

```bash
git log --oneline -10  # Find previous commit
git reset --hard <commit-hash>
docker compose up -d --build
```

### Database Backup

```bash
# Backup
docker compose exec db pg_dump -U backend_user backend_db > backup.sql

# Restore
cat backup.sql | docker compose exec -T db psql -U backend_user -d backend_db
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

## Environment Variables

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `ENVIRONMENT` | No | `production` | Runtime environment |
| `POSTGRES_USER` | Yes | `backend_user` | Database username |
| `POSTGRES_PASSWORD` | Yes | `<generated>` | Database password |
| `POSTGRES_DB` | Yes | `backend_db` | Database name |
| `INTERNAL_API_KEY` | Yes* | `<generated>` | API authentication key |
| `STATE_SECRET` | Yes* | `<generated>` | OAuth state signing key |
| `ENCRYPTION_KEY` | Yes* | `<generated>` | Token encryption key |
| `STRAVA_CLIENT_ID` | Yes | `161983` | Strava app client ID |
| `STRAVA_CLIENT_SECRET` | Yes | `<your_secret>` | Strava app secret |
| `STRAVA_REDIRECT_URI` | Yes | `https://api.example.com/strava/callback` | OAuth redirect |
| `FRONTEND_URL` | No | `https://example.com` | Frontend origin for CORS |

\* Required in production (`ENVIRONMENT=production`)

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
