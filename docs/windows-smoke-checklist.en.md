> 🌐 English translation of [windows-smoke-checklist.md](windows-smoke-checklist.md). The Korean version is authoritative.

# Windows Smoke Checklist (5-minute verdict)

**Purpose**: When real Windows hardware becomes available, determine **within 5 minutes** whether the denver-workflow plugin is actually alive. 2.14.0 (the MCP launcher's dependency on a POSIX shell) and 2.15.0 (the slash commands' dependency on `make`) removed those dependencies **structurally**, but there has been **no verification on real hardware** (as of writing, 2026-08-08). This document fills that gap.

Guiding principle: **"It probably worked" is not evidence.** Every step has an artifact you can confirm with your own eyes.

---

## 0. Preconditions check (30 seconds)

```powershell
python3 --version      # ← If this fails, steps 1–4 all fail. Go to "Precondition A" below.
git --version
make --version         # From 2.15.0 on, this **is not required** (developers only — "Precondition B").
claude --version
```

* If `python3` does not resolve, **stop here** and resolve "Precondition A" first. `plugin.json`'s `mcpServers.command` is `"python3"`, so if the name does not resolve, the MCP will never come up.

## 1. Install the plugin (1 minute)

```powershell
claude plugin marketplace add denvernext80/Denver-Workflow
claude plugin install denver-workflow@denver-workflow
```

**Confirm**: The install path contains `_build\dw-mcp-launch.py` and **not** `_build\dw-mcp-launch.sh` (if it is present, you received a pre-2.14.0 build — `claude plugin update denver-workflow@denver-workflow`).

## 2. Start a new session (1 minute)

Launch `claude` in a new terminal. The first run triggers the venv bootstrap (creating `.venv` + installing `pyyaml` and `mcp<2`), which **may take 10–60 seconds** — do not treat a slow MCP startup as an immediate failure.

**Confirm**: `.venv\Scripts\python.exe` has appeared in the plugin root.

## 3. Confirm dw-vault tools are exposed (1 minute) — **the key gate**

Run `/mcp` in the session.

**Confirm**: `dw-vault` is **connected** and **11** tools are exposed.

```
dw_search  dw_read  dw_list  dw_resolve  dw_propose_rule
dw_write_memory  dw_write_backlog  dw_write_reference
dw_write_contract  dw_write_spec  dw_write_procedure
```

> The tool count must equal the number of `@mcp.tool()` entries in `_build/dw-mcp-server.py` (`make test`'s `test_launcher_serves_all_tools_over_stdio` checks the same thing on macOS).
> If this step fails, **the plugin is dead no matter what else happens**.

## 4. One real call (30 seconds)

Pose a question in the session that reads from the vault, so that `dw_search` actually runs. For example:

> Find and summarize tdd-iron-law in the vault.

**Confirm**: The result includes an actual note path (an empty result suggests the vault failed to resolve → "Precondition C").

## 5. Confirm hook behavior (1 minute)

Hooks are in string form, so they **go through a shell** — on Windows, Git Bash, or PowerShell when it is not installed. Both paths need to be checked.

1. **SessionStart**: When the session started in step 2, was the vault digest context injected (are project rules mentioned early in the session)? Silence may also be normal (by design there is no work when there are 0 items to ratify).
2. **PostToolUse**: Edit any project file by one line → the linter hook should run.
3. **PreToolUse**: Launch a single subagent → does the worktree guard intervene?

**Confirm**: View hook execution logs in the session with `/hooks`, and detailed diagnostics with `claude --debug`.

## 6. Slash command path (1 minute) — **the part that became a verdict target in 2.15.0**

From 2.15.0 on, the commands call a portable CLI instead of `make`. The crux is **whether it works without `make`**.

1. Whether the CLI itself comes up (outside a session, `$env:CLAUDE_PLUGIN_ROOT` is empty, so point directly at the install path):
   ```powershell
   python3 "<plugin install path>\_build\dw.py" --help
   ```
   **Confirm**: The subcommands show `build`, `dry-run`, `install-project`, `ratify`, `review`, `doctor`, `scaffold-vault`, and `plugin-scope-user|project|off`.
2. Start with a read-only command — **`/dw-review`** in the session.
   **Confirm**: The draft queue + health check appears, and the **first line** of the output is `== OBEY draft 큐`.
   (If the first line is a list of external dependencies, the output order is reversed — a pipe-buffering regression.)
3. A write command — **`/dw-install`** (no arguments = the current repository).
   **Confirm**: `<repository>\.claude\` gains `skills`, `dw-checks.json`, `agents`, and `dw-session-digest.md`, and the last line is `✓ 설치 완료:`. **Running it again yields the same result** (idempotent).
4. If all three above pass in an environment **without** `make`, that is precisely what 2.15.0 aimed for. `make` is only needed when **developing** this repo ("Precondition B").

---

## Where to look when something fails

| Symptom | Most likely cause | Where to check |
| --- | --- | --- |
| `dw-vault` is absent from `/mcp` entirely | Plugin not active / install failed | `claude plugin list`, `/dw-scope` |
| `dw-vault` is **failed** (**only the first session** right after install/update) | The cold bootstrap exceeded the MCP startup timeout. `claude plugin update` pulls a fresh clone with no `.venv`. | Open the session once more (the second reuses the venv). To warm it in advance, run `python3 _build/dw.py bootstrap` from the install root. **This is not a regression.** |
| `dw-vault` is **failed** (even in the second session) | `python3` name fails to resolve (**most common**) | The MCP stderr in `claude --debug` — if the spawn itself fails, it is a file-not-found / ENOENT-class error |
| `dw-vault` failed + `vault 없음` in stderr | The vault folder does not exist | "Precondition C" |
| `dw-vault` failed + `venv 생성 실패` in stderr | A problem with Python's `venv` module | The launcher prints the full command, exit code, and child output — read all of it |
| Fewer than 11 tools | Stale plugin version | Whether `plugin.json`'s `version` is 2.15.0 or higher |
| Tools appear but search is always empty | The vault path is elsewhere | "Precondition C" |
| Hooks do not run at all | No shell / `python3` fails to resolve | `claude --debug`, whether Git Bash is installed |
| A slash command shows `make: command not found` | Pre-2.14.0 command docs | `claude plugin update` — from 2.15.0 on, commands do not call `make` |
| Command output order appears reversed | Pipe buffering (the parent's print is pushed behind the child's) | Fixed in 2.15.0 — check the version. If it reproduces, a `_flush()` regression in `dw.py` |

### Precondition A — resolving the `python3` name

`plugin.json` has `"command": "python3"`. There is no per-platform branching key, so **there is no interpreter name that is simultaneously safe on both macOS/Linux and Windows** — all 10 of this plugin's hooks already use `python3` throughout, so we matched that.

* Microsoft Store edition of Python: provides `python3.exe` → likely to work as is.
* python.org edition of Python: provides only `python.exe` and `py.exe` → **`python3` does not resolve.** Either switch to the Store edition, or create a `python3` name in a directory on PATH.

Check: whether `where python3` points to an actual executable (if only the Store app's alias stub is found, execution may fail).

### Precondition B — `make` (**resolved in 2.15.0**)

Up through 2.14.0, 7 of the 10 slash commands invoked `make` targets. **From 2.15.0 on, the commands call the `_build/dw.py` CLI directly, so `make` is not needed.** `make` is used only when developing this repo (`make test`, `seed-check`, `update-seed`, etc. — the developer targets that were not delegated still contain POSIX pipelines like `find|wc|tr`).

Git for Windows provides `grep`, `uname`, `cp`, and shell substitution, but **not `make`** — which is why `make` was the target of the port. The handful of coreutils uses remaining in the command docs (the legacy-detection `grep -rlE`, the optional-step `--project "$(pwd)"`) are intentional remainders that Git Bash covers.

### Precondition C — vault location

The resolution order is `DW_VAULT_DIR` (env) → `vault_root` in `<project>\.claude\dw-config.json` (searched up through ancestors and the git-root repo) → `%USERPROFILE%\denver-workflow-vault` (the convention) → **error**. From 2.16.0 on, all 11 tool sites share this one order. There is no fallback after the convention — a server that came up without a vault would silently answer with empty knowledge, so it refuses to start.

The `DW_VAULT_DIR` value may use a literal `~/`, `$HOME/`, or `%USERPROFILE%\` prefix (only that prefix is expanded — a `$VAR` or `%VAR%` in the middle of the path is left untouched).

**What to watch specifically on real Windows hardware**: `%USERPROFILE%\` expansion is the part that used to rely on `os.path.expandvars`, so it **did not work at all on posix** (measured on 3.9.6 and 3.14.6 — `posixpath.expandvars` does not know `%VAR%`). 2.16.0 handles that prefix explicitly so both platforms give the same answer — verify it once with `DW_VAULT_DIR=%USERPROFILE%\denver-workflow-vault` (previously it fell back to the convention path, and only on Windows did the answer happen to coincide).

---

## What this checklist cannot determine

* **Performance and long-term stability** — outside the scope of a 5-minute smoke test.
* **The difference between the Git Bash path and the PowerShell path** — step 5 verifies only whichever one was actually used. To see both, run step 5 once more in an environment with Git Bash removed.
* **`os.execv`-related regressions** — the Windows branch spawns children via `subprocess`, so it never goes through `execv` in the first place (see the comment on `launch()` in `_build/dw-mcp-launch.py`).
* **Developer targets that go through `make`** — `make test`, `seed-check`, and `update-seed` are outside the Windows verdict scope (POSIX pipelines remain, intentionally).

The verdict is used as the basis for updating the "unverified" lists for 2.14.0 and 2.15.0 in the CHANGELOG — move an item to "verified" **only after confirming it on real hardware**.
