#!/usr/bin/env bash
#
# Weekly restore verification.
#
# Restores the newest dump into a throwaway PostgreSQL container and checks that
# the schema actually arrives, then destroys it. `pg_dump` exiting 0 only proves a
# file was written; this proves the file can be turned back into a database, which
# is the only property anyone actually wants from a backup.
#
# The scratch container is created with --network none and no published ports, so
# it is unreachable from the host and from the other containers while it exists.
#
# Usage:  pg-restore-test.sh [path/to/dump]
# Cron:   0 4 * * 0  /home/rocky/ops/pg-restore-test.sh >> /home/rocky/logs/pg-restore-test.log 2>&1

set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

BACKUP_DIR="${BACKUP_DIR:-/mnt/docker-data/backups/postgres}"
DB_CONTAINER="${DB_CONTAINER:-backend-db-1}"
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
SCRATCH_NAME="restore-test-$$"
READY_TIMEOUT="${READY_TIMEOUT:-60}"

# A fixed name in /tmp is a symlink someone else can plant; mktemp is not.
ERR_FILE="$(mktemp)"

cleanup() {
    docker rm -f "$SCRATCH_NAME" >/dev/null 2>&1 || true
    rm -f "$ERR_FILE"
}
trap cleanup EXIT

main() {
    require_cmd docker flock
    hold_lock pg-restore-test

    local dump
    dump="${1:-$(newest_dump)}"
    [[ -n "$dump" && -f "$dump" ]] || fail "no dump found in $BACKUP_DIR"

    log "restore test using $dump"

    start_scratch
    wait_ready

    if ! docker exec -i "$SCRATCH_NAME" \
        pg_restore -U postgres -d postgres --no-owner --no-privileges < "$dump" 2>"$ERR_FILE"; then
        # pg_restore warns about things that do not matter here (missing roles,
        # extension ownership). Only a hard failure to produce tables is fatal,
        # so fall through to the table count rather than trusting the exit code.
        log "pg_restore exited non-zero; checking whether the schema arrived anyway"
        log "$(tail -5 "$ERR_FILE" 2>/dev/null || true)"
    fi

    local restored expected
    restored="$(count_tables "$SCRATCH_NAME" postgres)"
    expected="$(count_tables "$DB_CONTAINER" '' || echo 0)"

    log "tables restored=$restored, live=$expected"

    if (( restored < 1 )); then
        fail "restore produced no tables from $dump"
    fi

    if (( expected > 0 && restored < expected )); then
        fail "restore is incomplete: $restored of $expected tables from $(basename "$dump")"
    fi

    log "restore test passed: $restored tables from $(basename "$dump")"
}

newest_dump() {
    find "$BACKUP_DIR" -maxdepth 1 -name 'backend_db-*.dump' -printf '%T@ %p\n' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-
}

start_scratch() {
    # Password is random and never leaves this function; nothing connects to this
    # container over the network anyway.
    docker run -d --rm \
        --name "$SCRATCH_NAME" \
        --network none \
        -e POSTGRES_PASSWORD="$(openssl rand -hex 16)" \
        "$PG_IMAGE" >/dev/null || fail "could not start scratch container"
}

wait_ready() {
    local waited=0
    until docker exec "$SCRATCH_NAME" pg_isready -U postgres -q 2>/dev/null; do
        sleep 2
        waited=$(( waited + 2 ))
        if (( waited >= READY_TIMEOUT )); then
            fail "scratch database never became ready within ${READY_TIMEOUT}s"
        fi
    done
    log "scratch database ready after ${waited}s"
}

# count_tables <container> <db-or-empty-to-use-container-env>
count_tables() {
    local container="$1" db="$2"
    local sql="SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"

    if [[ -n "$db" ]]; then
        docker exec "$container" psql -U postgres -d "$db" -tAc "$sql" 2>/dev/null | tr -d '[:space:]'
    else
        docker exec "$container" sh -c \
            "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"$sql\"" 2>/dev/null | tr -d '[:space:]'
    fi
}

fail() {
    local msg="$1"
    log "ERROR: $msg" >&2
    send_notification ":test_tube: **Restore-test feilet** på $(hostname)

$msg

Backupene kan ikke antas å være gjenopprettbare før dette er undersøkt." || true
    exit 1
}

main "$@"
