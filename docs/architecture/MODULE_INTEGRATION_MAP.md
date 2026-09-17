# MODULE INTEGRATION MAP — the concrete "tightly synced" table

> **Owner:** cross-module (see `deliverables/software-company/crore-strategy-ARCH-2026-09-16.md` §10)
> **Companion doc:** `docs/architecture/EVENT_CONTRACTS.md` (schema field definitions)
> **Evidence labels:** PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN

"Tightly synced" ka matlab yahan **exact event/field coupling** hai — har edge ke liye
**producer → consumer → field → frequency**. Koi vague "integration" phrase nahi.

---

## 1. Coupling table

| From → To | Coupling | Exact field/event | Frequency | Label |
|---|---|---|---|---|
| M1 → M5 | Task execution metrics | `DevWorkerRecord.state` + `TaskRecord.status` → `KpiRecord(metric="tasks_done", verified=True)` | per task | CODE-PRESENT |
| M1 → M4 | Task lifecycle alerts | `FeedEvent(kind="done"/"blocked"/"incident")` → digest | per task | CODE-PRESENT |
| M1 → M3 | Funnel automation | `TaskRecord(owner_bot="sales", assigned_agent="rohan")` on lead capture | per lead | CODE-PRESENT |
| M2 → M5 | Capacity truth | `CapacityRecord.gap_to_target_x` → `KpiRecord(metric="capacity_gap")` | daily | CODE-PRESENT |
| M2 → M4 | Bottleneck alert | `FeedEvent(kind="blocked", text="channel cap hit")` | per cap event | CODE-PRESENT |
| M3 → M4 | **Payment alert** | `AlertRecord(severity="P0", topic="payments")` → `owner_alerts` | per payment | CODE-PRESENT |
| M3 → M5 | Revenue truth | `gst_invoice.stats()` → `KpiRecord(metric="mrr_inr", source="invoices.jsonl", verified=True)` | per invoice | PRODUCTION-PROVEN |
| M4 → Owner | Delivery | `send_owner()` → Telegram `chat_id` (from `setup_spec.yaml`) | P0 immediate / else hourly | CODE-PRESENT |
| M5 → M4 | Honest digest line | `"verified X / unverified Y"` in hourly digest | hourly | CODE-PRESENT |
| M6 → M4 | Deploy notice | `FeedEvent(source="prod", kind="done", text="deployed <sha>")` → `internal_admin` | per deploy | CODE-PRESENT |
| M6 → M5 | Version KPI | `/health.version == deployed sha` → `KpiRecord(metric="prod_sha_match")` | per deploy | CODE-PRESENT |

---

## 2. Sync invariants (the "tight" part)

1. **Har KPI ka ek `evidence` field hai** jo traceable source file/query batata hai.
   `KpiRecord.validate()` `verified=True` ko empty evidence ke saath reject karta hai.
2. **Har alert ka ek `dedupe_key` hai** (per-hour) — owner spam-free.
3. **`workforce` source har edge pe `verified=False`** — M1→M5, M1→M4, M2→M5 sab me
   (`owner_feed.FORCE_UNVERIFIED_SOURCES`, `contracts.FORCE_UNVERIFIED_SOURCES`).
4. **M3 ka payment confirm hi M4 ka payment alert + M5 ka revenue KPI trigger karta hai** —
   ek hi source of truth (`data/invoices.jsonl` via `gst_invoice.stats()`).
5. **M6 ka deploy completion hi M4 ka deploy notice + M5 ka `prod_sha_match` KPI trigger karta hai** —
   ek hi source of truth (`/health.version`).

---

## 3. Canonical files — DO NOT DUPLICATE

| Concern | Canonical | Never create |
|---|---|---|
| Task execution ledger | `DurableTaskStore` (`data/orchestrator_ledger.db`) | a 4th ledger |
| Coordination board | `command_center/data/tasks.json` | a 2nd board |
| Event feed | `data/owner_feed_events.jsonl` (via `owner_feed.py`) | a 2nd feed |
| Bot registry | `AutomationOrchestrator.HERMES_BOTS` (9) | a 2nd registry |
| Agent registry | `app/platform/team.py → STAFF` (31) | hand-edited registry |
| Money truth | `data/invoices.jsonl` via `gst_invoice.stats()` | `revenue_attribution.jsonl` as money |
| Deploy authority | `scripts/deploy_vps.sh` (`systemctl restart leadgen`) | a 2nd deploy script |

> **Pre-existing drift flagged (NOT created by this work):** THREE task ledgers coexist —
> `command_center/data/tasks.json` (board), `data/admin_tasks.db` (admin `task_ledger.py`),
> `data/orchestrator_ledger.db` (`DurableTaskStore`). ARCH §M1 resolves this by **purpose-split,
> not merge**. This work adds NO fourth ledger (`dev_workers` rows live INSIDE
> `orchestrator_ledger.db`, next to `task_records`).
