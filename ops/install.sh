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

# The one cron line the old setup used, matched in full so that a hand-written
# variant of it is never silently thrown away. Override if yours differs.
LEGACY_CRON="${LEGACY_CRON:-15 9 * * * $HOME/scripts/backend_healthcheck.sh >> $HOME/logs/backend_healthcheck.log 2>&1}"

die() { echo "install.sh: $*" >&2; exit 1; }

main() {
    # A typo like --uninstal must not silently fall through to a full install,
    # which would rewrite the managed cron block.
    case "${1:-}" in
        "")          ;;
        --uninstall) uninstall; exit 0 ;;
        *)           die "unknown argument: $1 (usage: $0 [--uninstall])" ;;
    esac

    # Before anything is written, not after: a syntax error found post-install
    # leaves broken scripts on disk and broken jobs in cron.
    verify
    install_scripts
    install_dirs
    install_cron

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
    # Only the directory itself changes hands: a recursive chown of its parent
    # would take ownership of every unrelated backup set stored alongside it.
    if [[ ! -d "$BACKUP_DIR" ]]; then
        sudo mkdir -p "$BACKUP_DIR"
        sudo chown "$(id -u):$(id -g)" "$BACKUP_DIR"
        sudo chmod 0700 "$BACKUP_DIR"
    fi
    echo "backup dir: $BACKUP_DIR"
}

# `crontab -l 2>/dev/null || true` turns *any* read failure into an empty crontab,
# and the crontab written from it would then wipe every hand-written job on the
# box. Only "this user has no crontab yet" may be treated as empty.
read_crontab() {
    local out rc=0
    out="$(crontab -l 2>&1)" || rc=$?

    if (( rc == 0 )); then
        printf '%s\n' "$out"
        return 0
    fi
    [[ "$out" == *"no crontab for"* ]] && return 0

    die "cannot read the current crontab (exit $rc): $out"
}

install_cron() {
    local current new
    current="$(read_crontab)"

    # Drop any previous managed block.
    new="$(printf '%s\n' "$current" \
        | sed "/$(escape "$BEGIN_MARK")/,/$(escape "$END_MARK")/d")"

    # Retire the old daily container-only healthcheck -- server-watchdog.sh covers
    # it and much more, hourly. Matched as a whole line against the exact legacy
    # entry: a substring match on the script name would also delete a hand-written
    # invocation of it, which this script promises never to touch.
    if printf '%s\n' "$new" | grep -qxF -- "$LEGACY_CRON"; then
        new="$(printf '%s\n' "$new" | grep -vxF -- "$LEGACY_CRON" || true)"
        echo "retired the legacy healthcheck entry (superseded by server-watchdog.sh)"
    fi

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
    current="$(read_crontab)"
    printf '%s\n' "$current" \
        | sed "/$(escape "$BEGIN_MARK")/,/$(escape "$END_MARK")/d" \
        | crontab -
    echo "cron block removed (scripts and backups left in place)"
}

verify() {
    local script ok=1
    # common.sh included: every other script sources it, so a syntax error there
    # breaks all four at once. Checked in $SRC_DIR because this runs before install.
    for script in common.sh pg-backup.sh pg-restore-test.sh server-watchdog.sh caddy-reload.sh; do
        bash -n "$SRC_DIR/$script" || { echo "SYNTAX ERROR in $script" >&2; ok=0; }
    done
    (( ok )) || die "refusing to install scripts that do not parse"
    echo "syntax check passed"
}

# sed treats / and & specially; marker text contains neither today, but escaping
# keeps this from breaking silently if the markers are ever edited.
escape() { printf '%s' "$1" | sed 's/[\/&]/\\&/g'; }

main "$@"
