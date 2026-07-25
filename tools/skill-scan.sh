#!/usr/bin/env bash
#
# SkillSpector wrapper -- the single entry point for scanning agent skills.
#
# Used in three places, all calling this one script so the threshold, the
# baseline and the exit-code rules can never drift apart:
#
#   1. Before installing anything:  tools/skill-scan.sh https://github.com/x/y
#   2. Auditing this machine:       tools/skill-scan.sh --installed
#   3. CI (.github/workflows):      tools/skill-scan.sh --repo
#
# Findings you have looked at and accepted go into a baseline, one file per
# skill, so a re-scan only surfaces what is *new*. Per skill rather than one
# merged file because the fingerprints are content hashes scoped to a relative
# path: merging them lets an accepted finding in one skill silently suppress an
# identical-looking one in another.
#
# `skillspector scan` already exits non-zero on a risky skill, but it only walks
# *immediate* subdirectories and it cannot tell "this skill is dangerous" apart
# from "the scanner crashed". Both matter here: a security gate that treats its
# own failure as a pass is worse than no gate, so every scan must produce a
# parseable report or this script fails closed.
#
# Env:
#   SKILL_SCAN_FAIL_ON      LOW|MEDIUM|HIGH|CRITICAL  severity that fails the run (default HIGH)
#   SKILL_SCAN_BASELINE_DIR directory of baselines    default $CLAUDE_DIR/skillspector-baselines
#   CLAUDE_DIR              agent config dir          default ~/.claude
#   SKILL_SCAN_LLM          1 to enable LLM analysis  default off (no API cost)

set -euo pipefail

FAIL_ON="${SKILL_SCAN_FAIL_ON:-HIGH}"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
BASELINE_DIR="${SKILL_SCAN_BASELINE_DIR:-$CLAUDE_DIR/skillspector-baselines}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACCEPT=0

die() { echo "skill-scan: $*" >&2; exit 2; }

# Reports are written to a scratch dir. The cleanup handler is installed at the
# top level -- registering it inside a function would leave it referencing a
# `local` that is out of scope by the time the trap actually fires -- and it
# hands back the status it was called with, because a successful `rm` must never
# overwrite a failing exit code and turn a tripped gate into a pass.
WORKDIR=""
cleanup() {
    local rc=$?
    [[ -n "$WORKDIR" ]] && rm -rf "$WORKDIR"
    exit "$rc"
}
trap cleanup EXIT

# Severity ranking. Exit codes: 0 clean, 1 gate tripped, 2 could not scan --
# distinct on purpose so CI can tell a real finding from a broken toolchain.
# `tr`, not ${x^^}: macOS ships bash 3.2 and this script has to run identically
# on the laptop that vets a skill and on the ubuntu runner that gates the repo.
severity_rank() {
    case "$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')" in
        LOW)      echo 1 ;;
        MEDIUM)   echo 2 ;;
        HIGH)     echo 3 ;;
        CRITICAL) echo 4 ;;
        *)        echo 0 ;;
    esac
}

usage() {
    cat >&2 <<EOF
usage: $0 [--accept] <path|url>...
       $0 [--accept] --installed    every skill under $CLAUDE_DIR
       $0 [--accept] --repo         every skill committed to this repo

  --accept  record the current findings as a baseline instead of scanning,
            so later runs report only NEW findings. Read them first.
EOF
    exit 2
}

main() {
    (( $# )) || usage

    if [[ "$1" == "--accept" ]]; then
        ACCEPT=1
        shift
        (( $# )) || usage
    fi

    command -v skillspector >/dev/null 2>&1 \
        || die "skillspector not installed -- uv tool install git+https://github.com/NVIDIA/skillspector.git"
    command -v python3 >/dev/null 2>&1 || die "python3 not found"

    local threshold
    threshold="$(severity_rank "$FAIL_ON")"
    (( threshold )) || die "SKILL_SCAN_FAIL_ON must be LOW, MEDIUM, HIGH or CRITICAL (got: $FAIL_ON)"

    # Collected with read -r rather than mapfile for the same bash 3.2 reason,
    # and through process substitution so the array survives the loop.
    local -a targets=()
    local root="" dir
    case "$1" in
        --installed) root="$CLAUDE_DIR" ;;
        --repo)      root="$REPO_ROOT" ;;
        -h|--help)   usage ;;
        -*)          die "unknown option: $1" ;;
        *)           targets=("$@") ;;
    esac

    if [[ -n "$root" ]]; then
        # Checked here, not inside find_skills: that runs in a process
        # substitution, so a die() in there would kill only the subshell and the
        # parent would read an empty list and call a mistyped root a clean pass.
        [[ -d "$root" ]] || die "not a directory: $root"
        while IFS= read -r dir; do
            [[ -n "$dir" ]] && targets+=("$dir")
        done < <(find_skills "$root")
    fi

    if (( ${#targets[@]} == 0 )); then
        # Only reachable via --installed/--repo. Nothing to scan is a pass, but
        # say so out loud: a silently empty gate looks identical to a passing one.
        echo "no SKILL.md found under the requested root -- nothing to scan"
        return 0
    fi

    if (( ACCEPT )); then
        accept_all "${targets[@]}"
        return 0
    fi
    scan_all "$threshold" "${targets[@]}"
}

# One baseline per skill, named after its path so the mapping is obvious when
# you later wonder why a finding stopped being reported.
baseline_path() {
    local slug
    # Leading dots are stripped: most skills live under ~/.claude, and keeping
    # that dot would make every baseline a hidden file -- invisible to `ls`, and
    # easy to lose track of for something whose whole job is suppressing alerts.
    slug="$(printf '%s' "${1#"$HOME"/}" | sed 's|[^A-Za-z0-9._-]|_|g; s|^[._]*||')"
    printf '%s/%s.yaml' "$BASELINE_DIR" "$slug"
}

accept_all() {
    local target out
    mkdir -p "$BASELINE_DIR" || die "cannot create baseline directory: $BASELINE_DIR"

    for target in "$@"; do
        out="$(baseline_path "$target")"
        skillspector baseline "$target" --no-llm --output "$out" >/dev/null 2>&1 || true
        # No baseline file means the accept did not happen. Saying "accepted"
        # anyway would leave you believing findings are triaged when a later
        # scan will still report every one of them.
        [[ -s "$out" ]] || die "could not write a baseline for $target"
        echo "accepted: $(display_name "$target")  ->  $(tildify "$out")"
    done
    echo
    echo "$# baseline(s) written. Future scans report only NEW findings."
}

# Skills nest at arbitrary depth (marketplace/plugins/<p>/skills/<s>/SKILL.md),
# which is why `skillspector -r` alone is not enough.
find_skills() {
    local root="$1"
    [[ -d "$root" ]] || die "not a directory: $root"
    # find's stderr is deliberately not silenced. A directory it cannot read
    # would otherwise shrink the target list without a word, and a gate that
    # skips a skill looks exactly like a gate that cleared it.
    find "$root" \
        \( -name .venv -o -name node_modules -o -name .git -o -name worktrees \) -prune -o \
        -name SKILL.md -print \
        | while IFS= read -r f; do dirname "$f"; done \
        | sort -u
}

scan_all() {
    local threshold="$1"; shift
    local flagged=0 scanned=0
    WORKDIR="$(mktemp -d)" || die "cannot create temp directory"

    local -a llm_arg=(--no-llm)
    [[ "${SKILL_SCAN_LLM:-0}" == "1" ]] && llm_arg=()

    printf '%-8s %-9s %5s  %s\n' "SCORE" "SEVERITY" "FIND" "SKILL"
    printf -- '---------------------------------------------------------------------\n'

    local target report line score severity count rank baseline
    local -a baseline_arg=()
    for target in "$@"; do
        scanned=$((scanned + 1))
        report="$WORKDIR/$scanned.json"

        # A baseline is used when one exists for this exact skill; a missing one
        # simply means nothing has been accepted yet, which must scan everything
        # rather than quietly skip the skill.
        baseline_arg=()
        baseline="$(baseline_path "$target")"
        [[ -s "$baseline" ]] && baseline_arg=(--baseline "$baseline")

        # The exit code is deliberately ignored here: non-zero means either "risky
        # skill" or "scanner broke", and only the report can tell those apart.
        # ${a[@]+"${a[@]}"}: on bash 3.2 an empty array under `set -u` is an
        # unbound-variable error, which would abort the scan mid-gate.
        skillspector scan "$target" \
            ${llm_arg[@]+"${llm_arg[@]}"} ${baseline_arg[@]+"${baseline_arg[@]}"} \
            --format json --output "$report" >/dev/null 2>&1 || true

        [[ -s "$report" ]] || die "no report produced for $target -- scan did not complete"

        line="$(read_report "$report" "$target")" \
            || die "unreadable report for $target -- refusing to call this a pass"

        IFS='|' read -r score severity count <<<"$line"
        printf '%-8s %-9s %5s  %s\n' "$score" "$severity" "$count" "$(display_name "$target")"

        rank="$(severity_rank "$severity")"
        # `count` matters as well as `rank`: a skill with nothing wrong still
        # carries the severity label LOW, so gating on the label alone would make
        # SKILL_SCAN_FAIL_ON=LOW fail every clean skill and be useless.
        if (( count > 0 && rank >= threshold )); then
            flagged=$((flagged + 1))
            details "$report"
        fi
    done

    echo
    if (( flagged )); then
        echo "FAIL: $flagged of $scanned skill(s) at or above $FAIL_ON"
        return 1
    fi
    echo "PASS: $scanned skill(s) scanned, none at or above $FAIL_ON"
}

# Parsing lives in python because a truncated or malformed report must raise,
# not silently yield an empty score that would round down to "clean".
read_report() {
    REPORT="$1" python3 -c '
import json, os, sys
with open(os.environ["REPORT"]) as fh:
    d = json.load(fh)
ra = d["risk_assessment"]
print("%s|%s|%d" % (ra["score"], ra["severity"], len(d.get("issues", []))))
' 2>/dev/null
}

details() {
    REPORT="$1" THRESHOLD="$FAIL_ON" python3 -c '
import json, os
rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
floor = rank[os.environ["THRESHOLD"].upper()]
with open(os.environ["REPORT"]) as fh:
    d = json.load(fh)
for i in d.get("issues", []):
    if rank.get(i.get("severity", "").upper(), 0) < floor:
        continue
    loc = i.get("location") or {}
    where = loc.get("file", "?") if isinstance(loc, dict) else str(loc)
    line = loc.get("start_line") if isinstance(loc, dict) else None
    print("    [%s] %s / %s" % (i["severity"].upper(), i.get("category"), i.get("pattern")))
    print("      %s%s -- %s" % (where, ":%s" % line if line else "", str(i.get("finding", ""))[:100]))
'
}

tildify() {
    case "$1" in
        "$HOME"/*) printf '~%s' "${1#"$HOME"}" ;;
        *)         printf '%s' "$1" ;;
    esac
}

# Full marketplace paths are unreadable in a table; the skill and its plugin are
# what identify it.
display_name() {
    [[ "$1" == *://* ]] && { echo "$1"; return; }
    echo "$1" | rev | cut -d/ -f1-2 | rev
}

main "$@"
