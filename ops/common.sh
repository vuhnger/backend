#!/usr/bin/env bash
#
# Shared helpers for the ops scripts. Source it, do not execute it:
#
#   . "$(dirname "$0")/common.sh"
#
# Every script here runs unattended from cron, so the rules are: fail loudly to
# the notifier, never print secrets, and never block forever on the network.

# Cron gets a minimal PATH. linuxbrew first because python3 and docker live there.
PATH=/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin
export PATH

# Where the Discord webhook URL is kept. One line, no trailing junk. The file is
# the only place the URL exists -- it must never be baked into a script or a cron
# entry, both of which end up in git or in `ps` output.
WEBHOOK_FILE="${WEBHOOK_FILE:-$HOME/.config/backend-healthcheck/discord_webhook_url}"

# Discord rejects payloads over 2000 characters outright, so a long alert would
# be silently lost -- exactly when you most want it delivered.
readonly MAX_MESSAGE_CHARS=1900

log() {
    printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
    log "FATAL: $*" >&2
    exit 1
}

# send_notification <message>
#
# Returns non-zero if the message could not be delivered, so callers can decide
# whether an undeliverable alert is itself fatal.
send_notification() {
    local message="$1"
    local webhook_url payload

    if [[ ! -s "$WEBHOOK_FILE" ]]; then
        log "cannot notify: webhook file missing or empty: $WEBHOOK_FILE" >&2
        return 1
    fi

    webhook_url="$(<"$WEBHOOK_FILE")"

    if (( ${#message} > MAX_MESSAGE_CHARS )); then
        message="${message:0:$MAX_MESSAGE_CHARS}"$'\n[...avkortet]'
    fi

    # Build the JSON in python rather than by string concatenation: an alert body
    # containing a quote or a newline would otherwise produce invalid JSON and the
    # alert would vanish.
    payload="$(CONTENT="$message" python3 -c '
import json, os
print(json.dumps({"content": os.environ["CONTENT"]}))
')" || {
        log "cannot notify: failed to build payload" >&2
        return 1
    }

    curl -fsS --max-time 15 --retry 2 --retry-delay 3 \
        -H "Content-Type: application/json" \
        -d "$payload" "$webhook_url" >/dev/null
}

# require_cmd <name>...
require_cmd() {
    local cmd
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || die "required command not found: $cmd"
    done
}

# Locks live under $HOME, not /var/lock: that directory is root-owned, so these
# scripts cannot create a lock file there and would abort on every cron run.
LOCK_DIR="${LOCK_DIR:-$HOME/.local/state/backend-ops}"

# Single-instance guard. A backup that overruns its hour must not have a second
# copy started on top of it.
#
#   hold_lock pg-backup
hold_lock() {
    local name="$1"
    local lockfile="$LOCK_DIR/$name.lock"

    mkdir -p "$LOCK_DIR" || die "cannot create lock directory: $LOCK_DIR"
    exec 9>"$lockfile" || die "cannot open lock file: $lockfile"
    flock -n 9 || {
        log "another instance is already running ($lockfile); exiting"
        exit 0
    }
}
