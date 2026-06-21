---
name: split-to-prs
description: Split current work into small reviewable PRs. Use when user asks to split branch, chat work, or one big diff into multiple PRs.
---
# Split to PRs

## Hard rules

- No branch/commit/push/PR until user approves split plan.
- No destructive git without explicit OK.
- Snapshot first: `git stash create "pre-split"` → `git update-ref refs/backup/pre-split-$(date +%s) $SHA`
- Stage **named files/hunks only** — no `git add .`

## Flow

1. Diff vs default branch + chat intent · CODEOWNERS boundaries.
2. Propose slices (titles + optional mermaid) · ask approval.
3. Per slice: branch from base → commit planned files → push → `gh pr create`.
4. Report URLs + leftover work.

## LeadGen tip

Billing/marketing/voice alag products → separate PRs when possible (ADR-009).
