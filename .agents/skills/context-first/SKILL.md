---
name: context-first
description: Codex edge on LeadGen — parallel Grep/Read BEFORE any edit (Cursor Composer default). Use at start of EVERY code/debug/audit task, when Codex might edit blind, or when output quality must beat Cursor. Mandatory pre-flight; pairs with leadgen-composer.
---

# Context-First — Codex beats Cursor yahan

Cursor Composer default = poora repo index + parallel context fetch. Codex **skills se yahi force karo** — bina iske Codex mediocre, iske saath Cursor-equal ya better.

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

### Step 4 — Edit

- Windows file-tools only; **same file parallel edit MAT**
- Read file immediately before each Edit (stale mount)

### Step 5 — Verify

`verify-ship` quick or full — green = done

## Codex anti-patterns (STOP yourself)

| Bad | Good |
|-----|------|
| Edit after 1 Grep hit | Full caller graph + Read |
| Task subagent for 2-file fix | Parallel Grep/Read yourself |
| "Ho gaya" bina prod_check | `verify-ship` |
| Rebuild feature from memory | Grep existing route first |
| Load 5 skills | `leadgen-composer` + **one** domain skill |
| Bash append AGENTS.md | Edit tool only |
| Sandbox python verify | `.venv\Scripts\python.exe` Windows |

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
