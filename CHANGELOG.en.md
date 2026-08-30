> 🌐 English changelog for denver-workflow. The Korean [CHANGELOG.md](CHANGELOG.md) is authoritative and holds the **full history**. To keep this file useful without duplicating ~1,700 lines of dense history, only the **most recent releases** are translated here; older entries live in the Korean changelog.

# Changelog (English)

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
