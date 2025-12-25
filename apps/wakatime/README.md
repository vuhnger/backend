# WakaTime Database Schema - Implementation Summary

## What Was Created

### Files Created

1. **apps/wakatime/__init__.py** - Module marker
2. **apps/wakatime/models.py** - SQLAlchemy ORM models (main deliverable)
3. **apps/wakatime/migrations.sql** - Reference SQL DDL for manual creation
4. **apps/wakatime/verify.sql** - Verification queries
5. **apps/wakatime/DATABASE.md** - Comprehensive documentation

### Tables Defined

1. **wakatime_auth** - Single-row OAuth token storage (id=1)
2. **wakatime_stats** - Multi-row cached statistics

---

## How Tables Will Be Created

### Automatic Creation (Recommended)

Tables are created automatically when you add this to your FastAPI app:

```python
# In apps/wakatime/main.py
from apps.shared.database import Base, engine
from apps.wakatime.models import WakaTimeAuth, WakaTimeStats

# Create all tables defined in Base
Base.metadata.create_all(bind=engine)
```

This follows the Strava pattern and is **idempotent** (safe to run multiple times).

### Manual Creation (Alternative)

If you prefer manual control:

```bash
# Start database container
docker compose up -d db

# Wait for DB to be ready
sleep 5

# Run migration script
docker exec -i backend-db-1 psql -U backend_user -d backend_db < apps/wakatime/migrations.sql
```

---

## Verification Steps

### 1. Check Tables Were Created

```bash
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\dt wakatime*"
```

**Expected Output:**
```
           List of relations
 Schema |      Name       | Type  |    Owner
--------+-----------------+-------+--------------
 public | wakatime_auth   | table | backend_user
 public | wakatime_stats  | table | backend_user
```

### 2. Verify Table Structures

```bash
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\d wakatime_auth"
```

**Expected Output:**
```
                                      Table "public.wakatime_auth"
    Column     |           Type           | Collation | Nullable |      Default
---------------+--------------------------+-----------+----------+-------------------
 id            | integer                  |           | not null |
 user_id       | character varying(255)   |           | not null |
 access_token  | character varying(500)   |           | not null |
 refresh_token | character varying(500)   |           | not null |
 expires_at    | integer                  |           | not null |
 token_type    | character varying(50)    |           |          | 'Bearer'::varchar
 updated_at    | timestamp with time zone |           |          | now()
Indexes:
    "wakatime_auth_pkey" PRIMARY KEY, btree (id)
    "idx_wakatime_auth_user_id" btree (user_id)
```

```bash
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\d wakatime_stats"
```

**Expected Output:**
```
                                      Table "public.wakatime_stats"
   Column    |           Type           | Collation | Nullable |                 Default
-------------+--------------------------+-----------+----------+-----------------------------------------
 id          | integer                  |           | not null | nextval('wakatime_stats_id_seq'::regclass)
 stats_type  | character varying(50)    |           | not null |
 data        | jsonb                    |           | not null |
 fetched_at  | timestamp with time zone |           |          | now()
Indexes:
    "wakatime_stats_pkey" PRIMARY KEY, btree (id)
    "wakatime_stats_stats_type_key" UNIQUE CONSTRAINT, btree (stats_type)
    "idx_wakatime_stats_type" btree (stats_type)
```

### 3. Test Data Operations

```bash
# Test inserting auth token
docker exec -i backend-db-1 psql -U backend_user -d backend_db <<EOF
INSERT INTO wakatime_auth (id, user_id, access_token, refresh_token, expires_at, token_type)
VALUES (1, 'test-uuid-123', 'test_access_token', 'test_refresh_token', 1735084800, 'Bearer');

SELECT id, user_id, token_type FROM wakatime_auth;
EOF
```

```bash
# Test inserting stats (upsert pattern)
docker exec -i backend-db-1 psql -U backend_user -d backend_db <<EOF
INSERT INTO wakatime_stats (stats_type, data)
VALUES ('test_type', '{"test": "data"}'::jsonb)
ON CONFLICT (stats_type)
DO UPDATE SET data = EXCLUDED.data;

SELECT stats_type, data FROM wakatime_stats;
EOF
```

**Cleanup test data:**

```bash
docker exec -i backend-db-1 psql -U backend_user -d backend_db <<EOF
DELETE FROM wakatime_auth WHERE id = 1;
DELETE FROM wakatime_stats WHERE stats_type = 'test_type';
EOF
```

---

## PostgreSQL-Specific Features Used

### 1. JSONB Data Type

The `data` column uses PostgreSQL's **JSONB** (binary JSON) for:
- Efficient storage and indexing
- Fast queries on nested fields
- Flexible schema for different stats types

**Example queries:**

```sql
-- Get all languages from 7-day stats
SELECT data->'languages' FROM wakatime_stats WHERE stats_type = 'last_7_days';

-- Filter by language name
SELECT * FROM wakatime_stats WHERE data @> '{"languages": [{"name": "Python"}]}';
```

### 2. Timestamp with Timezone

Uses `TIMESTAMPTZ` for automatic timezone handling:

```sql
-- Always stored in UTC
-- Returned in connection's timezone
SELECT updated_at FROM wakatime_auth;
```

### 3. Unique Constraints

`stats_type` has a UNIQUE constraint for upsert pattern:

```sql
-- This is safe - updates existing row instead of failing
INSERT INTO wakatime_stats (stats_type, data)
VALUES ('today', '{"total_seconds": 3600}'::jsonb)
ON CONFLICT (stats_type)
DO UPDATE SET data = EXCLUDED.data, fetched_at = NOW();
```

### 4. Auto-Update Timestamps

SQLAlchemy's `onupdate=func.now()` triggers timestamp updates on every UPDATE.

---

## Comparison with Strava Schema

| Aspect | Strava | WakaTime | Reason |
|--------|--------|----------|--------|
| **ID Column** | `athlete_id` (BIGINT) | `user_id` (VARCHAR) | WakaTime uses UUID strings |
| **Token Length** | 255 chars | 500 chars | WakaTime tokens can be longer |
| **Extra Column** | None | `token_type` | OAuth 2.0 compliance |
| **Stats Types** | 3 (ytd, activities, monthly) | 6 (today, 7d, 30d, all-time, langs, projects) | Richer data |
| **JSON Type** | JSON | JSONB | Same (PostgreSQL auto-converts) |

---

## Next Steps

### 1. Build WakaTime Service

Follow Phase 1-10 of the implementation plan:

```bash
# Phase 2: Create client.py for WakaTime API calls
# Phase 3: Create tasks.py for background data fetching
# Phase 4: Create main.py with OAuth and API routes
# Phase 7: Add wakatime-api service to docker-compose.yml
```

### 2. Test Database Integration

```bash
# Start containers
docker compose up -d db wakatime-api

# Check tables were created
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\dt wakatime*"

# Check logs
docker logs backend-wakatime-api-1
```

### 3. Complete OAuth Flow

1. Visit `http://localhost:5002/wakatime/authorize`
2. Authorize on WakaTime
3. Check database:
   ```sql
   SELECT * FROM wakatime_auth WHERE id = 1;
   ```

### 4. Verify Data Caching

```bash
# Manually trigger data fetch
docker exec backend-wakatime-api-1 python -m apps.wakatime.tasks

# Check cached stats
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "SELECT stats_type, fetched_at FROM wakatime_stats;"
```

---

## Troubleshooting

### Tables Not Created

**Problem**: Tables don't exist after starting the app.

**Solution**:

1. Check if models are imported in main.py:
   ```python
   from apps.wakatime.models import WakaTimeAuth, WakaTimeStats
   ```

2. Verify Base.metadata.create_all() is called:
   ```python
   Base.metadata.create_all(bind=engine)
   ```

3. Check database connection:
   ```bash
   docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "SELECT version();"
   ```

4. Manually create tables:
   ```bash
   docker exec -i backend-db-1 psql -U backend_user -d backend_db < apps/wakatime/migrations.sql
   ```

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'sqlalchemy'`

**Solution**: This is expected if testing outside Docker. Import works fine inside containers where dependencies are installed.

### JSONB Type Not Working

**Problem**: Data stored as plain text instead of JSONB.

**Solution**: Ensure you're using PostgreSQL 9.4+. Check with:

```sql
SELECT version();
```

Your setup uses PostgreSQL 16, so JSONB is fully supported.

---

## Performance Considerations

### Expected Load

**WakaTime tables are LOW traffic:**

- **wakatime_auth**: 1 row, rarely updated (only on token refresh every ~2 weeks)
- **wakatime_stats**: 6 rows, updated hourly via cron

**Query patterns:**

- Token retrieval: 1-10 times/hour (when API calls happen)
- Stats retrieval: Variable based on frontend traffic (cached responses)

### Index Strategy

**Current indexes are sufficient:**

1. **wakatime_auth**: Primary key on `id` (always id=1, instant lookup)
2. **wakatime_stats**: Unique index on `stats_type` (6 rows total, instant lookup)

**Optional optimization:**

If you query JSON fields frequently:

```sql
CREATE INDEX idx_wakatime_stats_data_gin ON wakatime_stats USING GIN (data);
```

Only add this if you see slow queries in production.

### Storage Estimate

- **wakatime_auth**: <1 KB (1 row)
- **wakatime_stats**: 10-50 KB (6 rows, JSONB compressed)
- **Total**: <100 KB

**Growth**: Negligible. Tables don't grow (fixed row counts in single-user mode).

---

## Security Notes

1. **Token Storage**: Stored in plaintext (industry standard for OAuth)
2. **Database Access**: Password-protected, network isolated
3. **No PII**: Only WakaTime UUID and coding stats stored
4. **Injection Safety**: SQLAlchemy parameterizes all queries

**Future enhancement**: Encrypt tokens at rest using pgcrypto extension.

---

## Backup & Recovery

### Backup WakaTime Data

```bash
# Backup both tables
docker exec backend-db-1 pg_dump -U backend_user backend_db \
  -t wakatime_auth -t wakatime_stats > wakatime_backup.sql

# Backup just auth tokens (for disaster recovery)
docker exec backend-db-1 pg_dump -U backend_user backend_db \
  -t wakatime_auth > wakatime_auth_backup.sql
```

### Restore from Backup

```bash
# Restore all WakaTime data
docker exec -i backend-db-1 psql -U backend_user backend_db < wakatime_backup.sql

# Or restore just auth tokens (if stats cache is stale)
docker exec -i backend-db-1 psql -U backend_user backend_db < wakatime_auth_backup.sql
```

### Recovery Scenarios

**Scenario 1: Lost auth tokens**
- Restore from backup OR
- Re-run OAuth flow (GET /wakatime/authorize)

**Scenario 2: Lost stats cache**
- No backup needed
- Trigger manual refresh: `POST /wakatime/refresh-data`

**Scenario 3: Corrupted database**
- Restore from full database backup
- Re-run OAuth flow if auth tokens are old
- Trigger stats refresh

---

## Monitoring Checklist

After deployment, monitor:

- [ ] Tables exist (`\dt wakatime*`)
- [ ] Auth token exists and is valid (check expires_at)
- [ ] Stats cache is recent (check fetched_at < 2 hours)
- [ ] No table bloat (pg_total_relation_size)
- [ ] Indexes are used (EXPLAIN ANALYZE queries)
- [ ] No slow queries (pg_stat_statements)

---

## Questions & Clarifications

If you encounter issues:

1. **Check logs**: `docker logs backend-wakatime-api-1`
2. **Verify database connection**: Run verify.sql queries
3. **Test manually**: Use psql to insert/query data
4. **Compare with Strava**: Same pattern, should work identically

---

## References

- **Implementation Plan**: /Users/vuhnger/Developer/backend/WAKATIME-IMPLEMENTATION-PLAN.md
- **Database Docs**: /Users/vuhnger/Developer/backend/apps/wakatime/DATABASE.md
- **Strava Reference**: /Users/vuhnger/Developer/backend/apps/strava/models.py
- **SQLAlchemy Docs**: https://docs.sqlalchemy.org/en/20/
- **PostgreSQL JSONB**: https://www.postgresql.org/docs/16/datatype-json.html

---

**Status**: Database schema ready for Phase 2 (API Client) implementation.
