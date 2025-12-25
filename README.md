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

### Data Freshness

- Stats are cached and updated hourly (via cron job)
- Check the `fetched_at` timestamp to see when data was last updated
- OAuth tokens are automatically refreshed before each API call (expires after 6 hours)

### TypeScript Types

```typescript
// API Response Types
interface StravaStats {
  count: number;
  distance: number;        // meters
  moving_time: number;     // seconds
  elevation_gain: number;  // meters
}

interface YTDResponse {
  type: 'ytd';
  data: {
    run: StravaStats;
    ride: StravaStats;
  };
  fetched_at: string;
}

interface Activity {
  id: number;
  name: string;
  type: string;
  distance: number;        // meters
  moving_time: number;     // seconds
  elevation_gain: number;  // meters
  start_date: string;      // ISO 8601
}

interface ActivitiesResponse {
  type: 'recent_activities';
  data: Activity[];
  fetched_at: string;
}

interface MonthlyStats {
  count: number;
  distance: number;
  moving_time: number;
  elevation_gain: number;
}

interface MonthlyResponse {
  type: 'monthly';
  data: Record<string, MonthlyStats>;  // Key format: "YYYY-MM"
  fetched_at: string;
}

interface HealthResponse {
  status: string;
  service: string;
  database: string;
}
```

### Utility Functions

```typescript
// Format distance in meters to kilometers
function formatDistance(meters: number): string {
  return (meters / 1000).toFixed(2);
}

// Format time in seconds to hours
function formatTime(seconds: number): string {
  return (seconds / 3600).toFixed(1);
}

// Format pace (min/km)
function formatPace(meters: number, seconds: number): string {
  const minutesPerKm = (seconds / 60) / (meters / 1000);
  const mins = Math.floor(minutesPerKm);
  const secs = Math.round((minutesPerKm - mins) * 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Format elevation gain
function formatElevation(meters: number): string {
  return Math.round(meters).toString();
}

// Format date for display
function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}

// Calculate time since last update
function getTimeSinceUpdate(fetchedAt: string): string {
  const now = new Date();
  const fetched = new Date(fetchedAt);
  const diffMs = now.getTime() - fetched.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 60) return `${diffMins} minutes ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours} hours ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} days ago`;
}
```

### API Client (Vanilla JavaScript/TypeScript)

```typescript
class StravaAPIClient {
  private baseURL: string;

  constructor(baseURL = 'https://api.vuhnger.dev') {
    this.baseURL = baseURL;
  }

  private async request<T>(endpoint: string): Promise<T> {
    try {
      const response = await fetch(`${this.baseURL}${endpoint}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'omit', // No cookies needed
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('Network error: Unable to connect to API');
      }
      throw error;
    }
  }

  async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>('/strava/health');
  }

  async getYTDStats(): Promise<YTDResponse> {
    return this.request<YTDResponse>('/strava/stats/ytd');
  }

  async getRecentActivities(): Promise<ActivitiesResponse> {
    return this.request<ActivitiesResponse>('/strava/stats/activities');
  }

  async getMonthlyStats(): Promise<MonthlyResponse> {
    return this.request<MonthlyResponse>('/strava/stats/monthly');
  }

  async refreshData(apiKey: string): Promise<{ status: string; message: string }> {
    const response = await fetch(`${this.baseURL}/strava/refresh-data`, {
      method: 'POST',
      headers: {
        'X-API-Key': apiKey,
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }
}

// Usage
const client = new StravaAPIClient();
```

### React Example: YTD Stats Component

```typescript
import { useState, useEffect } from 'react';

interface YTDStatsProps {
  apiURL?: string;
}

export function YTDStats({ apiURL = 'https://api.vuhnger.dev' }: YTDStatsProps) {
  const [stats, setStats] = useState<YTDResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchStats() {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch(`${apiURL}/strava/stats/ytd`);

        if (!response.ok) {
          throw new Error(`Failed to fetch: ${response.status}`);
        }

        const data = await response.json();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    }

    fetchStats();
  }, [apiURL]);

  if (loading) {
    return (
      <div className="stats-loading" role="status" aria-live="polite">
        <p>Loading statistics...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="stats-error" role="alert" aria-live="assertive">
        <p>Error loading stats: {error}</p>
        <button onClick={() => window.location.reload()}>Retry</button>
      </div>
    );
  }

  if (!stats) {
    return <div>No data available</div>;
  }

  const { run, ride } = stats.data;
  const lastUpdate = getTimeSinceUpdate(stats.fetched_at);

  return (
    <div className="ytd-stats">
      <header>
        <h2>Year-to-Date Statistics</h2>
        <p className="last-update">Updated {lastUpdate}</p>
      </header>

      <section className="activity-type" aria-labelledby="run-heading">
        <h3 id="run-heading">Running</h3>
        <dl className="stats-grid">
          <div>
            <dt>Activities</dt>
            <dd>{run.count}</dd>
          </div>
          <div>
            <dt>Distance</dt>
            <dd>{formatDistance(run.distance)} km</dd>
          </div>
          <div>
            <dt>Time</dt>
            <dd>{formatTime(run.moving_time)} hours</dd>
          </div>
          <div>
            <dt>Elevation</dt>
            <dd>{formatElevation(run.elevation_gain)} m</dd>
          </div>
          <div>
            <dt>Avg Pace</dt>
            <dd>{formatPace(run.distance, run.moving_time)} /km</dd>
          </div>
        </dl>
      </section>

      <section className="activity-type" aria-labelledby="ride-heading">
        <h3 id="ride-heading">Cycling</h3>
        <dl className="stats-grid">
          <div>
            <dt>Activities</dt>
            <dd>{ride.count}</dd>
          </div>
          <div>
            <dt>Distance</dt>
            <dd>{formatDistance(ride.distance)} km</dd>
          </div>
          <div>
            <dt>Time</dt>
            <dd>{formatTime(ride.moving_time)} hours</dd>
          </div>
          <div>
            <dt>Elevation</dt>
            <dd>{formatElevation(ride.elevation_gain)} m</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
```

### React Example: Recent Activities List

```typescript
import { useState, useEffect } from 'react';

export function RecentActivities() {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchActivities() {
      try {
        setLoading(true);
        const response = await fetch('https://api.vuhnger.dev/strava/stats/activities');

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const data: ActivitiesResponse = await response.json();
        setActivities(data.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        setLoading(false);
      }
    }

    fetchActivities();
  }, []);

  if (loading) {
    return <div role="status">Loading activities...</div>;
  }

  if (error) {
    return <div role="alert">Error: {error}</div>;
  }

  return (
    <div className="activities-list">
      <h2>Recent Activities</h2>
      <ul>
        {activities.map(activity => (
          <li key={activity.id} className="activity-card">
            <div className="activity-header">
              <h3>{activity.name}</h3>
              <span className="activity-type">{activity.type}</span>
            </div>
            <div className="activity-stats">
              <span>{formatDistance(activity.distance)} km</span>
              <span>{formatTime(activity.moving_time)} hrs</span>
              <span>{formatPace(activity.distance, activity.moving_time)} /km</span>
              <span>{formatElevation(activity.elevation_gain)} m</span>
            </div>
            <time dateTime={activity.start_date}>
              {formatDate(activity.start_date)}
            </time>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### Vue 3 Example: Monthly Stats

```vue
<template>
  <div class="monthly-stats">
    <h2>Monthly Statistics</h2>

    <div v-if="loading" role="status">
      Loading monthly data...
    </div>

    <div v-else-if="error" role="alert" class="error">
      {{ error }}
    </div>

    <div v-else-if="monthlyData" class="chart-container">
      <div
        v-for="(stats, month) in monthlyData"
        :key="month"
        class="month-bar"
      >
        <div class="month-label">{{ formatMonth(month) }}</div>
        <div class="bar-wrapper">
          <div
            class="bar"
            :style="{ width: getBarWidth(stats.distance) }"
            :aria-label="`${formatMonth(month)}: ${formatDistance(stats.distance)} km`"
          >
            {{ formatDistance(stats.distance) }} km
          </div>
        </div>
        <div class="month-details">
          <span>{{ stats.count }} activities</span>
          <span>{{ formatTime(stats.moving_time) }} hrs</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const loading = ref(true);
const error = ref<string | null>(null);
const monthlyData = ref<Record<string, MonthlyStats> | null>(null);
const maxDistance = ref(0);

async function fetchMonthlyStats() {
  try {
    loading.value = true;
    error.value = null;

    const response = await fetch('https://api.vuhnger.dev/strava/stats/monthly');

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data: MonthlyResponse = await response.json();
    monthlyData.value = data.data;

    // Calculate max distance for bar chart scaling
    maxDistance.value = Math.max(
      ...Object.values(data.data).map(s => s.distance)
    );
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load';
  } finally {
    loading.value = false;
  }
}

function formatMonth(yearMonth: string): string {
  const [year, month] = yearMonth.split('-');
  const date = new Date(Number(year), Number(month) - 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function getBarWidth(distance: number): string {
  const percentage = (distance / maxDistance.value) * 100;
  return `${Math.max(percentage, 5)}%`; // Minimum 5% width
}

onMounted(() => {
  fetchMonthlyStats();
});
</script>

<style scoped>
.month-bar {
  margin-bottom: 1rem;
}

.bar {
  background: linear-gradient(90deg, #fc4c02, #fc7302);
  padding: 0.5rem;
  color: white;
  font-weight: 600;
  transition: width 0.3s ease;
}

.month-details {
  display: flex;
  gap: 1rem;
  font-size: 0.875rem;
  color: #666;
  margin-top: 0.25rem;
}
</style>
```

### Custom Hook (React)

```typescript
import { useState, useEffect } from 'react';

interface UseStravaStatsOptions {
  endpoint: 'ytd' | 'activities' | 'monthly';
  apiURL?: string;
  refreshInterval?: number; // milliseconds
}

interface UseStravaStatsResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  lastUpdate: string | null;
}

export function useStravaStats<T>({
  endpoint,
  apiURL = 'https://api.vuhnger.dev',
  refreshInterval
}: UseStravaStatsOptions): UseStravaStatsResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${apiURL}/strava/stats/${endpoint}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      setData(result.data);
      setLastUpdate(result.fetched_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (refreshInterval) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [endpoint, apiURL, refreshInterval]);

  return {
    data,
    loading,
    error,
    refetch: fetchData,
    lastUpdate
  };
}

// Usage example
function MyComponent() {
  const { data, loading, error, refetch, lastUpdate } = useStravaStats<YTDResponse['data']>({
    endpoint: 'ytd',
    refreshInterval: 60000 // Refresh every minute
  });

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!data) return <div>No data</div>;

  return (
    <div>
      <button onClick={refetch}>Refresh</button>
      <p>Last updated: {lastUpdate ? getTimeSinceUpdate(lastUpdate) : 'Unknown'}</p>
      <div>Runs: {data.run.count}</div>
    </div>
  );
}
```

### Error Handling Best Practices

```typescript
class StravaAPIError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public endpoint?: string
  ) {
    super(message);
    this.name = 'StravaAPIError';
  }
}

async function fetchWithErrorHandling<T>(
  url: string,
  options?: RequestInit
): Promise<T> {
  try {
    const response = await fetch(url, options);

    // Handle HTTP errors
    if (!response.ok) {
      if (response.status === 404) {
        throw new StravaAPIError(
          'No data available. Complete OAuth flow first.',
          404,
          url
        );
      }

      if (response.status === 500) {
        throw new StravaAPIError(
          'Server error. Please try again later.',
          500,
          url
        );
      }

      throw new StravaAPIError(
        `Request failed: ${response.statusText}`,
        response.status,
        url
      );
    }

    return await response.json();
  } catch (error) {
    // Network errors
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new StravaAPIError(
        'Network error. Check your internet connection.',
        undefined,
        url
      );
    }

    // Re-throw StravaAPIError
    if (error instanceof StravaAPIError) {
      throw error;
    }

    // Unknown errors
    throw new StravaAPIError(
      error instanceof Error ? error.message : 'Unknown error',
      undefined,
      url
    );
  }
}

// Usage with user-friendly error messages
async function displayStats() {
  try {
    const data = await fetchWithErrorHandling<YTDResponse>(
      'https://api.vuhnger.dev/strava/stats/ytd'
    );
    console.log(data);
  } catch (error) {
    if (error instanceof StravaAPIError) {
      // Display user-friendly error
      alert(error.message);

      // Log technical details for debugging
      console.error('API Error:', {
        message: error.message,
        statusCode: error.statusCode,
        endpoint: error.endpoint
      });
    }
  }
}
```

### Loading States Example

```typescript
import { useState } from 'react';

type LoadingState = 'idle' | 'loading' | 'success' | 'error';

export function StatsWithStates() {
  const [state, setState] = useState<LoadingState>('idle');
  const [data, setData] = useState<YTDResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  async function loadStats() {
    setState('loading');

    try {
      const response = await fetch('https://api.vuhnger.dev/strava/stats/ytd');

      if (!response.ok) {
        throw new Error('Failed to load');
      }

      const result = await response.json();
      setData(result);
      setState('success');
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : 'Unknown error');
      setState('error');
    }
  }

  return (
    <div>
      {state === 'idle' && (
        <button onClick={loadStats}>Load Stats</button>
      )}

      {state === 'loading' && (
        <div className="spinner" role="status" aria-live="polite">
          <span className="sr-only">Loading statistics...</span>
        </div>
      )}

      {state === 'error' && (
        <div role="alert" className="error-message">
          <p>{errorMsg}</p>
          <button onClick={loadStats}>Try Again</button>
        </div>
      )}

      {state === 'success' && data && (
        <div className="stats-content">
          {/* Display stats */}
        </div>
      )}
    </div>
  );
}
```

### Complete Production Example

```typescript
// strava-dashboard.tsx
import { useState, useEffect } from 'react';

interface DashboardProps {
  apiURL?: string;
}

export function StravaDashboard({ apiURL = 'https://api.vuhnger.dev' }: DashboardProps) {
  const [ytdStats, setYtdStats] = useState<YTDResponse | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [monthly, setMonthly] = useState<Record<string, MonthlyStats> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  async function fetchAllData() {
    try {
      setLoading(true);
      setError(null);

      // Fetch all endpoints in parallel
      const [ytdRes, activitiesRes, monthlyRes] = await Promise.all([
        fetch(`${apiURL}/strava/stats/ytd`),
        fetch(`${apiURL}/strava/stats/activities`),
        fetch(`${apiURL}/strava/stats/monthly`)
      ]);

      // Check all responses
      if (!ytdRes.ok || !activitiesRes.ok || !monthlyRes.ok) {
        throw new Error('One or more requests failed');
      }

      // Parse all responses
      const [ytdData, activitiesData, monthlyData] = await Promise.all([
        ytdRes.json(),
        activitiesRes.json(),
        monthlyRes.json()
      ]);

      setYtdStats(ytdData);
      setActivities(activitiesData.data);
      setMonthly(monthlyData.data);
      setLastFetch(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAllData();

    // Refresh every 5 minutes
    const interval = setInterval(fetchAllData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [apiURL]);

  if (loading && !ytdStats) {
    return (
      <div className="dashboard-loading" role="status">
        <div className="spinner" aria-hidden="true"></div>
        <p>Loading your Strava data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-error" role="alert">
        <h2>Unable to load stats</h2>
        <p>{error}</p>
        <button onClick={fetchAllData}>Retry</button>
      </div>
    );
  }

  return (
    <div className="strava-dashboard">
      <header className="dashboard-header">
        <h1>Strava Statistics</h1>
        {lastFetch && (
          <p className="last-update">
            Last updated: {getTimeSinceUpdate(lastFetch.toISOString())}
          </p>
        )}
        <button
          onClick={fetchAllData}
          disabled={loading}
          aria-label="Refresh statistics"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </header>

      {ytdStats && (
        <section className="ytd-section" aria-labelledby="ytd-heading">
          <h2 id="ytd-heading">Year to Date</h2>
          <div className="stats-grid">
            <div className="stat-card">
              <h3>Running</h3>
              <dl>
                <div><dt>Activities</dt><dd>{ytdStats.data.run.count}</dd></div>
                <div><dt>Distance</dt><dd>{formatDistance(ytdStats.data.run.distance)} km</dd></div>
                <div><dt>Time</dt><dd>{formatTime(ytdStats.data.run.moving_time)} hrs</dd></div>
                <div><dt>Elevation</dt><dd>{formatElevation(ytdStats.data.run.elevation_gain)} m</dd></div>
              </dl>
            </div>

            <div className="stat-card">
              <h3>Cycling</h3>
              <dl>
                <div><dt>Activities</dt><dd>{ytdStats.data.ride.count}</dd></div>
                <div><dt>Distance</dt><dd>{formatDistance(ytdStats.data.ride.distance)} km</dd></div>
                <div><dt>Time</dt><dd>{formatTime(ytdStats.data.ride.moving_time)} hrs</dd></div>
                <div><dt>Elevation</dt><dd>{formatElevation(ytdStats.data.ride.elevation_gain)} m</dd></div>
              </dl>
            </div>
          </div>
        </section>
      )}

      {activities.length > 0 && (
        <section className="activities-section" aria-labelledby="activities-heading">
          <h2 id="activities-heading">Recent Activities</h2>
          <ul className="activities-list">
            {activities.slice(0, 10).map(activity => (
              <li key={activity.id} className="activity-item">
                <div className="activity-info">
                  <strong>{activity.name}</strong>
                  <span className="activity-type">{activity.type}</span>
                </div>
                <div className="activity-metrics">
                  <span>{formatDistance(activity.distance)} km</span>
                  <span>{formatPace(activity.distance, activity.moving_time)} /km</span>
                  <time dateTime={activity.start_date}>
                    {formatDate(activity.start_date)}
                  </time>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
```

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
