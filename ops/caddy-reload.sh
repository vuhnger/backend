#!/usr/bin/env bash
#
# Safe Caddy reload.
#
# On 2026-07-25 the Caddyfile sat syntactically invalid for hours without a single
# symptom: caddy kept serving its last good in-memory config, systemctl reported
# active, and every endpoint returned 200. The only thing that would have surfaced
# it was a reboot, at which point every site would have gone down at once.
#
# This script makes that state unreachable by tying the four steps together:
#   1. validate the file           -- never load something that does not parse
#   2. reload                      -- systemctl, falling back to the admin API
#   3. verify against the admin API -- prove the running config is the file's
#   4. commit                      -- /etc/caddy is a git repo; keep it honest
#
# Usage:  caddy-reload.sh ["commit message"]

set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
ADMIN="${CADDY_ADMIN:-http://localhost:2019}"

# File scope, not local to main: the EXIT trap fires after main has returned, so
# a local would be out of scope by then and `set -u` would abort the trap -- which
# made the script exit non-zero after a completely successful reload.
ADAPTED=""

cleanup() {
    [[ -n "$ADAPTED" ]] && rm -f "$ADAPTED"
    return 0
}
trap cleanup EXIT

main() {
    require_cmd caddy curl python3
    [[ -f "$CADDYFILE" ]] || die "no such file: $CADDYFILE"

    ADAPTED="$(mktemp)"
    local adapted="$ADAPTED"

    log "validating $CADDYFILE"
    if ! caddy validate --adapter caddyfile --config "$CADDYFILE" >/dev/null 2>&1; then
        # Re-run without suppression so the operator sees the parse error itself.
        caddy validate --adapter caddyfile --config "$CADDYFILE" 2>&1 | grep -i error >&2 || true
        die "Caddyfile is invalid; nothing was reloaded"
    fi
    log "valid"

    caddy adapt --adapter caddyfile --config "$CADDYFILE" > "$adapted" 2>/dev/null \
        || die "could not adapt config"

    reload "$adapted"
    verify "$adapted"
    commit "${1:-update Caddyfile}"

    log "reload complete and verified"
}

reload() {
    local adapted="$1"

    if sudo systemctl reload caddy 2>/dev/null; then
        log "reloaded via systemctl"
        return 0
    fi

    # systemctl reload needs systemd to fork a helper, which fails under memory
    # pressure (see ops/README.md). The admin API runs inside the existing caddy
    # process and needs no fork, so it still works when systemctl does not.
    log "systemctl reload failed; falling back to the admin API"
    # A timeout or refused connection makes curl exit non-zero, which under
    # `set -e` would kill the script at the assignment -- before the HTTP check
    # below could say why. Catch the transport failure separately.
    local code
    if ! code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 \
        -X POST -H 'Content-Type: application/json' \
        --data-binary "@$adapted" "$ADMIN/load")"; then
        die "could not reach the admin API at $ADMIN"
    fi

    [[ "$code" == "200" ]] || die "admin API load returned HTTP $code"
    log "reloaded via admin API"
}

# Compare what caddy is actually running against what the file says. Without this
# the script would report success for a reload that silently did not take.
verify() {
    local adapted="$1"
    local live
    live="$(mktemp)"

    curl -fsS --max-time 15 "$ADMIN/config/" > "$live" || {
        rm -f "$live"
        die "could not read running config from the admin API"
    }

    # Compare every top-level section the Caddyfile actually declares -- apps, but
    # also logging and admin -- rather than apps alone, which would call a reload
    # that changed only logging a success. Sections present solely in the running
    # config are Caddy's own defaults and would produce false mismatches, so they
    # are not required to appear in the adapted output.
    if python3 -c '
import json, sys
with open(sys.argv[1]) as f: want = json.load(f)
with open(sys.argv[2]) as f: live = json.load(f)
missing = [k for k, v in want.items() if live.get(k) != v]
if missing:
    print("sections that did not take: " + ", ".join(sorted(missing)), file=sys.stderr)
sys.exit(1 if missing else 0)
' "$adapted" "$live"; then
        log "running config matches $CADDYFILE"
        rm -f "$live"
    else
        rm -f "$live"
        die "running config does NOT match $CADDYFILE -- reload did not take effect"
    fi
}

commit() {
    local message="$1"
    local dir
    dir="$(dirname "$CADDYFILE")"

    [[ -d "$dir/.git" ]] || { log "no git repo in $dir; skipping commit"; return 0; }

    if sudo git -C "$dir" diff --quiet -- "$(basename "$CADDYFILE")" 2>/dev/null; then
        log "no changes to commit"
        return 0
    fi

    sudo git -C "$dir" add "$(basename "$CADDYFILE")"
    sudo git -C "$dir" commit -q -m "$message"
    log "committed: $message"
}

main "$@"
