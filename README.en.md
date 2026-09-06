> 🌐 English translation of [README.md](README.md). The Korean version is authoritative.

# Denver AI Workflow

**A governance system that consolidates a team's knowledge (rules, contracts, and lessons learned) into a single Vault, has Claude Code agents read it, obey it, and continuously feed back what they newly learn.** A single knowledge folder becomes the **Single Source of Truth (SSOT)** shared by both the team and the agents.

> **💡 Non-developers can use it right away.** The three steps in [🚀 Quick Start](#-quick-start-3-steps) below are all you need to get set up. Refer to the detailed sections further down whenever you need them.

---

## 📌 Overview

As a project grows, team knowledge — collaboration conventions, API contracts, incident-response history, and the like — tends to scatter across many places. Denver consolidates this knowledge into a single **Obsidian** Vault for management.

From then on, in every work session Claude Code **automatically obeys existing rules (OBEY)** and records newly learned context (LIVE) into the Vault in real time. This eliminates the need for people to manually review, copy-paste, and approve knowledge, and automates the entire pipeline — validation, compilation, and context injection.

```
               Humans (author rules & knowledge)
                         │
        Obsidian Vault (SSOT · team knowledge folder)
           ├── OBEY (rules·guidance·procedures) ── dw-ratify (auto validate·approve) → [compile] → .claude/skills
           └── LIVE (learnings·contracts·specs) ── MCP server stores in real time ◀── agents read/write
                         │                                             │ dw-vault MCP (11 tools)
                         ▼                                             ▼
 ───────────────────────────────────────────────────────────────────────────────
 At session start: a Hook auto-injects "must-follow guidance + enforced rules + knowledge index" into context
                         │
                         ▼
                target project session ◀──────▶ Claude Code (discipline enforced)
```

> ℹ️ This document is a **usage and operations guide**. For design principles and invariants, see [BOOTSTRAP.md](./BOOTSTRAP.md).

---

## 🚀 Quick Start (3 Steps)

1. **Install the plugin** — Launch Claude Code in your terminal and enter the following commands in order:
   ```bash
   claude plugin marketplace add https://github.com/denvernext80/Denver-Workflow
   claude plugin install denver-workflow@denver-workflow
   ```
2. **Initial setup** — Enter `/dw-setup` in a session. The setup assistant automatically walks you through installing the required programs (Obsidian, etc.), preparing the knowledge folder (Vault), and connecting your project (it auto-detects the project type: new, existing, or multi-repo).
3. **Start using it** — Enter `/denver-workflow`. It automatically guides you through the entire feature-development process, from requirements analysis to final deployment, in 11 stages.

> 💡 One-off tasks such as typo fixes, one-line bug fixes, and simple documentation edits skip the 11 stages and go straight to the Git flow (Branch/PR). **Apply the full cycle only when full-cycle validation is needed, such as for new feature development.**

---

## 💻 Slash Commands

| Command | Description |
| --- | --- |
| `/dw-setup` | **Initial setup assistant** — Handles installing required tools, preparing the Vault, and connecting the project in one pass |
| `/denver-workflow` | **Feature-development full cycle** — Runs the 11-stage process from requirements definition to deployment (multi-repo capable) |
| `/dw-install` | Syncs/updates the Vault's latest state (rules, checks, agent settings, digest) to the target project |
| `/dw-build` | Compiles the Vault contents and builds them into `.claude/skills` (Strict validation mode applied) |
| `/dw-ratify` | **Automatically validates and approves** rules/procedures in Draft state, building and installing them into Stable state (no human intervention required) |
| `/dw-review` | Reviews the manual-review queue for items where auto-approval was held, and runs a system health check |
| `/dw-scope` | Sets the plugin activation scope (user-global vs. current-project only) |
| `/dw-ci-review` | Installs the **(optional) GitHub PR auto-reviewer** — when a PR is created, Claude performs a branch-level code review |
| `/dw-api-spec` | **API spec inspection/update** — Checks whether the code and the vault spec have diverged (no arguments); re-sweep with `재추출` (re-extract) or `<도메인>` (<domain>) |
| `/dw-batch-spec` | **Batch/cron spec inspection/update** — Compares actually-running scheduled executions against the spec (no arguments); re-sweep with `재추출` (re-extract) or `<그룹>` (<group>) |
| `/dw-metrics` | **(Optional) Engineering Evidence measurement** — Transforms repository history into reproducible evidence (development patterns, delivery, stability) for observation (Git-only / GitHub extended) |

---

## 🔄 Feature-Development Full Cycle — `/denver-workflow`

A multi-agent workflow that carries a new feature through a safe, consistent procedure from **requirements definition to deployment**.

In a multi-repository (multi-repo) environment, it automatically analyzes the scope of change (Frontend, Backend, QA, etc.) and dispatches the work to the appropriate repository and its responsible agent (**Do-er**). When work stalls or additional review is needed, it escalates to the Advisor, a higher-tier reviewer model, for review.

* **One-time preparation stage (Stage 0):** In a multi-repo environment, an interactive interface generates a **Repo-Map** that maps repositories to their responsible agents. Configure it once, and it is thereafter used automatically in every workflow with no further setup.


### 🛠️ 5-Phase Flow (Design ➔ Dispatch/Contract ➔ Implementation ➔ Validation ➔ Deployment)

| Phase | Stage | Sub-stage | Tools (Skill / Agent) |
| --- | --- | --- | --- |
| **① Design** | 1 | Requirements analysis | `brainstorming` + ★ `advisor` |
|  | 2 | Detailed planning | `writing-plans` |
|  | 3 · 3.5 | UI/UX mockups · Design HTML | `impeccable` · `gstack` |
| **② Dispatch/Contract** 🔒 | 4 | Work distribution + Worktree isolation | per-repo `do-er` |
|  | 🔒 | **API Contract GATE** (no entry into implementation before the interface is finalized) | `contracts/` in the Vault + ★ `advisor` |
| **③ Implementation** | 5 | Implementation and running the regression-prevention guard | `subagent-driven` (sequential: contract ➔ supplier ➔ consumer) |
| **④ Validation** | 6 | PR creation + review + CI build | `gh pr create` ➔ repo CI (optional: `dw-pr-review.yml`) |
|  | 7 · 7.5 | Plan-vs-implementation sync comparison · Design QA | ★ `advisor` · `gstack` |
|  | 8 · 8.5 | Feature QA · Running the regression test suite | `gstack` ➔ full test suite of the target repo passing Green |
| **⑤ Deployment** | 9 | Merge + production deployment | Follow per-repository discipline (**merge/deploy gates require user consent**) |

> 📌 **Notation conventions**
> * ★ = `advisor` escalation point
> * 🔒 = **GATE** (absolutely no entry into the next stage before the conditions are met and passed)


### 🚨 Core Disciplines

* **Contract First:** For cross-repository work, implementation (Stage 5) can begin only once the interface contract spec is finalized in the Vault's `contracts/`. (No entry into Stage 5 without an interface definition.)
* **Sequential dispatch:** Implementation work runs sequentially based on the agreed spec, in the order **[Contract] ➔ [Supplier (Backend)] ➔ [Consumer (Frontend/App)]**. Parallel work across mutually differing directories is prohibited.
* **Two-point regression defense:** When fixing a defect in Stage 5, you must first write a failing test (RED), and before deployment (Stage 8.5) the entire test suite must pass (GREEN).
* **Completion Gate:** **You cannot arbitrarily declare completion until all validation results in the target repository's `.claude/dw-checks.json` are Green.**
* **Merge/Deploy Gate:** Changes involving database migrations, secret-key changes, infrastructure permission changes, or a risk of data loss **must go through the user's explicit approval.**

---

## 📂 Vault Knowledge Structure and Management Principles

The knowledge folder (Vault) is organized along two axes by role. **The folder classification is for the operator's readability; the compiler performs the actual agent routing based on the `type` declared in each note's top Frontmatter.** Therefore, moving a note to a different folder has no effect on the compile result.

### B — Operating System `governance/` ("how we work" | project-agnostic | compile target)

| Folder path | Purpose and description | `type` | Compile and application |
| --- | --- | --- | --- |
| `governance/_skills/` | Skill scope and manifest definitions | `skill-manifest` | ✅ |
| `governance/rules/` | **Enforced rules (law)** — the validator (`enforced-by`) field must be specified | `rule` | ✅ Stable only |
| `governance/guidance/` | Work discipline and shared principles (not a hard gate) | `guidance` | ✅ Stable only |
| `governance/procedures/` | Reusable procedures (Playbook) — supports agent auto-authoring | `procedure` | ✅ Stable only |
| `governance/agents/` | Role definitions (security/review dedicated subagents and harness) | `agent` | Installed as subagents |

### A — Project Knowledge `project/` ("what we build" | changes in real time | LIVE)

**The LIVE area is stored and searched by agents immediately, with no separate ratification gate.**

| Folder path | Purpose and description | `type` | Completion handling |
| --- | --- | --- | --- |
| `project/memory/` | Records of an agent's non-obvious learnings accumulated during work | `memory` | Permanent accumulation |
| `project/contracts/` | Interface contracts between backend ↔ app/frontend (SSOT) | `contract` | On completion: `dw_resolve` ➔ archive |
| `project/specs/` | Feature plans, specs, and architecture design documents (protected against loss) | `spec` | On completion: `dw_resolve` ➔ archive |
| `project/backlog/` | Follow-up work and to-dos (managed here instead of BACKLOG comments in code) | `backlog` | On completion: `dw_resolve` ➔ archive |
| `project/reference/` | Current system snapshot (**3 API specs**, **3 batch/cron specs**, DB schema, and other extracted data) | `reference` | Overwritten on re-extraction of the latest data (except `— change history` notes, which accumulate append-only) |
| `project/decisions/` | Architecture Decision Records (ADR) | `decision` | Append-only (accumulated) |
| `project/repo-map.md` | Multi-repo routing topology definition | `repo-map` | Auto-injected via the digest |

> ⚠️ **Cleanup and security principles**
> * `backlog` is closed by moving to the archive folder on completion, but `reference` syncs the system's current state, so it is **replaced** with the latest data with no notion of completion.
> * Data under `project/` is a private domain asset, so it is **never included** in the open-source plugin Seed distribution.

---

## 🛠️ Vault Knowledge Management Tools (MCP `dw-vault`)

Denver exposes the Vault to agents as an MCP (Model Context Protocol) server. Agents do not handle raw Markdown files directly; they read and write only through standardized **type-specific dedicated tools**. This is to prevent format contamination at the source.

| Category | Tool name | Description |
| --- | --- | --- |
| **Read** | `dw_search(query)` <br> `dw_read(name)` <br> `dw_list(type?)` | Knowledge search <br> View the raw text of a specific note <br> List knowledge by type |
| **Write · LIVE** *(applied immediately)* | `dw_write_memory` <br> `dw_write_backlog` <br> `dw_write_reference` <br> `dw_write_contract` <br> `dw_write_spec` | Record real-time agent learnings <br> Record follow-up to-dos <br> Record a system snapshot (calling with the same title auto-overwrites/replaces) <br> Record a contract (specify `signoff` [pending\|agreed] and whether `blocking`) <br> Record feature plans and design documents |
| **Write · OBEY** *(validate and propose)* | `dw_write_procedure` <br> `dw_propose_rule` | Propose procedures (Playbook) and rules <br> *(not applied immediately on write — held in `draft` state)* |
| **Resolve** | `dw_resolve(name, resolution)` | Moves completed backlog, spec, and contract notes to the `archive/` folder <br> *(Note: memory, decision, and reference are not targets of this tool)* |

> 💡 **Automatic MCP registration** — Agent tools are registered automatically in every session where the plugin is active, based on the settings defined in plugin.json. There is therefore no need to run claude mcp add manually per user. Tools load at session start, so after updating the plugin, please start a new session.

---

## 🌟 Optional Extensions

### 1. GitHub Actions-integrated Claude PR reviewer (`/dw-ci-review`)

When a Pull Request is created or updated, GitHub Actions runs automatically and **Claude checks out the latest state of the PR branch to perform a precise code review**.

* It leaves file-level inline comments and provides a final summary (Pass/Fail verdict).
* On a Fail verdict, the CI check fails, so combined with a Branch Protection Rule it can forcibly block merging of code that does not meet the quality bar.
* It operates on a **per-repository opt-in basis**. Review criteria are not tied to a specific language and take the governance rules committed within the project (`.claude/skills`, `CLAUDE.md`, etc.) as the top-priority basis.
* **Authentication:** It uses the user's **Claude Pro/Max OAuth token** (`CLAUDE_CODE_OAUTH_TOKEN`) with no separate API billing.
* **Installation:** In a session, enter `/dw-ci-review` and follow the guidance to register the secret and commit the workflow template (`assets/gh-workflows/dw-pr-review.yml`).

### 2. Graphify semantic graph exploration (MCP)

When the external tool **graphify** — which indexes the relationships between the codebase and knowledge as a graph structure — is available, the system automatically switches to prioritize **relationship- and traversal-path-based semantic search** instead of the default string-based dw_search.

* If a graphify environment is detected during `/dw-setup`, it is automatically registered in the per-project .mcp.json. It is configured independently per project without changing global settings.
* If graphify is not installed or does not respond properly, the system automatically falls back to the existing dw_search so you can keep using the feature.

### 3. Engineering Evidence measurement (`/dw-metrics`)

Transforms repository history into **reproducible Engineering Evidence (evidence verifiable by the numbers)**. It is not a mere Git-statistics utility but a **Measure/Evidence layer** that, from Denver-Workflow's AI-native Software Engineering perspective, **observes how software is actually built, validated, and delivered**.

The core design principle is **Evidence first, interpretation second**. Deterministic computation produces the raw evidence (raw) and aggregates (metrics.json · REPORT.md) **first**, and LLM interpretation happens **only after** reading those outputs — the LLM does not guess numbers or interpret Git history from memory.

* **Purpose:** It is not telemetry that measures Denver-Workflow's own usage (that is a separate feature). It exists to **observe** what development, delivery, and stability patterns the target repository exhibits — not to inflate results or prove causation.
* **Usage:** Running `/dw-metrics` in the repository you are working in auto-detects the current repository and measures it. Optional arguments — `--phases <d1,d2>` (phase-comparison boundary dates), `--json`, `--no-github` (force Git-only), `-p <path>` (specify a different repository).
* **Prerequisites:** `git` is required. `gh` (GitHub CLI) is optional — if present and authenticated, deployment/PR/CI metrics are added.
* **Git-only vs GitHub-enhanced:** If `gh` is missing, not authenticated, or there is no remote, it operates gracefully in **Git-only mode** (all Git-based metrics — commits, PR discipline, classification, size, revert, growth, AI traces, etc. — are still produced). If `gh` works, it adds deployment-workflow runs, CI failure rate, and PR status/throughput in **GitHub-enhanced mode**.
* **Key metrics:** development duration · commits · PRs (created/merged/closed), throughput, PR size distribution, change classification, codebase growth, CI activity/failures, deployment activity, reverts, hotfixes, test activity, AI-assisted development traces, and (when boundaries are given) per-phase changes.
* **Output structure:** Under the target repository's `.claude/dw-metrics/`, it creates `raw/` (raw evidence) · `metrics.json` (deterministic aggregate) · `REPORT.md` (human-readable summary). Because `.claude/` is gitignored, it **does not pollute the repository**, and every number can be directly re-derived from `raw/`.
* **FACT / INFERENCE / UNKNOWN principle:** Interpretation distinguishes recomputable values (FACT), rule-based estimates (INFERENCE), and things unverifiable from history alone (UNKNOWN). It **does not present correlation as causation** and does not assert CI/deploy failures as production defects/incidents, or reverts as outright outages (hotfixes are classified as corrective changes). Whether a production incident, user impact, or an actual outage occurred cannot be verified from Git/GitHub history alone, so it is not estimated.
* **Limitations:** The GitHub Actions run count is a live value that increases depending on when it runs. In the keyword search for concept-occurrence tracking (`raw/evolution.txt`), because `git --grep` defaults to BRE, `|` alternation does not apply (only a single token matches — the behavior of the verified tool is preserved as-is). For example output, see `docs/dw-metrics-example.md`.

### 4. Self-hosted CI runner docker-volume reclaim hook (`make wire-ci-runners`)

Stops the **anonymous docker-volume leak** left by CI `services:` containers (postgres, redis, …) on self-hosted GitHub Actions runners, via a per-job cleanup hook. A runner only `docker rm`s the container (WITHOUT `-v`) at job end, so it leaves the anonymous volume behind and the leak accumulates every job.

* **Hook:** `ci-runner/job-completed-prune.sh` — set as the runner's `ACTIONS_RUNNER_HOOK_JOB_COMPLETED`, it runs `docker volume prune -f` after each job (dangling anonymous volumes only; a concurrent job's active service volume is attached to a live container and is safe). `timeout`-guarded against a hung daemon; always `exit 0` (non-blocking — no effect on the job result). Dangling-image reclaim is opt-in via `DW_PRUNE_IMAGES=1`.
* **Wiring:** `make wire-ci-runners` (= `dw.py wire-ci-runners`). Copies the hook to a fixed path on the runner host (755) and **idempotently** upserts `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` into each runner's `.env`. Supports `DRY=1` (inspect only) and `RESTART=1` (restart only runners with no active job).
* **Why separate from `/dw-install`:** runner-host access is a single-host external dependency; folding it into per-project install would fail silently on machines without it. It is an **explicit separate target** like `plugin-scope-*` and `verifier-scope`, and aborts loudly when the host is unreachable.
* **When it arms:** a runner reads `.env` only at service start, so setting `.env` takes effect on the **next runner restart**; `RESTART=1` arms idle runners immediately (never kills a running job). The proof of effect is the hook output in a subsequent job's "Complete job" log.

---

## 🔒 Governance Harness

So that it does not remain mere advisory guidance, Denver enforces execution by binding the following protection layers into a deterministic loop through the **`dw-governed` harness agent**. Adding the `"agent": "dw-governed"` setting to the project's `settings.local.json` starts every session under the harness's control.

* **Session digest injection (SessionStart Hook):** The instant a session starts, it injects into the agent's context a Digest context containing always-on compliance guidance, enforced rules, and the knowledge index (marked with `🔒`). This is the key path for delivering the actual rules in a Claude Code environment where skill bodies are not auto-loaded.
* **Auto-ratification loop (`dw-ratify`):** Proposed rules and procedures (`draft`) are automatically checked by a deterministic validation script (schema match, whether the validator actually exists, etc.), and — for items with no false positives — are automatically promoted to `stable` state, compiled, and installed. Only cases requiring manual judgment are handed off to the LLM validator (`dw-ratifier`) queue.
* **Deterministic linter (PostToolUse Hook):** It checks in real time for static rule-violation patterns (`check-deny`/`check-require`) declared in knowledge notes, and when a violation occurs it gives the agent immediate feedback and prompts self-correction.
* **Worktree contamination-prevention guard (PreToolUse Hook):** It detects and immediately blocks subagent-spawn attempts that would directly modify files in a shared checkout environment without change-scope isolation (Worktree), and seeks user consent (`ask`).
* **False-positive prevention:** All static checks limit their targets to the specified file formats via `check-glob`, and exclude build artifacts, canonical test files, and the like from checks via `check-exclude`.
* **Batch/cron spec harness:** It keeps regularly-executed jobs (batch/cron) in the vault's `project/reference/` as **current state + change history**. On the first `/dw-setup`, it sweeps the entire surface of CI schedules, timer units, scheduled jobs, app schedulers, and cron install scripts. **Unlike APIs, the source of truth also lives outside the repo (host cron)**, so it counts repo-declared and host-installed jobs separately and leaves any host it could not verify as `unverified (last-checked date · reason)` — it does not assume none exist. If a host-installed job differs from the spec, it **does not adjust it arbitrarily but obtains the user's judgment** (preventing an unauthorized change from silently becoming the source of truth). Disabled jobs also remain with an `inactive` state and a reason, so it can answer "why is this turned off?" Inspection is via `/dw-batch-spec`.
* **API spec harness:** It keeps all of the project's APIs in the vault's `project/reference/` as **current state + change history**. On the first `/dw-setup`, it sweeps all existing APIs to build the 3 specs (full index · per-domain detail · change history), and thereafter API work **begins by reading the index and ends with updating the spec**. The read discipline is always injected in full into the session digest (`api-spec-first`), and a missing update is blocked in PR review (`api-spec-sync-required`, enforced-by `code-review`). Whether the spec has drifted from the code can be inspected anytime via `/dw-api-spec`. **Even deleted endpoints remain permanently in the change history**, so it can answer "why did this API disappear?"

---

## ⚙️ Setup and Operations Guide (Ops)

### 1. Installed Components

This repository itself has a plugin structure (`.claude-plugin/plugin.json`, `hooks/`, `commands/`). Activating the plugin installs the following components in one pass.

* **MCP server (`dw-vault`)** + **governance harness and validator agents**
* **Runtime hook system** (linter, artifact guard, Worktree protection guard, session-knowledge injection hook, etc.)
* **Slash command set**

> ⚠️ Project-specific skills, check rules, and the session digest file must be built and deployed separately from the plugin installation by running the **`/dw-install`** command (or `make install-project`). The plugin is the common "engine," while per-project compile artifacts are managed independently.

### 2. Vault Location Control and Priority

Knowledge data (Vault) is stored in the user's **independent local folder**, not inside the plugin code. People edit it with Obsidian, and agents access it through the MCP server.

* **Path resolution priority (identical across all tools since 2.16.0):** Environment variable `DW_VAULT_DIR` ➔ `vault_root` in the project-installed `<project>/.claude/dw-config.json` (searches up to the parent folder and the git-main repository — worktree-aware) ➔ the default convention path (`~/denver-workflow-vault`) ➔ if still not found, it returns an error and server startup halts.
  * If an earlier-priority entry points to a **nonexistent folder**, it does not give up silently but tries the next priority.
  * The value may use the literal `~/`, `$HOME/`, or `%USERPROFILE%\` **prefixes** (only that prefix is expanded — a `$variable` in the middle of the path is left as-is).
  * **If different sources point to different vaults**, a warning appears in the session-start notice and the health check (`/dw-review`). There must be exactly one vault, and silently choosing one would let a state pointing at two locations pass without error.
* To use a custom location, declare the terminal environment variable before launching Claude Code:
  ```bash
  export DW_VAULT_DIR="$HOME/My Vaults/denver"
  ```

### 3. Advisor Model Selection (Claude Opus recommended)

This is the model used for Advisor escalation, invoked when the 11-stage workflow hits a technical stalemate or needs a strong review.

* Enter the `/advisor opus` command in the session window, or apply the following setting in `~/.claude/settings.json`:
  ```json
  { "advisorModel": "claude-opus-4-8" }
  ```
* *(Note: an Anthropic API Key is required, and Claude Code v2.1.98 or later.)*

### 4. Managing External Dependencies

Denver contains only its own governance core and harness engine. The powerful external plugins/skills that agents come to invoke during the development workflow must be installed by the user in their own environment. If a tool is invoked while uninstalled, the system surfaces a self-healing installation guidance message on its own.

| Dependency | Purpose | Installation |
| --- | --- | --- |
| **Obsidian** *(required)* | IDE environment for knowledge authoring and editing | Download from the official site, or `brew install --cask obsidian` |
| **superpowers** *(recommended)* | Leads brainstorming, plan writing, and TDD implementation | `claude plugin install superpowers@claude-plugins-official` |
| **impeccable** *(optional)* | Expert critique of frontend UI/UX | `claude plugin install impeccable@impeccable` |
| **gstack** *(recommended)* | Design-mockup implementation, browsing, comprehensive design QA | After `git clone`, run the bundled `./setup` targeting the skills directory |

### 5. Platform — Windows Assumptions and Unverified Scope

> **⚠️ We do not claim "Windows support."** What was done in 2.14.0–2.15.0 goes only as far as **removing the POSIX shell and `make`
> dependencies (structurally)**. **We were unable to verify on real Windows hardware** (this repo has no CI workflow,
> and this account cannot use GitHub-hosted runners). Once real hardware is available,
> use [docs/windows-smoke-checklist.md](docs/windows-smoke-checklist.md) to make a determination within 5 minutes.

**What changed.**

* **2.14.0 — MCP launcher.** The `dw-vault` launcher changed from a `#!/bin/sh` script to pure Python
  (`_build/dw-mcp-launch.py`). Since `plugin.json`'s `mcpServers.command` is **spawned directly without going through a shell**,
  the previous wiring meant the launcher itself would not run in an environment lacking a POSIX shell,
  and as a result **all 11 dw-vault MCP tools failed to start** (the plugin's core stopped).
* **2.15.0 — the slash commands' `make` dependency.** 7 of the 10 commands called `make` targets.
  They now all invoke the portable CLI (`_build/dw.py`) directly —
  `python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" <subcommand>`.
  `make` **still works as a developer interface**, thinly delegating to the same CLI (one implementation).

> **Why `make` and not `grep`·`uname`·`cp`.** Git for Windows (Git Bash) provides `grep`·`uname`·
> `cp` and shell substitution, but **does not provide `make`.** So the target of the porting work is `make`, and
> the handful of coreutils uses remaining in the command docs (such as `grep -rlE` for legacy detection) are intentional remnants.

**Prerequisites needed on Windows (if unmet, it fails loudly rather than silently).**

| Prerequisite | Why it's needed | Verify / resolve |
| --- | --- | --- |
| **The name `python3` resolves on PATH** | The MCP wiring (`"command": "python3"`), 10 hooks, and the slash commands all call `python3`. There is no per-platform branching key, so an interpreter name that is safe on both sides simultaneously **does not exist** — it was unified to `python3`, which many already used. | `python3 --version` in the terminal. The Microsoft Store edition of Python provides `python3.exe`, but **the python.org edition provides only `python.exe`·`py.exe`** (in which case `python3` does not resolve and MCP and the commands all die). Use the Store edition or create a `python3` name on PATH. |
| **Python's `venv` module** | On first run, the launcher/CLI creates `<plugin root>/.venv` and installs `pyyaml`·`mcp` (pins live in one place, `DEPS` in `_build/dw_runtime.py`). | On failure it prints the cause, command, and full child output to stderr and dies (no silent failure). |
| ~~**`make`**~~ | **Not needed for the slash commands since 2.15.0.** `make` is used only when developing this repo (`make test`·`seed-check`·`update-seed`, etc.). | — |

**The hooks (10 wirings · 9 scripts) kept their string form** — reviewed and left unchanged. The rationale is
in the CHANGELOG 2.14.0 entry.

---

## 💻 Key CLI Commands

**Two interfaces use the same code.** The logic's source of truth is `_build/dw.py` (the portable CLI), and `make` thinly
delegates to it — a structure where `make X` and `/dw-X` cannot diverge (a self-check pins the delegation).

* **Anywhere (no make needed, the path the slash commands use)**
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" --help          # list subcommands
  python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" dry-run
  python3 "${CLAUDE_PLUGIN_ROOT}/_build/dw.py" install-project  # defaults to the current directory
  ```
  The subcommands are **1:1 identical** to the make target names below (`build`·`dry-run`·`install-project`·
  `ratify`·`review`·`doctor`·`scaffold-vault`·`plugin-scope-user|project|off`).

* **When developing this repo (macOS/Linux — `make` required)**

```bash
make build                    # Compile the Vault ➔ build into the .claude/skills directory
make dry-run                  # Validate rules and the build without modifying files (for CI; treats warnings as errors)
make test                     # Engine self-test (stdlib unittest, temp vault fixtures — the real Vault is untouched)
make doctor                   # On cold-start, fully probe venv, compiler, and MCP status
make ratify                   # Auto-ratify drafts + compile·install to every registered project (manual path)
                              #   Normally the session-start hook does the same — no scheduler (cron/launchd) registration needed
make review                   # Check the manual-review queue that needs human judgment, plus a system status check
make scaffold-vault           # Set up the default template (Generic Seed) in a new empty Vault (with overwrite protection)
make update-seed              # Back-update the shared governance-rule parts of the active Vault into the template Seed (private data auto-excluded)
make clean / make distclean   # Remove build artifacts / remove build artifacts and the local virtualenv (.venv) entirely
```

*(Note: the only external dependency packages are `pyyaml` and `mcp`, which on first run are safely and automatically installed in isolation into a project-local virtual environment (`.venv`) without polluting the system environment. For both `make` and the CLI, the bootstrap code is a single file, `_build/dw_runtime.py`, and the version pins live in that one place too.)*

> ⚠️ **If the dw-vault MCP tools do not appear in your session, run `make distclean` and rebuild.**
> `mcp` is pinned to **`<2`** (2.0.0 removed `mcp.server.fastmcp`, so the server cannot start — fixed in 2.12.0). However, that pin
> applies **only to a newly created `.venv`.** If a `.venv` created before 2.12.0 is holding `mcp` 2.0.0, it stays as-is and the server dies, so you must delete the
> virtual environment with `make distclean` and recreate it (if you installed via the plugin, delete the plugin cache's `.venv` —
> the launcher will recreate it with the pin on the next run).

### Deploying Governance to Target Projects (Multi-Repo Deployment)

```bash
# Deploy the full governance skill bundle to a target project
make install-project P=/absolute/path/to/target-project

# Deploy only specific work-domain (Scope) areas
make install-project P=/absolute/path/to/target-project SCOPES=engineering,qa
```


The `/dw-install` command reads the **Repo-Map** registered in the session digest and iterates over each multi-repo path, performing the sync automatically.
During the sync, it **preserves the target project's existing skills and agent settings as-is** and updates only the governance area managed by the Denver manifest to the latest state.
Do not directly modify the synced artifacts in the target project. If a change is needed, you must **edit the original Vault and re-run /dw-install** to reflect the change.

---

## 📝 Frontmatter Authoring Contract (Vault Authoring Rules)

The **Frontmatter (YAML metadata)** at the top of a note is the **sole Interface Contract** linking the document structure people understand with the rules the compiler interprets.

```yaml
---
type: rule
scope: backend-engineering
status: stable
compiles-to: skill
enforced-by: security-qa
check-deny:
  - "exec\\s*\\("
check-glob: "*.js,*.ts"
check-hint: "Using raw exec in production code is strictly forbidden. Use the dedicated wrapper module."
---
```

### Key Frontmatter Field Conventions

* **`type`:** The main routing key that classifies a note. (Choose from `rule`, `guidance`, `procedure`, `memory`, `contract`, `spec`, `backlog`, `reference`, `decision`, `skill-manifest`, `agent`.)
* **`scope`:** Specifies the domain the knowledge applies to, in `kebab-case`. (e.g., `api-design`, `frontend-qa`)
* **`status`:** Denotes the ratification state. (`draft`, `stable`, `deprecated`) **Only knowledge notes in `stable` state are compiled into agent skills and carry enforcement power in a real environment.**
* **`compiles-to`:** Defines whether the note is included in the agent's executable skill manifest. (Set to `skill`.)
* **`enforced-by`:** Matches the ID of the dedicated subagent that will validate the rule at runtime. (A required field for the `rule` type; if there is no corresponding agent definition under `agents/`, the compiler returns a warning/error.)
* **Static linter fields (`check-deny`, `check-require`, `check-glob`, `check-exclude`, `check-hint`):** Specify contextual regex patterns and the target file Glob scope. **(Knowledge notes that do not specify a `check-glob` field are excluded from the automatic linter's static checks.)**

---

## 🔗 Related Documentation Links

* **Denver architecture invariants and the 9 design principles** ➔ [BOOTSTRAP.md](./BOOTSTRAP.md)
* **Plugin core development and build conventions** ➔ [CLAUDE.md](./CLAUDE.md)
* **Detailed per-version release change history** ➔ [CHANGELOG.md](./CHANGELOG.md)
