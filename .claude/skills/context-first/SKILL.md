---
name: context-first
description: Claude Code edge on LeadGen — parallel Grep/Read BEFORE any edit (Cursor Composer default). Use at start of EVERY code/debug/audit task, when Claude might edit blind, or when output quality must beat Cursor. Mandatory pre-flight; pairs with leadgen-composer.
---

# Context-First — Claude beats Cursor yahan

Cursor Composer default = poora repo index + parallel context fetch. Claude **skills se yahi force karo** — bina iske Claude mediocre, iske saath Cursor-equal ya better.

## Rule: ZERO edits until step 1–3 done

Har code task pe **ek hi message me parallel** (sequential mat chhodo):

### Step 1 — Locate (parallel batch)

| What | Tool |
|------|------|
| Function/class name | `Grep` definition + callers |
| New API route | `duplicate-route-guard` grep lists |
| Marketing feature | `Grep '@router' app/api/marketing*.py` |
| UI tab | `Grep` in `frontend/*.html` |
| Tests | `Glob tests/test_*<area>*` |
| Similar feature | `SemanticSearch` "how does X work" |

**Minimum:** 3–8 files identified before Read.

### Step 2 — Read FULL (parallel batch)

- Jo files edit hongi — **pura file** ya relevant section (imports + handler + neighbors)
- Snippet blind edit = #1 bug source on this repo
- `main.py` route order matters (first-route-wins)

### Step 3 — Touch-point plan (1 paragraph, user ko optional)

```
Files: [list]
Change: [minimal additive diff]
Tests: tests/test_X.py
Risks: duplicate route? billing truth? ban-safe?
```

### Step 3.5 — Risk gate

Before editing, decide the risk class:

| Risk | Required action |
|------|-----------------|
| Low | Small additive patch + targeted verify |
| Medium | Add/adjust focused test + self-review diff |
| High | Use domain skill, check auth/billing/compliance/deploy path, then verify full relevant gate |
| Unclear | Ask only if repo context cannot safely decide |

High-risk signals: auth/RBAC, billing/pricing, compliance gates, scheduler/worker loops, production deploy, data deletion, secrets, duplicate routes, public marketing copy with pricing.

### Step 3.6 — Enterprise automation gate

If change touches automation, scheduled jobs, agent loops, webhooks, integrations, billing, outbound, or production runtime, confirm all applicable items before edit:

- Flag/kill-switch exists and default behavior is safe.
- Idempotency or dedupe prevents duplicate sends, bills, calls, posts, or CRM writes.
- Timeout, bounded retry, and DLQ/fail record exist for background/provider work.
- Observability exists: event/log/metric/heartbeat and admin/operator surface when useful.
- Rollback path is clear: env toggle, container recreate, migration rollback, or data repair.
- Quota/cost fallback stays free-stack and graceful.
- Security/compliance gates remain fail-closed where required.
- Test/smoke plan covers happy path and one failure path.

### Step 4 — Edit

- Windows file-tools only; **same file parallel edit MAT**
- Read file immediately before each Edit (stale mount)

### Step 5 — Verify

`verify-ship` quick or full — green = done

### Step 6 — Evidence handoff

Final response includes:

- Files changed
- Verification command(s) and result
- Any unverified risk, with exact reason
- Next deploy/user action only if genuinely needed

## Claude anti-patterns (STOP yourself)

| Bad | Good |
|-----|------|
| Edit after 1 Grep hit | Full caller graph + Read |
| Task subagent for 2-file fix | Parallel Grep/Read yourself |
| "Ho gaya" bina prod_check | `verify-ship` |
| Rebuild feature from memory | Grep existing route first |
| Load 5 skills | `leadgen-composer` + **one** domain skill |
| Bash append CLAUDE.md | Edit tool only |
| Sandbox python verify | `.venv\Scripts\python.exe` Windows |
| AskUserQuestion as escape hatch | Execute safe default or ask one focused blocker |
| Final answer with no proof | Evidence handoff |
| Automation without ops hooks | Add flag, idempotency, retry/DLQ, metrics, rollback |

## When subagent OK

- 4+ disjoint directories, no overlap
- VPS SSH deploy (shell skill)
- Broad audit with report (explore agent)

Chhote fix = **never** subagent (token + context loss).

## Cursor parity checklist

Before claiming "done", self-check:

- [ ] Grep touch-points ≥ 3 areas (code, routes, tests/UI)
- [ ] Read before every Edit
- [ ] `prod_check.py` green
- [ ] Targeted pytest green
- [ ] No duplicate `@router` path
- [ ] Hinglish reply concise

Parent: `leadgen-composer` · Verify: `verify-ship`
