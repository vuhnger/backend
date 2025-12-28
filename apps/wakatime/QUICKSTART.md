# WakaTime Database Schema - Quick Start

## TL;DR

Database schema is ready. Tables will auto-create when you build the FastAPI app.

---

## Files Created

```
apps/wakatime/
├── __init__.py           # Module marker
├── models.py             # ✅ SQLAlchemy models (MAIN FILE)
├── migrations.sql        # Reference SQL DDL
├── verify.sql            # Verification queries
├── DATABASE.md           # Full documentation
├── README.md             # Implementation summary
└── QUICKSTART.md         # This file
```

---

## Schema at a Glance

### Table 1: wakatime_auth (OAuth tokens)

| Column | Type | Note |
|--------|------|------|
| id | INTEGER PK | Always 1 |
| user_id | VARCHAR(255) | WakaTime UUID |
| access_token | VARCHAR(500) | Longer than Strava |
| refresh_token | VARCHAR(500) | Longer than Strava |
| expires_at | INTEGER | Unix timestamp |
| token_type | VARCHAR(50) | Default 'Bearer' |
| updated_at | TIMESTAMPTZ | Auto-update |

**Indexes**: id (PK), user_id

---

### Table 2: wakatime_stats (cached data)

| Column | Type | Note |
|--------|------|------|
| id | SERIAL PK | Auto-increment |
| stats_type | VARCHAR(50) UNIQUE | today, last_7_days, etc. |
| data | JSONB | Flexible schema |
| fetched_at | TIMESTAMPTZ | Auto-update |

**Indexes**: id (PK), stats_type (UNIQUE)

**Stats Types**: today, last_7_days, last_30_days, all_time, languages, projects

---

## Auto-Create (Default)

Tables auto-create when you add this to your FastAPI app:

```python
# In apps/wakatime/main.py
from apps.shared.database import Base, engine
from apps.wakatime.models import WakaTimeAuth, WakaTimeStats

Base.metadata.create_all(bind=engine)
```

---

## Manual Create (Optional)

```bash
docker compose up -d db
docker exec -i backend-db-1 psql -U backend_user -d backend_db < apps/wakatime/migrations.sql
```

---

## Verify Tables Exist

```bash
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\dt wakatime*"
```

Expected: 2 tables (wakatime_auth, wakatime_stats)

---

## Test Insert

```sql
-- Auth token
INSERT INTO wakatime_auth (id, user_id, access_token, refresh_token, expires_at)
VALUES (1, 'test-uuid', 'access_token', 'refresh_token', 1735084800);

-- Stats cache
INSERT INTO wakatime_stats (stats_type, data)
VALUES ('today', '{"total_seconds": 3600}'::jsonb);

-- Cleanup
DELETE FROM wakatime_auth WHERE id = 1;
DELETE FROM wakatime_stats WHERE stats_type = 'today';
```

---

## Key Differences from Strava

- **ID**: `user_id` (String) vs `athlete_id` (BigInteger)
- **Tokens**: 500 chars vs 255 chars
- **Extra column**: `token_type`
- **Stats**: 6 types vs 3 types

---

## Next Steps

1. ✅ Database schema created (YOU ARE HERE)
2. ⏳ Create apps/wakatime/client.py (API wrapper)
3. ⏳ Create apps/wakatime/tasks.py (background fetch)
4. ⏳ Create apps/wakatime/main.py (FastAPI routes)
5. ⏳ Update docker-compose.yml (add wakatime-api service)

---

## Need More Info?

- **Full docs**: DATABASE.md
- **Implementation plan**: /Users/vuhnger/Developer/backend/WAKATIME-IMPLEMENTATION-PLAN.md
- **Strava reference**: /Users/vuhnger/Developer/backend/apps/strava/models.py

---

## Common Commands

```bash
# Check tables
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\dt wakatime*"

# View auth token
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "SELECT * FROM wakatime_auth;"

# View cached stats
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "SELECT stats_type, fetched_at FROM wakatime_stats;"

# Describe table structure
docker exec -it backend-db-1 psql -U backend_user -d backend_db -c "\d wakatime_stats"

# Run verification queries
docker exec -i backend-db-1 psql -U backend_user -d backend_db < apps/wakatime/verify.sql
```

---

**Status**: ✅ Database schema ready for implementation
