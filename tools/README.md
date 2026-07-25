# Agent skill scanning

[SkillSpector](https://github.com/NVIDIA/skillspector) (NVIDIA, Apache-2.0) scans
agent skills for prompt injection, data exfiltration, privilege escalation and
supply-chain risk. Agent skills execute with your privileges and are installed
with roughly the vetting of a curl-pipe-bash, which is the gap this closes.

`skill-scan.sh` is the only entry point. Three uses, one script, so the
threshold and the exit-code rules cannot drift apart between them.

## Install

```bash
uv tool install 'skillspector[mcp] @ git+https://github.com/NVIDIA/skillspector.git@fd25398d7aa99353d86237b9c260759351f0e644'
```

Pinned to a commit because upstream publishes no tags. The same SHA is pinned in
`.github/workflows/skillspector.yml` — bump both together.

## Use

```bash
make skill-scan target=https://github.com/someone/their-skill   # before installing
make skill-audit                                                # everything under ~/.claude
tools/skill-scan.sh --repo                                      # what CI runs
```

Exit codes are the contract:

| Code | Meaning |
| --- | --- |
| `0` | nothing at or above the threshold |
| `1` | a skill tripped the gate |
| `2` | the scan could not complete — **not** a pass |

Code `2` is separate on purpose. A gate that reports its own failure as success
is worse than no gate, so a missing or unparseable report is a hard error. Call
the script directly rather than through `make` when you need that distinction —
`make` reports both as its own exit 2.

Knobs: `SKILL_SCAN_FAIL_ON` (default `HIGH`), `SKILL_SCAN_BASELINE_DIR`,
`CLAUDE_DIR`, `SKILL_SCAN_LLM=1` to add the LLM pass (costs API credits; static
analysis is the default).

## Baselines

Static pattern matching is noisy on legitimate skills. Accept what you have
triaged so re-scans only surface what is *new*:

```bash
tools/skill-scan.sh --accept --installed
```

One file per skill under `$SKILL_SCAN_BASELINE_DIR` (default
`~/.claude/skillspector-baselines`), not one merged file: fingerprints are
content hashes scoped to a path relative to the skill root, so merging lets an
accepted finding in one skill suppress an identical-looking one in another.

**Read the findings before accepting them.** `--accept` is how a real
vulnerability gets permanently silenced.

## How noisy, concretely

First run against the 67 skills installed on this machine, all from Anthropic's
official marketplaces: **407 findings — 1 CRITICAL, 99 HIGH.** Triaging a sample
of them:

| Reported | Actually |
| --- | --- |
| CRITICAL: `pillow==10.0.0`, 10 CVEs incl. RCE | `requirements.txt` says `pillow>=10.0.0` — a floor, read as a pin |
| Env variable harvesting | `os.environ["GITHUB_TOKEN"]` in a documentation example |
| Env variable harvesting | `os.environ.copy()`, the standard subprocess idiom |
| Hidden instructions in a `.xsd` | a byte-order mark (U+FEFF) |
| Prompt injection in `receipts` | the paragraph *defending against* prompt injection |
| `subprocess.Popen(shell=True)` | real, and worth knowing |
| `&& sudo`, `--noconfirm` | real, in a skill whose job is installing things |

Zero confirmed vulnerabilities in what was installed. So the value is not the
audit — it is the gate on what gets installed next, and the baseline that makes
a new finding stand out instead of drowning in 407 old ones.

## CI

`.github/workflows/skillspector.yml` runs `--repo` on every PR. The repo has no
`SKILL.md` today, so it passes trivially; it exists so the first one to land is
scanned before it merges. Baselines for repo skills go in `.skillspector/baselines/`
and are reviewed like any other change.

Note that on a `pull_request` event the workflow runs the PR's copy of this
script. That is inherent to running any repo tooling on PR code, and the job has
a read-only token and no secrets — but do not treat a green check on an untrusted
PR as proof the skill in it is safe. Read the diff.

## MCP

`.mcp.json` registers SkillSpector as a project-scoped MCP server exposing a
single `scan_skill` tool, so an agent session can vet a skill without shelling
out. It needs the `[mcp]` extra from the install line above.
