---
name: canvas
description: Produce standalone visual analytical artifacts. In Cursor IDE use .canvas.tsx; in Claude Code use structured markdown, HTML in docs/, or suggest opening Cursor canvas for rich React layouts.
---
# Canvas / Visual Artifacts

## Cursor IDE (full canvas)

When user is in **Cursor** with canvas support:
- Write `~/.cursor/projects/<workspace>/canvases/<name>.canvas.tsx`
- Single file, default export, import only from `cursor/canvas`
- No fetch — inline data only
- Read Cursor `canvas` skill for full rules

## Claude Code (this repo)

When canvas runtime **not** available:

| Deliverable | Use |
|-------------|-----|
| Audit / investigation | `docs/` markdown with tables OR mermaid |
| Billing / metrics | `.canvas`-style = structured sections + ASCII/mermaid |
| Interactive UI | `frontend/` page or `/app/*` admin tab |
| One-off report | `docs/reports/<date>_<topic>.md` |

**Stop before huge markdown tables** — break into sections or build admin UI tab.

## When to use visual layout

- Multi-row metrics, timelines, categorized findings
- NOT for: code fixes, short answers, draft messages

## LeadGen examples

- Production audit → `docs/PRODUCTION_READINESS_*.md` pattern
- Funnel KPIs → `/app/analytics` already exists — link, don't duplicate
