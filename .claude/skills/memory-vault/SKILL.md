---
name: memory-vault
description: Rowboat-style compounding memory — per-prospect/client/topic markdown memory, call-prep briefs, live notes (memory_vault), PLUS pointer to vector agent_memory (cross-session lead recall). Use when the user says "memory", "prep brief", "call prep", "live note", "track topic", "prospect history", "agent yaad rakhe", AGENT_MEMORY/MEMORY_VAULT flags, or agents need long-lived context instead of cold-start. Covers sync job, flags, API, and how to inject memory into any agent.
---

# Memory Vault (compounding memory, Rowboat-inspired)

Har entity ka LONG-LIVED markdown memory jo events se khud-ba-khud banta hai — agents ko cold-start nahi. (`app/platform/memory_vault.py`)

> **Do alag memory systems — confuse mat karo:**
> - **memory_vault (YE skill)** = human-readable MARKDOWN per entity, cursor-tail sync se banti, `MEMORY_VAULT=1`. Dialer prep / sales context ke liye.
> - **agent_memory** (`app/voice_agent/agent_memory.py`, flag `AGENT_MEMORY`) = VECTOR (Qdrant `agent_memory` collection) semantic cross-session lead-recall, voice hot-path prompt-inject (`recall_block`/`remember`, fail-open + off-loop). Admin inspect/DPDP-purge: `/api/agent-memory/{inspect,purge,stats}` (`app/api/agent_memory_admin.py`).

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

## Enterprise gate (memory governance)

Run the operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Memory stores PII (prospect phone, deal context) → **High-risk tier** on the data-governance axis: DPDP purge path + no-secrets + dedupe before any store/handler change.

- **Safety / boundary:** `MEMORY_VAULT=1` + `AGENT_MEMORY` gated default OFF, inert-without-flag. Per-entity files keyed by `phone10`/`client_id` — kabhi cross-tenant context leak na ho (`context_snippet(..., max_chars)` bounded). Secrets/keys memory me KABHI nahi (it's git-adjacent `data/`); `scripts/check_secrets.py` clean.
- **Dedupe (built-in, don't break):** `## Profile` = dedupe facts, `## Timeline` append-only with >80 → static-digest compact to last-30. New `_STORES` handler must be idempotent via `_cursor.json` tail (only NEW lines) — re-sync 2× = no duplicate bullets. deals.jsonl = new-deals tail only (no in-place stage rewrite).
- **No hot-path / no network in sync:** sync job = pure cursor-tail, NEVER LLM/network (prod-down lesson). LLM only in `regen_summary`/`prep_brief`/live-notes, always `wait_for ≤25s`, never-raise. Memory writes never in a request path.
- **DPDP / consent (fail-CLOSED):** opt-out → consent_ledger suppression must reach memory; vector `agent_memory` purge via `POST /api/agent-memory/purge` (inspect/stats siblings); markdown entity edit/delete via `PUT /api/memory/entity` (Rowboat "editable memory"). 90-day retention honored. Purge = real delete, not soft-hide.
- **Observability:** `POST /api/memory/sync` result + `/api/agent-memory/stats`; admin inspect endpoints for audit.
- **Rollback (NAMED):** flag OFF (`MEMORY_VAULT=0`/`AGENT_MEMORY=0` = inert) · revert `_STORES` entry · delete/restore the per-entity `.md` (plain files, easy repair) · reset `_cursor.json` to re-tail. Vector store = re-embed from source.
- **Evidence (done):** `.venv\Scripts\python.exe -m pytest tests\test_parity_memory.py -q` + `scripts\prod_check.py` + a `POST /api/memory/sync` adds expected NEW lines only (no dupes) + a purge actually removes the entity. No deploy without explicit auth.
