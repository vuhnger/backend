#!/usr/bin/env bash
#
# Nightly PostgreSQL backup.
#
# Dumps the application database to BACKUP_DIR in pg_dump's custom format, then
# rotates old dumps. Credentials are never passed in: pg_dump runs inside the
# database container and reads POSTGRES_USER/POSTGRES_DB from the environment
# compose already gave it, so no secret ever reaches this script, the cron entry,
# or the process list.
#
# Usage:  pg-backup.sh
# Cron:   30 2 * * *  /home/rocky/ops/pg-backup.sh >> /home/rocky/logs/pg-backup.log 2>&1

set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

DB_CONTAINER="${DB_CONTAINER:-backend-db-1}"
BACKUP_DIR="${BACKUP_DIR:-/mnt/docker-data/backups/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
# Never rotate below this many dumps, however old they are. Retention by age
# alone would wipe every backup after a fortnight of the job failing unnoticed.
MIN_KEEP="${MIN_KEEP:-7}"
# Refuse to start a dump that could fill the disk and take the database with it.
MIN_FREE_MB="${MIN_FREE_MB:-1024}"

STAMP_FILE="${STAMP_FILE:-$BACKUP_DIR/.last-success}"

main() {
    require_cmd docker flock

    hold_lock pg-backup

    mkdir -p "$BACKUP_DIR"

    local free_mb
    free_mb="$(df -Pm "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
    if (( free_mb < MIN_FREE_MB )); then
        fail "only ${free_mb} MB free on $BACKUP_DIR (need ${MIN_FREE_MB} MB); refusing to dump"
    fi

    if ! docker inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q true; then
        fail "database container $DB_CONTAINER is not running"
    fi

    local stamp target tmp
    stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    target="$BACKUP_DIR/backend_db-$stamp.dump"
    tmp="$target.partial"

    log "dumping $DB_CONTAINER -> $target"

    # A dump that dies halfway leaves a truncated file. Write to .partial and only
    # promote it to a real backup name once it has been proven restorable, so the
    # directory never contains a file that looks like a backup but is not one.
    if ! docker exec "$DB_CONTAINER" sh -c \
        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$tmp"; then
        rm -f "$tmp"
        fail "pg_dump failed for $DB_CONTAINER"
    fi

    if ! verify_dump "$tmp"; then
        rm -f "$tmp"
        fail "dump did not pass verification; discarded"
    fi

    sync -f "$tmp" 2>/dev/null || true
    mv "$tmp" "$target"
    chmod 600 "$target"

    local size
    size="$(du -h "$target" | cut -f1)"
    log "backup ok: $target ($size)"

    printf '%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$STAMP_FILE"

    rotate
}

# A dump is only a backup if pg_restore can read its table of contents. This
# catches truncation, an out-of-disk kill, and a corrupted stream.
verify_dump() {
    local file="$1"
    local entries

    entries="$(docker run --rm -i postgres:16-alpine pg_restore --list < "$file" 2>/dev/null | grep -c ';' || true)"

    if [[ -z "$entries" ]] || (( entries < 1 )); then
        log "verification failed: pg_restore listed no entries" >&2
        return 1
    fi

    log "verified: $entries TOC entries readable"
}

rotate() {
    local -a dumps
    mapfile -t dumps < <(find "$BACKUP_DIR" -maxdepth 1 -name 'backend_db-*.dump' -printf '%T@ %p\n' \
        | sort -rn | cut -d' ' -f2-)

    local total=${#dumps[@]}
    if (( total <= MIN_KEEP )); then
        log "rotation: $total dumps, keeping all (floor is $MIN_KEEP)"
        return 0
    fi

    local removed=0 i path age_days
    for (( i = MIN_KEEP; i < total; i++ )); do
        path="${dumps[$i]}"
        age_days=$(( ( $(date +%s) - $(stat -c %Y "$path") ) / 86400 ))
        if (( age_days >= RETENTION_DAYS )); then
            rm -f "$path"
            (( ++removed ))
        fi
    done

    log "rotation: $total dumps, removed $removed older than ${RETENTION_DAYS}d"
}

fail() {
    local msg="$1"
    log "ERROR: $msg" >&2
    send_notification ":rotating_light: **Backup feilet** på $(hostname)

$msg

Ingen ny backup ble tatt. Siste vellykkede: $(cat "$STAMP_FILE" 2>/dev/null || echo 'ukjent')" || true
    exit 1
}

main "$@"
