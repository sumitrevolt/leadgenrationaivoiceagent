---
name: memory-vault
description: Rowboat-style compounding memory — per-prospect/client/topic markdown memory, call-prep briefs, live notes. Use when the user says "memory", "prep brief", "call prep", "live note", "track topic", "prospect history", or agents need long-lived context instead of cold-start. Covers sync job, flags, API, and how to inject memory into any agent.
---

# Memory Vault (compounding memory, Rowboat-inspired)

Har entity ka LONG-LIVED markdown memory jo events se khud-ba-khud बनta hai — agents ko cold-start nahi.

## Layout
- `data/memory/prospects/<phone10>.md` · `clients/<client_id>.md` · `topics/<slug>.md`
- Structure: `# title` → `## Profile` (dedupe facts) → `## Timeline` (append bullets, >80 pe static-digest compact → last 30) → `## Summary` (LLM, sirf on-demand `regen_summary`)
- Cursor: `data/memory/_cursor.json` — sync sirf NAYI lines tail karta (inquiries / widget_chats / dialer_logs / deals jsonl).

## Rules (tooti to prod girta hai)
- **Sync job me KABHI LLM/network nahi** (qa-job + widget-chat prod-down lessons). LLM sirf `regen_summary`/`prep_brief`/live-notes me, hamesha `wait_for ≤25s`.
- **Hot-path hooks NAHI** — memory hamesha cursor-tail se banti hai, request path me kabhi mat likho.
- deals.jsonl rewrite-store hai — sirf NAYE deals tail hote, in-place stage edits nahi (documented).

## Use
- Sync: `POST /api/memory/sync` (manual) ya flag `MEMORY_VAULT=1` (scheduler content job).
- Call-prep (dialer "📋 Prep" button bhi yahi): `GET /api/memory/prep?phone=` → Hinglish brief (talking points, objections+jawab, next action). `call_prep.prep_brief()`.
- Live notes: `POST /api/memory/topics {topic, niche?, city?}` + flag `LIVE_NOTES=1` (daily refresh, trends+weather reuse, 1/topic/day).
- Kisi bhi agent me context inject: `from app.platform.memory_vault import context_snippet` → `context_snippet(phone=..., client_id=..., max_chars=1200)` (pure-sync, fast) — sales_assistant/proposal me pattern dekho (optional `phone=""` param, never-raise).
- Human edit (Rowboat principle "memory editable ho"): `PUT /api/memory/entity {kind, key, content}`.

## Naya store memory me jodna ho
`memory_vault.py` me `_STORES` list me (path, handler) add karo — handler ek line se events nikale, `_tail_new` cursor sambhalta hai. Test: `tests/test_parity_memory.py` pattern.
