# WakaTime Database Schema Documentation

## Overview

The WakaTime integration uses two PostgreSQL tables following the proven Strava pattern:

1. **wakatime_auth** - Single-row OAuth token storage (id=1)
2. **wakatime_stats** - Multi-row cached statistics

Both tables share the same database as Strava (`backend_db`) and use PostgreSQL 16 features.

---

## Table Definitions

### Table 1: wakatime_auth

**Purpose**: Store OAuth 2.0 tokens for WakaTime API access in single-user mode.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Always 1 (single-user mode) |
| user_id | VARCHAR(255) | NOT NULL, INDEXED | WakaTime user ID (UUID string) |
| access_token | VARCHAR(500) | NOT NULL | OAuth access token (longer than Strava) |
| refresh_token | VARCHAR(500) | NOT NULL | OAuth refresh token |
| expires_at | INTEGER | NOT NULL | Unix timestamp for token expiry |
| token_type | VARCHAR(50) | DEFAULT 'Bearer' | OAuth token type |
| updated_at | TIMESTAMPTZ | AUTO-UPDATE | Last modification timestamp |

**Indexes:**
- PRIMARY KEY on `id`
- INDEX on `user_id` (idx_wakatime_auth_user_id)

**Constraints:**
- Optional CHECK constraint: `id = 1` (ensures single-row)

**Storage Estimate**: ~1 row, <1 KB

---

### Table 2: wakatime_stats

**Purpose**: Cache WakaTime statistics to minimize API calls and avoid rate limits.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | SERIAL | PRIMARY KEY | Auto-increment ID |
| stats_type | VARCHAR(50) | NOT NULL, UNIQUE, INDEXED | Type of cached stats |
| data | JSONB | NOT NULL | Cached statistics data |
| fetched_at | TIMESTAMPTZ | AUTO-UPDATE | Cache timestamp |

**Indexes:**
- PRIMARY KEY on `id`
- UNIQUE INDEX on `stats_type` (idx_wakatime_stats_type)
- Optional: GIN index on `data` for JSONB queries

**Valid stats_type Values:**
- `today` - Today's coding time
- `last_7_days` - 7-day summary with languages/projects
- `last_30_days` - 30-day summary
- `all_time` - All-time totals
- `languages` - Language breakdown
- `projects` - Project breakdown

**Storage Estimate**: ~6 rows, 10-50 KB (depends on JSONB size)

---

## Key Differences from Strava

| Aspect | Strava | WakaTime | Reason |
|--------|--------|----------|--------|
| ID Column | `athlete_id` (BIGINT) | `user_id` (VARCHAR) | WakaTime uses UUID strings |
| Token Length | 255 chars | 500 chars | WakaTime tokens can be longer |
| Additional Column | None | `token_type` | OAuth compliance |
| Stats Types | 3 types | 6 types | WakaTime has richer data |

---

## PostgreSQL-Specific Considerations

### 1. JSONB vs JSON

SQLAlchemy's `JSON` type automatically maps to PostgreSQL's **JSONB** (binary JSON) which provides:

- **Faster queries**: Indexed access to nested fields
- **Compression**: Efficient storage
- **GIN indexing**: Full-text search on JSON content

**When to add GIN index:**

```sql
CREATE INDEX idx_wakatime_stats_data_gin ON wakatime_stats USING GIN (data);
```

Add this if you frequently query specific JSON paths like:

```sql
SELECT data->'languages' FROM wakatime_stats WHERE stats_type = 'last_7_days';
```

### 2. Timestamp Auto-Updates

PostgreSQL doesn't natively support `ON UPDATE CURRENT_TIMESTAMP` like MySQL. We use two approaches:

**SQLAlchemy Level (Recommended):**
```python
updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

**Database Level (Triggers):**
```sql
CREATE TRIGGER trigger_wakatime_stats_update
    BEFORE UPDATE ON wakatime_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_wakatime_stats_timestamp();
```

The trigger approach is included in `migrations.sql` for manual deployments.

### 3. SERIAL vs IDENTITY

PostgreSQL 10+ recommends `GENERATED ALWAYS AS IDENTITY` over `SERIAL`:

**Current (SQLAlchemy):**
```python
id = Column(Integer, primary_key=True, autoincrement=True)  # Uses SERIAL
```

**Modern PostgreSQL:**
```sql
id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY
```

For new schemas, consider using Identity columns. For this project, SERIAL is fine since we're following the Strava pattern.

### 4. Constraint Enforcement

**Single-Row Constraint (wakatime_auth):**

```sql
ALTER TABLE wakatime_auth
    ADD CONSTRAINT chk_wakatime_auth_single_row
    CHECK (id = 1);
```

This prevents accidental insertion of multiple auth rows. **Trade-off**: Application logic already enforces id=1, so this is optional.

**Stats Type Validation:**

```sql
ALTER TABLE wakatime_stats
    ADD CONSTRAINT chk_wakatime_stats_type_valid
    CHECK (stats_type IN ('today', 'last_7_days', 'last_30_days', 'all_time', 'languages', 'projects'));
```

This ensures only valid stats types are stored. **Trade-off**: Requires schema change to add new stats types.

**Recommendation**: Skip these constraints initially. Add later if data quality issues arise.

### 5. Connection Pooling

The database.py uses `NullPool` for containerized environments:

```python
engine = create_engine(DATABASE_URL, poolclass=NullPool, echo=False)
```

**Considerations:**
- No connection pooling = new connection per request
- Good for: Low-traffic APIs, containerized apps
- Bad for: High-traffic scenarios (100+ req/sec)

**Alternative for production:**
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,          # Concurrent connections
    max_overflow=10,      # Extra connections when pool full
    pool_pre_ping=True    # Verify connection before use
)
```

### 6. Transaction Isolation

PostgreSQL defaults to **READ COMMITTED** isolation. For WakaTime:

**Auth Token Updates:**
- Single row (id=1)
- Low concurrency
- Default isolation is sufficient

**Stats Upserts:**
- Multiple concurrent cron jobs could conflict
- Use explicit locking for safety:

```python
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

# Safe upsert pattern
stmt = insert(WakaTimeStats).values(stats_type=stats_type, data=data)
stmt = stmt.on_conflict_do_update(
    index_elements=['stats_type'],
    set_={'data': data, 'fetched_at': func.now()}
)
db.execute(stmt)
db.commit()
```

This uses PostgreSQL's `ON CONFLICT` (UPSERT) for atomic operations.

---

## Table Creation Methods

### Method 1: SQLAlchemy Auto-Creation (Recommended)

Tables are created automatically when the FastAPI app starts:

```python
# In apps/wakatime/main.py
from apps.shared.database import Base, engine
from apps.wakatime.models import WakaTimeAuth, WakaTimeStats

Base.metadata.create_all(bind=engine)
```

**Pros:**
- Automatic on app startup
- Consistent with Strava pattern
- Idempotent (safe to run multiple times)

**Cons:**
- No migration tracking
- No rollback capability

### Method 2: Manual SQL Execution

```bash
# Connect to database container
docker exec -it backend-db-1 psql -U backend_user -d backend_db

# Run migration script
\i /path/to/migrations.sql

# Or copy-paste DDL statements
```

**Pros:**
- Full control over schema
- Can add custom constraints/triggers
- Can version control migrations

**Cons:**
- Manual process
- Requires database access

### Method 3: Alembic Migrations (Future)

For production systems, consider Alembic:

```bash
# Initialize Alembic
alembic init alembic

# Generate migration
alembic revision --autogenerate -m "Add WakaTime tables"

# Apply migration
alembic upgrade head
```

**Pros:**
- Version-controlled schema changes
- Rollback support
- Team-friendly

**Cons:**
- Additional setup complexity
- Overkill for single-user apps

---

## Verification Steps

### 1. After Table Creation

Run verification queries from `verify.sql`:

```bash
docker exec -it backend-db-1 psql -U backend_user -d backend_db -f apps/wakatime/verify.sql
```

**Expected Output:**
- 2 tables: wakatime_auth, wakatime_stats
- 2 indexes per table (primary + custom)
- No errors on structure queries

### 2. After OAuth Flow

Check that auth token is stored:

```sql
SELECT
    id,
    user_id,
    token_type,
    TO_TIMESTAMP(expires_at) AS expires_at,
    updated_at
FROM wakatime_auth
WHERE id = 1;
```

**Expected:**
- Exactly 1 row
- Valid user_id (UUID format)
- expires_at ~2 weeks in future

### 3. After Data Caching

Check that stats are cached:

```sql
SELECT
    stats_type,
    jsonb_typeof(data) AS data_type,
    fetched_at,
    AGE(NOW(), fetched_at) AS data_age
FROM wakatime_stats
ORDER BY stats_type;
```

**Expected:**
- 6 rows (one per stats_type)
- data_type = 'object'
- data_age < 1 hour (if cron is running)

### 4. Performance Check

Test query performance:

```sql
EXPLAIN ANALYZE
SELECT * FROM wakatime_stats WHERE stats_type = 'last_7_days';
```

**Expected:**
- Index Scan on idx_wakatime_stats_type
- Execution time < 1ms (minimal data)

---

## Common Operations

### Upsert Stats (Python)

**SAFE ATOMIC PATTERN** (recommended):

```python
from apps.wakatime.models import WakaTimeStats
from apps.shared.upsert import atomic_upsert_stats
from sqlalchemy.orm import Session

def upsert_stats(db: Session, stats_type: str, data: dict):
    """
    Atomic insert or update using PostgreSQL ON CONFLICT.

    This is race-condition-free and prevents duplicate key violations
    when multiple cron jobs run concurrently.

    Performance: ~2-3x throughput vs check-then-insert pattern.
    """
    atomic_upsert_stats(
        db=db,
        model=WakaTimeStats,
        unique_field='stats_type',
        unique_value=stats_type,
        update_data={'data': data}
    )
    db.commit()
```

**UNSAFE PATTERN** (DO NOT USE - has race condition):

```python
# ❌ DANGEROUS: Non-atomic check-then-insert pattern
def upsert_stats_UNSAFE(db: Session, stats_type: str, data: dict):
    """
    WARNING: This pattern has a race condition!

    Problem:
    - Process A: SELECT -> no result found
    - Process B: SELECT -> no result found
    - Process A: INSERT -> success
    - Process B: INSERT -> DUPLICATE KEY ERROR!

    When multiple cron jobs execute simultaneously, both may check for
    a missing record and try to insert, causing one to fail with a
    duplicate key violation.

    DO NOT USE THIS PATTERN!
    """
    existing = db.query(WakaTimeStats).filter(
        WakaTimeStats.stats_type == stats_type
    ).first()

    if existing:
        existing.data = data
    else:
        stats = WakaTimeStats(stats_type=stats_type, data=data)
        db.add(stats)

    db.commit()
```

### Token Refresh (Python)

```python
from apps.wakatime.models import WakaTimeAuth
import time

def update_tokens(db: Session, access_token: str, refresh_token: str, expires_in: int):
    """Update OAuth tokens after refresh"""
    auth = db.query(WakaTimeAuth).filter(WakaTimeAuth.id == 1).first()

    if auth:
        auth.access_token = access_token
        auth.refresh_token = refresh_token
        auth.expires_at = int(time.time()) + expires_in
        db.commit()
    else:
        raise Exception("No auth record found - run OAuth flow first")
```

### Check Token Expiry (SQL)

```sql
SELECT
    CASE
        WHEN expires_at < EXTRACT(EPOCH FROM NOW()) THEN 'EXPIRED'
        WHEN expires_at < EXTRACT(EPOCH FROM NOW() + INTERVAL '24 hours') THEN 'NEEDS_REFRESH'
        ELSE 'VALID'
    END AS token_status,
    TO_TIMESTAMP(expires_at) - NOW() AS time_remaining
FROM wakatime_auth
WHERE id = 1;
```

### Clear Cache (SQL)

```sql
-- Delete all cached stats
DELETE FROM wakatime_stats;

-- Delete specific stats type
DELETE FROM wakatime_stats WHERE stats_type = 'last_7_days';
```

### Force Re-Auth (SQL)

```sql
-- Delete auth tokens (requires new OAuth flow)
DELETE FROM wakatime_auth WHERE id = 1;
```

---

## Monitoring and Maintenance

### 1. Table Bloat

PostgreSQL uses MVCC (Multi-Version Concurrency Control) which can cause table bloat with frequent updates.

**Check bloat:**

```sql
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
    n_tup_upd AS update_count,
    n_tup_del AS delete_count
FROM pg_stat_user_tables
WHERE tablename IN ('wakatime_auth', 'wakatime_stats');
```

**If bloat is high (total_size > expected):**

```sql
VACUUM FULL wakatime_stats;
VACUUM FULL wakatime_auth;
```

Or enable autovacuum (usually enabled by default):

```sql
ALTER TABLE wakatime_stats SET (autovacuum_vacuum_scale_factor = 0.1);
ALTER TABLE wakatime_auth SET (autovacuum_vacuum_scale_factor = 0.1);
```

### 2. Index Maintenance

Check index usage:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan AS index_scans,
    idx_tup_read AS tuples_read
FROM pg_stat_user_indexes
WHERE tablename IN ('wakatime_auth', 'wakatime_stats')
ORDER BY idx_scan DESC;
```

**If idx_scan = 0**: Index is unused, consider dropping.

### 3. Query Performance

Track slow queries with pg_stat_statements:

```sql
-- Enable extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Check slow queries on WakaTime tables
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    stddev_exec_time
FROM pg_stat_statements
WHERE query LIKE '%wakatime%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### 4. Backup Strategy

**Logical Backup (recommended for small DBs):**

```bash
# Backup entire database
docker exec backend-db-1 pg_dump -U backend_user backend_db > backup.sql

# Backup only WakaTime tables
docker exec backend-db-1 pg_dump -U backend_user backend_db -t wakatime_auth -t wakatime_stats > wakatime_backup.sql

# Restore
docker exec -i backend-db-1 psql -U backend_user backend_db < backup.sql
```

**Physical Backup (recommended for large DBs):**

```bash
# Using pg_basebackup
docker exec backend-db-1 pg_basebackup -D /backup -F tar -z -P -U backend_user
```

**Backup Schedule:**
- Daily: Full database backup
- Hourly: Archive WAL logs (for point-in-time recovery)

---

## Troubleshooting

### Issue: Tables not created

**Symptoms:**
- 404 errors on stats endpoints
- "relation does not exist" errors

**Diagnosis:**

```sql
SELECT tablename FROM pg_tables WHERE tablename LIKE 'wakatime%';
```

**Fix:**

```bash
# Restart WakaTime API to trigger Base.metadata.create_all()
docker compose restart wakatime-api

# Or manually create
docker exec -i backend-db-1 psql -U backend_user backend_db < apps/wakatime/migrations.sql
```

---

### Issue: JSONB query slow

**Symptoms:**
- Stats endpoints slow (>100ms)
- Sequential scan in EXPLAIN

**Diagnosis:**

```sql
EXPLAIN ANALYZE
SELECT data->'languages' FROM wakatime_stats WHERE stats_type = 'last_7_days';
```

**Fix:**

```sql
-- Add GIN index for JSONB queries
CREATE INDEX idx_wakatime_stats_data_gin ON wakatime_stats USING GIN (data);

-- Rerun EXPLAIN to verify index usage
```

---

### Issue: Token auto-update not working

**Symptoms:**
- updated_at/fetched_at not changing on UPDATE

**Diagnosis:**

```sql
-- Check if triggers exist
SELECT trigger_name FROM information_schema.triggers
WHERE event_object_table = 'wakatime_auth';
```

**Fix:**

SQLAlchemy's `onupdate=func.now()` should handle this. If not:

```sql
-- Manually create trigger (see migrations.sql)
CREATE OR REPLACE FUNCTION update_wakatime_auth_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_wakatime_auth_update
    BEFORE UPDATE ON wakatime_auth
    FOR EACH ROW
    EXECUTE FUNCTION update_wakatime_auth_timestamp();
```

---

### Issue: Unique constraint violation on stats_type

**Symptoms:**
- "duplicate key value violates unique constraint"
- Occurs when multiple cron jobs run simultaneously

**Root Cause:**
- Non-atomic check-then-insert pattern creates race condition window
- Two processes both query for missing record, then both try to insert
- PostgreSQL rejects the second insert with duplicate key error

**Fix:**

Replace unsafe check-then-insert with atomic upsert:

```python
# ❌ BAD (race condition - can cause conflicts)
existing = db.query(WakaTimeStats).filter(
    WakaTimeStats.stats_type == stats_type
).first()

if existing:
    existing.data = data
else:
    stats = WakaTimeStats(stats_type=stats_type, data=data)
    db.add(stats)

db.commit()

# ✓ GOOD (atomic upsert - race-free)
from apps.shared.upsert import atomic_upsert_stats

atomic_upsert_stats(
    db=db,
    model=WakaTimeStats,
    unique_field='stats_type',
    unique_value=stats_type,
    update_data={'data': data}
)
db.commit()

# ✓ ALSO GOOD (direct PostgreSQL ON CONFLICT)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func

stmt = pg_insert(WakaTimeStats).values(stats_type='today', data=data)
stmt = stmt.on_conflict_do_update(
    index_elements=['stats_type'],
    set_={'data': stmt.excluded.data, 'fetched_at': func.now()}
)
db.execute(stmt)
db.commit()
```

**Prevention:**
- Use atomic upsert pattern for all operations on tables with unique constraints
- Never use check-then-insert pattern in concurrent environments
- See `benchmark_upsert.py` for performance comparison

---

## Security Considerations

1. **Token Storage**
   - Access tokens stored in plaintext (industry standard)
   - Database uses password authentication
   - Network isolated via Docker network
   - Consider: Encrypt tokens at rest using pgcrypto extension

2. **User ID Privacy**
   - user_id is WakaTime's UUID, not sensitive
   - No PII stored in database

3. **JSONB Injection**
   - Always use parameterized queries
   - SQLAlchemy handles this automatically
   - Never concatenate user input into SQL

4. **Least Privilege**
   - backend_user has full access to backend_db
   - Consider: Create read-only role for reporting queries

---

## Performance Tuning

### Expected Query Patterns

1. **Token retrieval** (high frequency)
   ```sql
   SELECT * FROM wakatime_auth WHERE id = 1;
   ```
   - Primary key lookup = O(1)
   - No tuning needed

2. **Stats retrieval by type** (high frequency)
   ```sql
   SELECT * FROM wakatime_stats WHERE stats_type = 'last_7_days';
   ```
   - Unique index = O(1)
   - No tuning needed

3. **JSONB path queries** (medium frequency)
   ```sql
   SELECT data->'languages' FROM wakatime_stats WHERE stats_type = 'last_7_days';
   ```
   - Add GIN index if slow (see above)

### Database Configuration Tuning

For low-traffic APIs, default PostgreSQL settings are fine. For higher traffic:

```sql
-- Increase shared buffers (PostgreSQL caches data in memory)
ALTER SYSTEM SET shared_buffers = '256MB';

-- Increase work_mem for complex queries
ALTER SYSTEM SET work_mem = '4MB';

-- Enable query planning stats
ALTER SYSTEM SET track_activities = on;
ALTER SYSTEM SET track_counts = on;

-- Reload configuration
SELECT pg_reload_conf();
```

---

## Migration Checklist

When deploying to production:

- [ ] Review schema definitions match requirements
- [ ] Verify no conflicts with existing tables
- [ ] Run `verify.sql` queries after creation
- [ ] Test OAuth flow stores tokens correctly
- [ ] Test cron job caches stats correctly
- [ ] Verify indexes are used (EXPLAIN ANALYZE)
- [ ] Set up backup schedule
- [ ] Monitor table sizes and bloat
- [ ] Document rollback procedure
- [ ] Test token refresh mechanism

---

## Future Enhancements

1. **Partitioning**: If stats history grows, partition by date
2. **Archiving**: Move old stats to separate archive table
3. **Replication**: Set up streaming replication for HA
4. **Monitoring**: Integrate with pg_stat_monitor or pgBadger
5. **Encryption**: Use pgcrypto for token encryption at rest
6. **Audit Logging**: Track who/when modified auth tokens

---

## References

- PostgreSQL 16 Documentation: https://www.postgresql.org/docs/16/
- JSONB Performance: https://www.postgresql.org/docs/16/datatype-json.html
- SQLAlchemy ORM: https://docs.sqlalchemy.org/en/20/
- WakaTime API: https://wakatime.com/developers
