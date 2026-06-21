---
name: review-bugbot
description: Bug-focused code review of local changes (Bugbot-style). Use when user asks for /review-bugbot, bug review, or pre-merge defect scan.
---
# Review Bugbot (Claude Code)

## Option A — Task subagent (Cursor parity)

Launch **one** `bugbot` subagent:
- `readonly: true`
- Prompt shape:
```text
Full Repository Path: <abs repo path>
Diff: branch changes | uncommitted changes
Change Description: <only if natural language diff>
Custom Instructions: <user extras>
```

Default `Diff: branch changes`. Don't compute diff yourself — subagent does.

## Option B — No subagent (Claude Code CLI)

1. `git diff` / `git diff main...HEAD`
2. Follow `self-code-review` + `systematic-debugging` checklists
3. Focus: logic bugs, FastAPI duplicate routes, fail-open security, voice path gaps
4. Output: Critical / Suggestion / Nice — Hinglish OK

## LeadGen hotspots

- `grep '@router'` duplicates
- Cross-path: `scripts/cross_path_audit.py`
- Billing truth: `tests/test_billing_truth_2026.py`
- Voice: `scripts/agent_tester.py` after brain changes

Retry once on subagent failure; then report blocker.
