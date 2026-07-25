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
    local message="FATAL: $*"
    log "$message" >&2
    # These scripts run unattended. A fatal error that only reaches a log file
    # nobody reads is a silent failure -- the exact class of problem they exist
    # to catch. Never let a failed notification mask the original error.
    send_notification "$message" || true
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

    # Anything but a plain https URL is either a corrupted file or an attempt to
    # smuggle extra directives into the curl config below.
    if [[ "$webhook_url" != https://* || "$webhook_url" == *[\"\\]* ]]; then
        log "cannot notify: webhook file does not contain a plain https URL" >&2
        return 1
    fi

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

    # The URL is the secret, so it must not become a curl argument: argv is world
    # readable through `ps` and /proc for every user on the box. Feeding it as a
    # curl config file on stdin keeps it out of the process table entirely.
    printf 'url = "%s"\n' "$webhook_url" \
        | curl -fsS --max-time 15 --retry 2 --retry-delay 3 \
            -H "Content-Type: application/json" \
            -d "$payload" --config - >/dev/null
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
    local rc=0

    require_cmd flock
    mkdir -p "$LOCK_DIR" || die "cannot create lock directory: $LOCK_DIR"
    exec 9>"$lockfile" || die "cannot open lock file: $lockfile"

    # Give contention its own exit code. A bare `flock -n 9 || exit 0` cannot tell
    # "another copy is running" from "flock is broken", so any operational failure
    # would look like a healthy skip and the job would quietly do nothing -- every
    # night, without a single alert.
    flock -n --conflict-exit-code 66 9 || rc=$?
    case "$rc" in
        0)  ;;
        66) log "another instance is already running ($lockfile); exiting"; exit 0 ;;
        *)  die "could not acquire lock $lockfile (flock exited $rc)" ;;
    esac
}
