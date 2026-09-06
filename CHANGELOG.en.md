> 🌐 English changelog for denver-workflow. The Korean [CHANGELOG.md](CHANGELOG.md) is authoritative and holds the **full history**. To keep this file useful without duplicating ~1,700 lines of dense history, only the **most recent releases** are translated here; older entries live in the Korean changelog.

# Changelog (English)

## 2.23.0 — 2026-09-06

**Stop the docker anonymous-volume leak on self-hosted CI runners with a job-completed hook — integrated into the plugin as a versioned, re-runnable wiring.**
GitHub Actions `services:` containers (e.g. postgres, redis) declare VOLUMEs, and a self-hosted runner
only `docker rm`s the container (WITHOUT `-v`) at job end, leaving the anonymous volume behind — a leak
per job. Measured (2026-09): 4,652 unused anonymous volumes = 362.7GB piled up in one runner VM's
docker-in-docker, ballooning the disk image from 394G to 46G after cleanup.

- **`ci-runner/job-completed-prune.sh`**: the `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` hook. Runs
  `docker volume prune -f` after each job (dangling anonymous volumes only — a concurrent job's active
  service volume is attached to a live container and is not touched). `timeout`-guarded against a hung
  daemon; always `exit 0` (non-blocking) whether docker is absent or prune fails. Dangling-image
  reclaim is opt-in via `DW_PRUNE_IMAGES=1`.
- **`_build/dw-wire-ci-runners.py` + `make wire-ci-runners M=<VM>` / `dw.py wire-ci-runners --machine`**:
  **auto-discovers** runners by reading `WorkingDirectory=` from the VM's systemd units
  (`actions.runner.*.service`) — no project/service names hard-coded — copies the hook to
  `$HOME/.dw-runner-hooks/` (755), and idempotently upserts `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` into
  each runner's `.env` (same value → no-op, different → replace, absent → append with a guaranteed
  trailing newline). Supports `--dry-run` and `--restart-idle` (restarts only runners with no active job).
- **Why separate from `/dw-install`**: this wiring depends on `orbctl … <VM>`, a single-host external
  dependency; folding it into per-project `install-project` would fail silently on machines without the
  VM. It follows the existing "sensitive/host-specific = explicit separate target" convention of
  `plugin-scope-*` and `verifier-scope`, and aborts loudly (exit 2) when orbctl/the VM is unavailable.
- **When it arms**: a runner reads `.env` only at service start, so setting `.env` takes effect on the
  next runner restart (`--restart-idle` arms idle runners immediately — it never kills a running job).

## 2.22.1 — 2026-09-05

**`--post-merge-hook` follow-up: warn when a missing local graph makes the installed hook a silent no-op.**
`detect()` falls back to the vault graph when a repo has no local `graphify-out/graph.json`. Installing `--post-merge-hook` in that state prints "hook installed" (green), but the installed hook's `[ -f graph.json ]` guard keeps it a **no-op until a local graph exists** — a coverage-zero shape where "install green" is misread as "working" (noted as a known follow-up in the 2.22.0 PR). The installer now prints a warning right after install when no local graph is present: the hook is inert until `graphify update <repo>` builds a local graph.

## 2.22.0 — 2026-09-05

**graphify graphs go stale because updates are on-demand — opt-in `dw-graphify-register.py --post-merge-hook` installs a git post-merge hook.**
Nothing enforces when `graphify update` runs (no watch, git hook, cron, or launchd), so graphs quietly rot. Measured (2026-09-05): one workspace's 3 repos + vault were ~2 months stale (Jul 18–Aug 9). The "graph first" query discipline is only accurate when the graph is fresh.

### Why `dw-graphify-register.py` (not `wire-hook.py`)

`wire-hook.py` / `hooks.json` wire **Claude Code lifecycle hooks** (PostToolUse etc., settings.json) — a different mechanism from git hooks, so putting it there crosses layers. The home for graphify integration is the existing `dw-graphify-register.py` (the opt-in step that registers `.mcp.json` and gitignores `graphify-out/`); the post-merge hook is part of "set graphify up for this repo," so it lives there.

### Design (safe defaults for a generic tool)

- **Opt-in flag** `--post-merge-hook`, mirroring `--graphifyignore`. `--apply` alone only prints a suggestion (never auto-enables).
- **Standalone path**: `--post-merge-hook` **without** `--apply` skips `.mcp.json` registration and installs only the hook. Repos using a workspace-level graphify (single `.mcp.json` + `project_path` routing) don't need per-repo MCP registration — the hook install, previously trapped inside `--apply`, was decoupled to support that topology.
- **Non-blocking**: the hook runs `graphify update` detached and returns immediately (never blocks `git pull`/`merge`), always exits 0 (a failed rebuild never breaks the merge), AST-only (no LLM / no API cost). A lock with a 60-min stale reap prevents pile-ups without permanent lockout; a `[ -f graph.json ]` guard makes graph-less clones/worktrees a no-op.
- **Idempotency marker** (`dw-graphify post-merge hook`): our hook is updated on re-run; a **foreign post-merge hook is left untouched with a warning**.
- 🔴 **dead `core.hooksPath` trap**: a repo migrated from another machine can point `core.hooksPath` at a non-existent absolute path, disabling all git hooks (measured 2026-09-05: two migrated repos were exactly in this state). The generic tool does **not** unset another repo's config — it warns and prints the fix command, then skips.

## 2.21.0 — 2026-08-30

**New `/dw-metrics` — a Measure/Evidence layer that turns repository history into reproducible Engineering Evidence.**
It **observes** how software is actually built, reviewed, and delivered. It is separate from and orthogonal to telemetry that measures denver-workflow's own usage. It is not meant to inflate outcomes or prove causation.

### Evidence first, interpretation second

Deterministic computation produces the raw evidence (`raw/`) and the aggregates (`metrics.json`, `REPORT.md`) **first**; LLM interpretation (**FACT / INFERENCE / UNKNOWN**) happens only **afterward**, reading those artifacts — the LLM never guesses numbers or interprets git history from memory. Correlation is not stated as causation; CI/deploy failures are not read as production defects/incidents, and reverts are not read as outages (a hotfix is classified as a corrective change). Production incidents, user impact, and actual outages cannot be determined from git/GitHub history alone, so they are not inferred (UNKNOWN).

### A behavior-preserving port of a proven tool

An externally proven engineering-metrics tool (`extract.sh` + `analyze.py`) was **ported to stdlib Python in a behavior-preserving way**, to honor the plugin's SSOT of **python3-only, no make/bash dependency, Windows portability** (rather than shipping bash into the plugin). The extraction semantics, the raw-evidence schema, and the aggregation semantics were left unchanged, and the original `extract.sh` was used as an **oracle for regression** — deterministic git files byte-identical, metrics matching, and the baseline reproduced exactly (2,413 commits · 1,321/1,292 PRs · deploy 1,791 · revert 40 · hotfix 6 · Claude 88%).

### Behavior

- Auto-detects the current repository (GitHub remote → `owner/repo`, `origin/HEAD` → default ref). When `gh` is missing or unauthenticated it degrades gracefully to **Git-only mode** — all git-based metrics (commits, PR discipline, classification, size, revert, growth, AI traces) are still produced; with `gh` available, deploy/CI/PR status is added (**GitHub-enhanced mode**).
- Output goes to the target repo's `.claude/dw-metrics/{raw/, metrics.json, REPORT.md}`. Because `.claude/` is gitignored, it **does not pollute the repository**, and every number can be recomputed from `raw/`.
- Usage: `/dw-metrics [--phases d1,d2] [--json] [--no-github] [-p path]`. See `docs/dw-metrics-example.md` for sample output.

### Added / changed

- New: `_build/dw-metrics.py` (detect → extract → analyze → report; stdlib only), `commands/dw-metrics.md`, `docs/dw-metrics-example.md`.
- Changed: `_build/dw.py` (`metrics` subcommand), `_build/dw-selftest.py` (`MetricsTest`, 7 cases), `README.md`.
- No new external Python dependencies. Existing governance/deploy/review/hooks behavior unchanged; backward-compatible (purely additive).

### Known limitation (follow-up candidate)

The concept-emergence keyword search in `raw/evolution.txt` uses `git --grep` in its default (BRE) mode, so `|` is treated literally rather than as alternation (only single-token keywords match). This is left unfixed in this release to preserve the oracle's behavior.

## 2.20.2 — 2026-08-15

**`dw-verifier-scope` had a silent fail-open — it landed "cannot determine" as "no verification needed".**
This tool's calling contract is *"dispatch only, never skip"* (dispatch-discipline), so wrongly emptying the change set results in a **merge without review**. Its polarity was broken in the dangerous direction. (issue 25)

### Why it was the default path, not an exception

Do-ers are disciplined to **always work in an isolated worktree** (dispatch-discipline). But passing the main checkout via `--repo` meant the changes weren't in that tree, yielding "0 changes → docs/config only → skip everything." **The more the discipline was followed, the more the gate turned itself off.** Two sessions independently hit this trap; one received "all verifiers skipped" for a 14-file frontend change. What filtered it out wasn't the tool — one side happened to know the base gap separately, the other had been burned before. **A tool that's only safe for people who've been burned is not a safe tool.**

### The four fail-opens that were closed

1. **(A) Swallowed exceptions** — `except Exception: return []`. A base typo, timeout, or not-a-repo all landed as "no verification needed." Now promoted to rc=-1 plus a reason string, handled as **cannot-determine**.
2. **(B) Unchecked `returncode`** — `git diff <base>...HEAD` failing merely produced empty stdout, so it proceeded. **A silent failure became a silent skip.** Now every git call's rc is checked.
3. **(C) Not distinguishing "0 changes" from "cannot determine"** — there's rarely a reason to call this script with zero changes. Empty sets, an unresolvable base, unrelated history, and **HEAD behind base** are now all treated as cannot-determine.
4. **(D) Not collecting staged/untracked** — the old collection only saw the commit range plus unstaged. The worktree-create → new file → `git add` → pre-commit gate call is exactly that state. A partial case (one unstaged `.md` + **10 staged code files**) had a non-empty set, was confirmed "determinable," and produced "1 change (0 code) → skip everything" — the quietest path, bypassing even (C)'s safety net.

---

*Older releases (2.20.1 and earlier) are documented in the Korean [CHANGELOG.md](CHANGELOG.md).*
