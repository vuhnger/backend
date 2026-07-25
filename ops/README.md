# ops/

Server-side operational scripts for the NREC host. They are not part of the
application and are not deployed by `deploy.yml`; install them explicitly:

```bash
ssh nrec
cd ~/backend && git pull
ops/install.sh
```

## Why these exist

Four things broke on 2026-07-25, and the monitoring at the time reported a
healthy system throughout every one of them:

| What happened | Why nothing noticed |
|---|---|
| The Caddyfile was syntactically invalid for hours | Caddy keeps serving its last good config from memory. `systemctl is-active` said `active`; every endpoint returned 200. Only a reboot would have surfaced it, by taking every site down at once. |
| systemd (PID 1) grew to 890 MB | 64,576 failed `systemd-coredump@*` unit tombstones, retained in RAM forever. Eventually systemd could not fork and every `systemctl` verb failed with ENOMEM. |
| `ruta.vuhnger.dev` served no certificate for 77 days | Nothing checked certificate expiry. Caddy retried ACME every 10 minutes into the void. |
| The root disk reached 80% | Nothing checked disk, and a 39 GB second volume sat mounted and empty the whole time. |

The common shape is **silent degradation**: the system looked fine until two
problems coincided. So `server-watchdog.sh` measures how much margin is left,
rather than whether things are currently up.

## Scripts

| Script | Schedule | What it does |
|---|---|---|
| `server-watchdog.sh` | hourly, :07 | Containers, public endpoints through Caddy, disk, memory, swap, PID 1 RSS, unit counts, Caddyfile validity, TLS expiry, backup age |
| `pg-backup.sh` | nightly, 02:30 | `pg_dump -Fc` → `/mnt/docker-data/backups/postgres`, verified before being accepted, then rotated |
| `pg-restore-test.sh` | Sundays, 04:00 | Restores the newest dump into a throwaway container and counts the tables |
| `caddy-reload.sh` | manual | validate → reload → verify against the admin API → commit to `/etc/caddy` |

All four alert to the same Discord webhook the previous healthcheck used:
`~/.config/backend-healthcheck/discord_webhook_url`. The URL exists only in that
file — never in a script, a cron entry, or this repo.

## Design notes

**Backups are verified, not assumed.** `pg_dump` exiting 0 only proves a file was
written. `pg-backup.sh` writes to `.partial`, runs `pg_restore --list` against it,
and only then renames it to a real backup name — so the directory can never hold a
file that looks like a backup but is not one. `pg-restore-test.sh` goes further and
restores into a live throwaway database weekly, because a backup nobody has ever
restored is a guess.

**Rotation has a floor.** Deleting by age alone would erase every backup after a
fortnight of the job failing unnoticed. `MIN_KEEP` (default 7) is never crossed
regardless of age.

**Credentials stay in the container.** `pg_dump` runs via `docker exec` and reads
`POSTGRES_USER`/`POSTGRES_DB` from the environment compose already gave the
database container. No secret reaches these scripts, the cron entries, or `ps`.

**Alerts deduplicate.** A condition that stays broken re-alerts at most every
`REMIND_HOURS` (default 12), and any change in the problem set alerts immediately.
An alert channel that cries every hour stops being read.

**`caddy-reload.sh` falls back to the admin API.** `systemctl reload` needs systemd
to fork a helper process, which is exactly what fails under the memory pressure you
most want to fix. The admin API runs inside the existing Caddy process and needs no
fork.

## Configuration

Every threshold is an environment variable with a default; nothing is hardcoded.
The ones worth knowing:

| Variable | Default | Meaning |
|---|---|---|
| `DISK_WARN_PCT` | `85` | Alert above this fill level |
| `MEM_MIN_MB` | `250` | Alert below this much available memory |
| `PID1_MAX_MB` | `200` | Alert if systemd exceeds this (normal is ~15 MB) |
| `UNITS_MAX` | `1000` | Alert on unit-tombstone accumulation |
| `CERT_MIN_DAYS` | `14` | Alert this long before a certificate expires |
| `BACKUP_MAX_AGE_H` | `30` | Alert if the last good backup is older than this |
| `RETENTION_DAYS` | `14` | Backup age limit |
| `MIN_KEEP` | `7` | Backups never rotated below this count |

## Recovering from the PID 1 leak

If the watchdog reports systemd using hundreds of MB, the order matters:

```bash
systemctl reset-failed     # clear the tombstones FIRST
systemctl daemon-reexec    # then reclaim the heap
```

Doing `daemon-reexec` first makes it worse — it re-serializes every retained unit.
Observed on 2026-07-25: 849 MB → 1,325 MB in the wrong order, then 1,325 MB → 13 MB
in the right one.

## Restoring a backup for real

```bash
ls -lt /mnt/docker-data/backups/postgres/
docker compose stop strava-api wakatime-api projects-api site-api n8n-api
docker exec -i backend-db-1 sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
  < /mnt/docker-data/backups/postgres/backend_db-<stamp>.dump
docker compose start strava-api wakatime-api projects-api site-api n8n-api
```

Backups are on `/dev/sdb`, a separate physical volume from the root disk, but still
on this host. They protect against a deleted volume, a bad migration, and disk
corruption — not against losing the VM. Off-site copies are not set up.
