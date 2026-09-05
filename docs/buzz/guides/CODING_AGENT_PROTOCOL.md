---
title: "Coding Agent Coordination Protocol — Cursor / Claude / OpenCode / Monkey Code"
tags: [buzz, build, cursor, claude, opencode, monkeycode, locks]
status: active
created: 2026-08-05
---

# Coding Agent Coordination Protocol

Home channel: **`#build`**. Plane: developer tooling only — not runtime STAFF,
not a prod control surface.

## Why this exists

The repo working tree is chronically dirty and more than one tool edits it at the
same time. Two failures already happened this way: parallel multi-file edits on
the same file caused truncation, and a `git add -A` swept another tool's
in-progress work into a commit. Locks are cheap; those failures were not.

## Identity

Every message in `#build` starts with a prefix. No prefix = untraceable = ignored.

| Prefix | Tool | Typical job |
|--------|------|-------------|
| `[CURSOR]` | Cursor | IDE-side edits, refactors, inline fixes |
| `[CLAUDE]` | Claude Code / Cowork | Multi-file changes, audits, loop-engineer runs |
| `[CODEX]` | Codex | Independent review of a Claude-authored diff; scripted patches |
| `[GOOSE]` | Goose | Block's harness; spikes and one-off automation |
| `[OPENCODE]` | OpenCode | Terminal-driven patches, scripted edits |
| `[FREEBUFF]` | Freebuff | Desktop-app sessions (Electron; no headless mode) |
| `[MONKEY]` | Monkey Code | Experiments, throwaway spikes |

`[CODEX]` here is the **keyboard-side** Codex CLI. The Buzz *agent* Comb also runs
on Codex (via `codex-acp`) and uses the same prefix and the same locks — one
identity per harness, so a `#build` line reads the same whoever drove it.

Freebuff and OpenCode cannot be Buzz agents: Freebuff is an Electron app and
OpenCode has no binary on PATH. The prefix plus the handoff format below is their
complete integration, not a placeholder for one.

## Claim-before-edit

1. **CLAIM** before touching any file:
   ```
   [CLAUDE] CLAIM app/api/growth_revenue.py, tests/test_billing_truth_2026.py
   reason: ADR-159 canary
   ```
2. **RELEASE** the moment you stop:
   ```
   [CLAUDE] RELEASE app/api/growth_revenue.py — 3 tests green, exit 0
   ```
3. File already claimed? Do **not** edit it. Post
   `[TOOL] BLOCKED ON <file> (held by <tool>)` and take different work.
4. Claim older than **4 hours** is stale. Anyone may post
   `[TOOL] STALE-BREAK <file>` and take it.
5. Machine-readable mirror lives at `docs/coordination/LOCKS.json` in the repo.
   Chat is for humans; the JSON is for tools. Keep them in sync.

## Handoff format

```
[TOOL] HANDOFF -> <next tool>
Goal:      <one line>
Done:      <what actually landed>
Evidence:  <exit codes / pytest / /health.version>
Left:      <precise next step>
Touched:   <file list>
```

A handoff without an Evidence line is not a handoff. It is a rumour.

## Shared rules (all four tools)

- **Read before Edit.** Never edit off stale content.
- **Context-grep first** — callers, routes, tests — before changing anything.
- **Never `git add -A`.** Stage explicit paths only.
- **No commit / push / deploy** unless the owner asks. Deploy is
  `scripts/deploy_vps.sh` with `APP_VERSION=<sha>`; nothing else.
- **Duplicate-route grep** across all split routers before adding a route.
  FastAPI is first-route-wins.
- **Evidence beats prose.** Exit code, or it did not happen.
- **Secrets never in a message.** Env var NAMES fine, values never.
- **Swara / voice path is FROZEN.** Propose, do not edit.
- **Compliance gates are RED** (see `AUTONOMY_POLICY.md`). Weakening one is an
  abort, not a fix.
- Scratch files get cleaned up before any commit.

## Relationship to the other planes

```
#build     ->  coding tools working the repo checkout
#dev       ->  reviewed changes, PRs, test results worth owner attention
#admin     ->  Boss routing and owner decisions
#staff-pulse -> the 31 runtime STAFF, read-only
```

A coding tool never posts a command for a runtime STAFF agent. If repo work
implies a STAFF action, raise it in `#dev`, and Boss routes it from `#admin`.
