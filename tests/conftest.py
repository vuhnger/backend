"""Shared test setup.

The app modules read a few env vars at import time (notably DATABASE_URL, which
`apps.shared.database` requires to build the engine). Set harmless defaults so
tests can import the apps without a real environment. `setdefault` means CI's
real values (e.g. a live Postgres service) always win.
"""

import os
import secrets

# No password in the default DSN — it's only used for import (create_engine is
# lazy) when DATABASE_URL is unset locally; CI sets a real one. Keeping it
# credential-free avoids committing a `user:password@host` string.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://backend_user@localhost:5432/backend_db",
)
# These just need to be set for the apps to import/boot; the tests don't rely on
# their values. Generate ephemeral ones so no secret-shaped literal is committed.
os.environ.setdefault("ENCRYPTION_KEY", secrets.token_hex(16))
os.environ.setdefault("STATE_SECRET", secrets.token_hex(16))
os.environ.setdefault("INTERNAL_API_KEY", secrets.token_hex(16))
os.environ.setdefault("ENVIRONMENT", "development")
