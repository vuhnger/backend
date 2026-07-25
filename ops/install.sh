#!/usr/bin/env bash
#
# Installs the ops scripts and their cron entries on the server. Idempotent --
# safe to re-run after every deploy.
#
# Cron entries live inside a marked block so re-running rewrites only that block
# and leaves hand-written entries (the hourly strava/wakatime tasks) untouched.
#
# Usage:  ops/install.sh [--uninstall]

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_DIR="${DEST_DIR:-$HOME/ops}"
LOG_DIR="${LOG_DIR:-$HOME/logs}"
BACKUP_DIR="${BACKUP_DIR:-/mnt/docker-data/backups/postgres}"

BEGIN_MARK="# >>> backend ops (managed by ops/install.sh) >>>"
END_MARK="# <<< backend ops <<<"

main() {
    [[ "${1:-}" == "--uninstall" ]] && { uninstall; exit 0; }

    install_scripts
    install_dirs
    install_cron
    verify

    cat <<EOF

Installert i $DEST_DIR. Cron-blokka er skrevet.

Neste steg, som ikke gjøres automatisk fordi de trenger et menneske:
  1. Sjekk at webhooken finnes:  test -s ~/.config/backend-healthcheck/discord_webhook_url
  2. Tørrkjør vaktbikkja:        $DEST_DIR/server-watchdog.sh --dry-run
  3. Ta en backup nå:            $DEST_DIR/pg-backup.sh
  4. Bevis at den kan gjenopprettes: $DEST_DIR/pg-restore-test.sh
EOF
}

install_scripts() {
    mkdir -p "$DEST_DIR"
    install -m 0644 "$SRC_DIR/common.sh" "$DEST_DIR/common.sh"

    local script
    for script in pg-backup.sh pg-restore-test.sh server-watchdog.sh caddy-reload.sh; do
        install -m 0755 "$SRC_DIR/$script" "$DEST_DIR/$script"
        echo "installed $DEST_DIR/$script"
    done
}

install_dirs() {
    mkdir -p "$LOG_DIR"

    # The backup directory lives on the large second disk, not the root volume.
    if [[ ! -d "$BACKUP_DIR" ]]; then
        sudo mkdir -p "$BACKUP_DIR"
        sudo chown -R "$(id -u):$(id -g)" "$(dirname "$BACKUP_DIR")"
    fi
    echo "backup dir: $BACKUP_DIR"
}

install_cron() {
    local current new
    current="$(crontab -l 2>/dev/null || true)"

    # Drop any previous managed block, and retire the old daily container-only
    # healthcheck -- server-watchdog.sh covers it and much more, hourly.
    new="$(printf '%s\n' "$current" \
        | sed "/$(escape "$BEGIN_MARK")/,/$(escape "$END_MARK")/d" \
        | grep -v 'backend_healthcheck.sh' || true)"

    new+="
$BEGIN_MARK
# Hourly: margins, not liveness. See ops/server-watchdog.sh.
7 * * * * $DEST_DIR/server-watchdog.sh >> $LOG_DIR/watchdog.log 2>&1
# Nightly 02:30: dump + verify + rotate.
30 2 * * * $DEST_DIR/pg-backup.sh >> $LOG_DIR/pg-backup.log 2>&1
# Sunday 04:00: prove the newest dump actually restores.
0 4 * * 0 $DEST_DIR/pg-restore-test.sh >> $LOG_DIR/pg-restore-test.log 2>&1
$END_MARK"

    printf '%s\n' "$new" | crontab -
    echo "cron block written"
}

uninstall() {
    local current
    current="$(crontab -l 2>/dev/null || true)"
    printf '%s\n' "$current" \
        | sed "/$(escape "$BEGIN_MARK")/,/$(escape "$END_MARK")/d" \
        | crontab -
    echo "cron block removed (scripts and backups left in place)"
}

verify() {
    local script ok=1
    for script in pg-backup.sh pg-restore-test.sh server-watchdog.sh caddy-reload.sh; do
        bash -n "$DEST_DIR/$script" || { echo "SYNTAX ERROR in $script" >&2; ok=0; }
    done
    (( ok )) || exit 1
    echo "syntax check passed"
}

# sed treats / and & specially; marker text contains neither today, but escaping
# keeps this from breaking silently if the markers are ever edited.
escape() { printf '%s' "$1" | sed 's/[\/&]/\\&/g'; }

main "$@"
