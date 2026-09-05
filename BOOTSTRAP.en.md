> 🌐 English translation of [BOOTSTRAP.md](BOOTSTRAP.md). The Korean version is authoritative.

# AI-Native Workflow — Design & Architecture

> This document covers the *what and why* (design and invariants); the README covers the *how* (operations and commands).

## Goal (in one sentence)

Treat this repo's **Obsidian vault as the single source of truth (SSOT)** — gathering rules, principles, memory, and contracts in one place — so that agents **read and obey** that SSOT and **write their learnings back to update it**.

## Architecture — a bidirectional, living SSOT

```
              Humans (author · ratify)
                   │
                   ▼
        ┌───────────────────  Obsidian vault (SSOT)  ───────────────────┐
        │  rules · guidance    →  [compile] → .claude/skills             │
        │                           (obey; stable only)                  │
        │  memory · contracts  →  live (not compiled)                    │  ← agents
        └───────────────┬─────────────────────────────────┬─────────────┘     read/write (draft)
                        │ /dw-install                     │ dw-vault MCP server
     project skills · checks · hooks · agents     (11 tools; LIVE→stable direct · OBEY→draft)
                        │                                 │
                        ▼                                 ▼
              target project session          ·  Claude Code (subscription)
```

- **Humans author** (mostly rules and principles). **Agents obey the compiled rules** and record and propose learnings, contracts, and rules.
- **Ratification is automatic** — LIVE content (memory/contract/spec/backlog/reference) has no gate, while OBEY content (rule/guidance/procedure) is ratified by `dw-ratify` (deterministic) plus `dw-ratifier` (LLM judgment).
- The only contract surface linking humans and machines is the **frontmatter**.
- vault = source. `.claude/skills` = build output (source → binary). **Never edit the output directly.**

## Two paths — obedience vs. learning/collaboration

| Path | Content | Flow | Compiled? |
|---|---|---|---|
| **Obedience** | `rules` · `guidance` · `procedures` | author/propose → auto-ratify → skill → agent obeys | ✅ `stable` only |
| **Learning** | `memory` | agent writes stable (no gate) (auto-capture is also funneled into the vault) | ❌ live |
| **Collaboration** | `contracts` | backend↔app agents read/write, stable · on completion `dw_resolve`→archive | ❌ live |
| **Design** | `specs` | plans, specs, designs, stable · on implementation `dw_resolve`→archive (prevents worktree volatility) | ❌ live |
| **Follow-up** | `backlog` | out-of-scope todos, stable · on completion `dw_resolve`→archive (vault instead of repo files) | ❌ live |
| **Reference** | `reference` | system-state snapshots (DB schema, API index), stable · re-extracted and replaced on drift | ❌ live |

LIVE content (memory, contract, spec, backlog, reference) is **not compiled**. Agents read and write the vault live.
Those with a completion/retirement lifecycle (contract, spec, backlog) are moved to `archive/` via `dw_resolve` to take them off the active list (memory = permanent accumulation; reference = replaced by re-extraction with no completion, so it is not a resolve target).
Since the read tools do not filter by status, the **draft↔stable distinction is meaningless for LIVE content** — which is why the MCP writes LIVE straight to stable (removing the ratification gate). `draft` carries meaning only for OBEY content (what gets compiled and enforced), where `dw-ratify` **empirically verifies** safety (running the check pattern against real code with zero false positives) before auto-promoting it.

## Absolute invariants (if any one breaks, something is wrong)

1. **Folders are for humans; frontmatter is for machine routing.** The compiler does not branch on folders — it sweeps the entire vault as `*.md` and routes solely by frontmatter (`type`/`compiles-to`/`scope`).
2. **Compilation is pure and deterministic.** Same vault → same output (sorted). Delete a note → it is deleted from the output too.
3. **A rule that cannot be verified is not a rule but a wish.** A `type:rule` must always have an `enforced-by`. `guidance` (working discipline) is not an enforced gate, so it needs no enforced-by.
4. **ADRs (`decisions/`) are never compiled.** Rules cover the "what"; ADRs the "why." Memory is not pushed down to agents.
5. **`scope` = the skill bundling/loading unit.** Notes with the same scope are merged into a single skill.
6. **`status` = the compile/enforcement gate.** Only `stable` is compiled. `draft`/`deprecated` are excluded from the output.
7. **Skills use progressive disclosure.** The description is always present; the body loads only when relevant.
8. **User/tenant data isolation is a first-class rule** — attach a verifier (`enforced-by: security-qa`). (Implementation varies by project.)
9. **Ratification is automatic; only enforced legislation is verified.** LIVE content (memory/contract/spec/backlog/reference) is written straight to stable by the MCP (reads ignore status → a gate would be meaningless). OBEY content (rule/guidance/procedure) is proposed as status:draft, and `dw-ratify` (deterministic: schema, existence of enforced-by, check pattern with zero matches in code) auto-promotes **only the safe ones** to stable. Only cases needing judgment (where the check matches existing code) are escalated to `dw-ratifier` (LLM) — no human required. **The heart of the invariant is not "human ratification" but "an enforced rule is empirically verified before it takes effect."**

## Enforcement — an active harness plus a gate layer

The gate layers (1–4) are on their own merely *advisory* — a compiled rule is ambient ("known"), hooks are feedback, and subagents are on-demand. Because they rely on cooperation, "knowing ≠ being unable to break." Real enforcement comes from the **active harness**.

The **`dw-governed` harness agent** (`agents/dw-governed.md`, `install: always`) binds the gates into an *inescapable loop*: pull rules → work → deterministic checks → verifiers → **loop until pass** → completion gate. Setting `agent: dw-governed` in the project's `settings.local.json` makes every session start under the harness (always enforced).

Gate layers:
0. **Auto-ratification** (session-start hook `dw-ratify-session.py`; the manual path is `make ratify`) — deterministically verifies OBEY drafts, then auto-promotes the safe ones to stable, compiles, and installs (across all registered repos). Only cases needing judgment are handed to `dw-ratifier` (LLM). It uses no host scheduler (the hook is platform-neutral — pure python3). At proposal time (`dw_propose_rule`) it **runs the same verification but returns only a prediction** — promotion happens outside the proposer's turn.
1. **MCP tools** (the primary path) — `dw_write_*` *constructs* the frontmatter. LIVE content (memory, contract, spec, backlog, reference) goes straight to stable, while OBEY content (rule/procedure) is proposed as draft (no status parameter → validate-by-construction). Completion/retirement is handled by `dw_resolve` moving the note to archive (distinguished by location, with no separate status).
2. **Deterministic linter** (automatic) — a PostToolUse hook inspects a rule's `check-deny`/`check-require` and feeds violations back via `additionalContext` (guiding self-correction rather than blocking).
3. **vault guard** (backstop) — checks the frontmatter contract and draft gate on raw `.md` direct writes.
4. **Subagents** (judgment) — structural rules that grep can't catch are reviewed by the `enforced-by` verifier (security-qa, etc.).

**Skill bodies are not auto-loaded (progressive disclosure, invariant 7)** — only the description is always in context, and the body (the full rule text, the accumulated-knowledge index) loads only when the skill is activated. So to make the compiled rules and knowledge reach a session, SessionStart digest injection (layer 5) is needed. `/dw-install` (`make install-project`) builds a per-project digest
(`.claude/dw-session-digest.md`: always-applied guidance + the list of enforced rules + the accumulated-knowledge index), and
`dw-session-context.py` (the SessionStart hook) **injects it directly into context at session start** —
unlike a body, additionalContext is always injected. Pull the full text via `dw_read` or the skill.

## MCP gateway — `dw-vault`

The vault is exposed as a stdio MCP server (`_build/dw-mcp-server.py`) → Claude Code (and any MCP client) accesses it through typed tools. The write tools have no status parameter (validate-by-construction):

- **Read**: `dw_search` · `dw_read` · `dw_list` (status-agnostic — searches both draft and stable)
- **Write · LIVE (straight to stable)**: `dw_write_memory` · `dw_write_backlog` · `dw_write_reference` ·
  `dw_write_contract` · `dw_write_spec`
- **Write · OBEY (propose as draft → auto-ratified by dw-ratify)**: `dw_write_procedure` · `dw_propose_rule`
- **Completion/retirement**: `dw_resolve(name)` — moves backlog, spec, or contract to `archive/` (excluding it from the active list).
  memory, decision, and reference are not targets (reference is replaced by re-extraction on drift).

Memory is **also funneled into the vault from CC auto-memory (`autoMemoryDirectory`)**, so both automatic capture and curation converge on the vault as a single SSOT (the guard and tools accept both the CC format and the vault format).

## The frontmatter contract

For the required fields per type, the check fields (`check-*`), and the routing rules, see the **"Frontmatter contract"** section in the README.
In short: `type` is the starting point for routing, a note must be `compiles-to: skill` + `status: stable` to be included in a skill, and a `rule` requires `enforced-by`.
