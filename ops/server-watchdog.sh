#!/usr/bin/env bash
#
# Hourly server watchdog.
#
# Supersedes backend_healthcheck.sh, which only asked "are the containers up?"
# once a day. Every incident on 2026-07-25 passed that test while it happened:
# the Caddyfile was invalid for hours, 64k systemd unit tombstones ate 890 MB of
# RAM, a TLS certificate had been dead for 77 days, and the root disk crept to
# 80%. Containers were up and every endpoint returned 200 throughout.
#
# So this measures margins, not liveness. Each check reports how much room is
# left before something breaks, and the alert fires while there is still time to
# act.
#
# Usage:  server-watchdog.sh [--dry-run]
# Cron:   7 * * * *  ~/backend/ops/server-watchdog.sh >> ~/logs/watchdog.log 2>&1

set -euo pipefail

. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

# 80, not 85: the incident this script was written for was a root disk at 80%,
# and a default that would have slept through it is not a default.
DISK_WARN_PCT="${DISK_WARN_PCT:-80}"
MEM_MIN_MB="${MEM_MIN_MB:-250}"
PID1_MAX_MB="${PID1_MAX_MB:-200}"
UNITS_MAX="${UNITS_MAX:-1000}"
CERT_MIN_DAYS="${CERT_MIN_DAYS:-14}"
BACKUP_MAX_AGE_H="${BACKUP_MAX_AGE_H:-30}"

CONTAINER_PATTERN="${CONTAINER_PATTERN:-^backend-.*-1$}"
HEALTH_URLS="${HEALTH_URLS:-https://api.vuhnger.dev/site/health https://api.vuhnger.dev/projects/health https://api.vuhnger.dev/strava/health https://api.vuhnger.dev/wakatime/health https://analytics.vuhnger.dev}"
CERT_HOSTS="${CERT_HOSTS:-api.vuhnger.dev analytics.vuhnger.dev}"
BACKUP_STAMP="${BACKUP_STAMP:-/mnt/docker-data/backups/postgres/.last-success}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"

STATE_DIR="${STATE_DIR:-$HOME/.local/state/backend-watchdog}"
STATE_FILE="$STATE_DIR/last-alert"
# A condition that stays broken should not produce 24 identical alerts a day.
# Re-alert at most this often while nothing changes.
REMIND_HOURS="${REMIND_HOURS:-12}"

DRY_RUN=0
PROBLEMS=()

problem() { PROBLEMS+=("$1"); }

main() {
    [[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

    require_cmd docker curl awk
    mkdir -p "$STATE_DIR"

    check_containers
    check_endpoints
    check_disk
    check_memory
    check_systemd
    check_caddy
    check_certs
    check_backup

    report
}

# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

check_containers() {
    local -a names
    mapfile -t names < <(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -E "$CONTAINER_PATTERN" || true)

    if (( ${#names[@]} == 0 )); then
        problem "Ingen containere matcher '$CONTAINER_PATTERN' -- stacken er nede eller omdøpt"
        return
    fi

    local name state health
    for name in "${names[@]}"; do
        state="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo unknown)"
        health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$name" 2>/dev/null || echo unknown)"

        if [[ "$state" != "running" ]]; then
            problem "Container $name: state=$state"
        elif [[ "$health" != "n/a" && "$health" != "healthy" ]]; then
            problem "Container $name: health=$health"
        fi
    done
}

# Tests through Caddy over the public name, not against the container port. A
# container can be perfectly healthy while the edge in front of it is broken --
# which is exactly the failure that went unnoticed.
check_endpoints() {
    local url code
    for url in $HEALTH_URLS; do
        code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$url" 2>/dev/null || echo 000)"
        [[ "$code" == "200" ]] || problem "Endepunkt $url svarte $code"
    done
}

check_disk() {
    local mount pct
    for mount in / /mnt/docker-data; do
        [[ -d "$mount" ]] || continue
        # `set -o pipefail` makes a failing df abort the assignment, and `set -e`
        # would then kill the whole watchdog run rather than skip one mount.
        pct="$(df -P "$mount" 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5}')" || pct=""
        [[ -n "$pct" ]] || continue
        (( pct >= DISK_WARN_PCT )) && problem "Disk $mount er ${pct}% full (grense ${DISK_WARN_PCT}%)"
    done
    return 0
}

check_memory() {
    local avail_mb swap_used_mb swap_total_mb
    avail_mb="$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)"
    swap_total_mb="$(awk '/SwapTotal/ {print int($2/1024)}' /proc/meminfo)"
    swap_used_mb=$(( swap_total_mb - $(awk '/SwapFree/ {print int($2/1024)}' /proc/meminfo) ))

    (( avail_mb < MEM_MIN_MB )) && problem "Kun ${avail_mb} MB ledig minne (grense ${MEM_MIN_MB} MB)"

    # No swap at all is how a fork failure turns into an outage rather than a
    # slowdown; that is what happened here.
    (( swap_total_mb == 0 )) && problem "Ingen swap konfigurert"

    if (( swap_total_mb > 0 )) && (( swap_used_mb * 100 / swap_total_mb > 75 )); then
        problem "Swap er ${swap_used_mb}/${swap_total_mb} MB i bruk -- maskinen bytter tungt"
    fi
    return 0
}

# The 2026-07-25 leak in one check: PID 1 grew to 890 MB because failed transient
# units are retained in memory forever. Both numbers are flat on a healthy box.
check_systemd() {
    local pid1_kb pid1_mb units failed
    # Under memory pressure -- the very condition being measured -- systemctl is
    # what fails first. Letting that abort the run would silence the watchdog at
    # exactly the moment it matters, so an unreadable value becomes a finding.
    pid1_kb="$(ps -o rss= -p 1 2>/dev/null | awk '{print $1}')" || pid1_kb=""
    units="$(systemctl list-units --all --plain --no-pager 2>/dev/null | wc -l)" || units=""
    failed="$(systemctl --failed --plain --no-pager 2>/dev/null | grep -c '\.service')" || failed=0

    if [[ -z "$pid1_kb" || -z "$units" ]]; then
        problem "Fikk ikke lest systemd-tall (ps/systemctl svarte ikke) -- selve verktøyet kan være rammet"
        return 0
    fi
    pid1_mb=$(( pid1_kb / 1024 ))

    (( pid1_mb > PID1_MAX_MB )) && problem "systemd (PID 1) bruker ${pid1_mb} MB (normalt ~15 MB) -- kjør 'systemctl reset-failed' så 'daemon-reexec'"
    (( units > UNITS_MAX )) && problem "${units} systemd-units lastet (grense ${UNITS_MAX}) -- gravsteiner hoper seg opp"
    (( failed > 5 )) && problem "${failed} feilede systemd-units"
    return 0
}

# Catches the exact failure that started all of this: a Caddyfile that no longer
# parses while caddy happily serves its last good config from memory.
check_caddy() {
    command -v caddy >/dev/null 2>&1 || return 0
    [[ -f "$CADDYFILE" ]] || return 0

    caddy validate --adapter caddyfile --config "$CADDYFILE" >/dev/null 2>&1 \
        || problem "$CADDYFILE er UGYLDIG -- kjøres fra minnet nå, men neste restart tar ned alt"
    return 0
}

check_certs() {
    local host expiry_date expiry_epoch days
    for host in $CERT_HOSTS; do
        # An unreachable host makes this pipeline fail, and with `pipefail` the
        # assignment fails with it -- killing the entire watchdog before it could
        # report the unreachable host. Empty means "could not probe", handled below.
        expiry_date="$(echo | timeout 15 openssl s_client -connect "$host:443" -servername "$host" 2>/dev/null \
            | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)" || expiry_date=""

        if [[ -z "$expiry_date" ]]; then
            problem "Fikk ikke hentet sertifikat for $host"
            continue
        fi

        expiry_epoch="$(date -d "$expiry_date" +%s 2>/dev/null || echo 0)"
        (( expiry_epoch == 0 )) && continue
        days=$(( (expiry_epoch - $(date +%s)) / 86400 ))

        (( days < CERT_MIN_DAYS )) && problem "Sertifikatet for $host utløper om ${days} dager"
    done
    return 0
}

check_backup() {
    if [[ ! -s "$BACKUP_STAMP" ]]; then
        problem "Ingen vellykket backup registrert ($BACKUP_STAMP mangler)"
        return 0
    fi

    local last_epoch age_h
    last_epoch="$(date -d "$(cat "$BACKUP_STAMP")" +%s 2>/dev/null || echo 0)"
    if (( last_epoch == 0 )); then
        problem "Kan ikke tolke tidsstempelet i $BACKUP_STAMP"
        return 0
    fi

    age_h=$(( ( $(date +%s) - last_epoch ) / 3600 ))
    (( age_h > BACKUP_MAX_AGE_H )) && problem "Siste vellykkede backup er ${age_h} timer gammel (grense ${BACKUP_MAX_AGE_H}t)"
    return 0
}

# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------

report() {
    local count=${#PROBLEMS[@]}

    if (( count == 0 )); then
        log "alle sjekker OK"
        # Only announce recovery if there was something to recover from -- and
        # only clear the state once the announcement actually went out, so a
        # failed delivery is retried instead of being forgotten.
        if [[ -s "$STATE_FILE" ]]; then
            if (( DRY_RUN )); then
                log "(dry-run: ville meldt at alt er friskt igjen)"
            elif notify ":white_check_mark: **Alt friskt igjen** på $(hostname)"; then
                rm -f "$STATE_FILE"
            fi
        fi
        return 0
    fi

    local body
    body="$(printf '%s\n' "${PROBLEMS[@]}")"
    log "$count problem(er):"
    printf -- '- %s\n' "${PROBLEMS[@]}"

    if (( DRY_RUN )); then
        log "(dry-run: varsler ikke)"
        return 0
    fi

    # Suppress repeats of an identical, still-unresolved condition so the channel
    # stays worth reading. A change in the problem set always alerts immediately.
    local fingerprint previous last_epoch
    fingerprint="$(printf '%s' "$body" | cksum | cut -d' ' -f1)"
    previous=""
    last_epoch=0
    if [[ -s "$STATE_FILE" ]]; then
        previous="$(head -1 "$STATE_FILE")"
        last_epoch="$(tail -1 "$STATE_FILE")"
    fi

    if [[ "$fingerprint" == "$previous" ]] \
        && (( ( $(date +%s) - last_epoch ) < REMIND_HOURS * 3600 )); then
        log "uendret siden forrige varsel; hopper over (påminnelse hver ${REMIND_HOURS}t)"
        return 0
    fi

    # Record the alert as sent only if it was. Otherwise an undelivered warning
    # would start the REMIND_HOURS clock and suppress every retry for half a day.
    if notify ":warning: **${count} problem(er)** på $(hostname)

$body"; then
        printf '%s\n%s\n' "$fingerprint" "$(date +%s)" > "$STATE_FILE"
    fi
}

notify() {
    if ! send_notification "$1"; then
        log "ADVARSEL: kunne ikke levere varselet" >&2
        return 1
    fi
}

main "$@"
