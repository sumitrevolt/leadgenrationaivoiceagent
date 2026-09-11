---
name: freebuff
description: "FreeBuff CLI coding agent — delegate coding tasks to freebuff (free, no subscription)."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows]
metadata:
  hermes:
    tags: [Coding-Agent, FreeBuff, CLI, Free, Coding]
    related_skills: [claude-code, codex, opencode]
---

# FreeBuff — CLI Coding Agent Worker Bot

Delegate autonomous coding tasks to [FreeBuff](https://freebuff.com) (`freebuff`), a free terminal-based AI coding agent. No subscription required.

## Prerequisites

- **Installed globally:** `npm install -g freebuff` (v0.0.173+)
- **Binary:** `freebuff` on PATH (verified at `%APPDATA%/Local/hermes/node/node_modules/freebuff/index.js`)
- **First run:** `freebuff login` to authenticate (opens browser).

## Important: FreeBuff is interactive-only

FreeBuff is a **purely interactive TUI application**. It has NO `-z` flag and NO non-interactive/print mode. Every task requires an active terminal session with PTY. Do NOT try `freebuff -z "task"` — it does not exist and the command will fail.

For one-shot non-interactive coding tasks, prefer `claude-code -p` or `codex exec` instead (see those skills).

## Launching FreeBuff from Hermes

### Interactive session (the only real mode)
```
freebuff --cwd <project-dir>
```
Launches the TUI. Must use `pty=true` in Hermes terminal calls. The session is fully interactive — send follow-up inputs via `process(action='submit', session_id=..., data='...')`.

```python
from hermes_tools import terminal

# Start interactive background session
proc = terminal("freebuff --cwd C:/path/to/repo", background=true, pty=true)
# Returns session_id for monitoring

# Send follow-up text
terminal(action='submit', session_id=proc['session_id'], data='add error handling')

# Check progress
terminal(action='poll', session_id=proc['session_id'])

# Kill when done
terminal(action='kill', session_id=proc['session_id'])
```

### Continue a previous session
```
freebuff --continue [conversation-id] --cwd <project-dir>
```
Resumes an existing conversation by ID. Requires `pty=true`.

### Login (first run only)
```
freebuff login
```
Opens browser for authentication. One-time setup.

## Models available in FreeBuff

- **Full mode** (US, CA, UK, EU, select countries): GLM 5.3 Flash (default), DeepSeek V4.1 Flash, GPT-5.6 Luna, MiMo 2.5, Solar Pro 4, Muse Spark 1.2
- **Limited mode** (elsewhere / VPN): GLM 5.3 Flash, DeepSeek V4.1 Flash, MiMo 2.5, Solar Pro 4 — 6 one-hour sessions/day, earn up to 7 via engagement
- **GLM 5.3 Flash** is always free and unmetered — the safest default

## Important notes

- FreeBuff includes built-in web research and browser use — no separate skill needed for those.
- Ads-supported model; data may be used for training per the privacy policy.
- `--cwd` controls the project directory; always set it explicitly for repo work.
- Use `--continue` to resume long-running sessions without losing context.
- Every FreeBuff invocation is interactive — there is no `-z` or print mode.

## Worker bot use cases for LeadGen

- Code refactors and bug fixes in the repo
- Test writing and execution
- Documentation updates
- CI/CD script generation
- Any routine coding task where a free, fast agent suffices
- **NOT for one-shot automation** — use claude-code `-p` or codex exec instead

## Comparison with other coding agents

| Agent | Cost | Non-interactive | Best for |
|-------|------|-----------------|----------|
| FreeBuff | Free | **No (TUI only)** | Interactive coding tasks, fast turnaround |
| Claude Code | Paid | Yes (`-p` flag) | Complex reasoning, PRs, one-shot automation |
| Codex | Paid | Yes (`exec`) | Multi-step engineering, batch work |
| OpenCode | Free | Varies | Open-source alternative |

Use FreeBuff for interactive speed and zero cost; reach for Claude/Codex when you need non-interactive automation or deeper reasoning.

## References

- **`references/cli-cmds.md`** — Verified CLI flags, invocation patterns, terminal code samples, known limitations
- **`references/install.md`** — Install steps, first-run setup, troubleshooting, where FreeBuff fits in the coding-agent stack
