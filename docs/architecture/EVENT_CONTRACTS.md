# EVENT CONTRACTS — the shared "bhasha" of the ₹1 Cr strategy

> **Owner:** M1/M4/M5 (see `deliverables/software-company/crore-strategy-ARCH-2026-09-16.md` §2 single-writer table)
> **Source of truth (code):** `app/platform/contracts.py` · **Feed store:** `app/utils/owner_feed.py`
> **Evidence labels:** PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN
> **Rule:** a claim without a label is a claim nobody may act on.

Ye doc un **paanch records** ko lock karta hai jo M1..M6 modules exchange karte hain.
Har record ka ek canonical producer hai, ek canonical consumer, aur ek `verified` + `evidence`
pair jo traceability deta hai.

---

## 0. Kyun ek hi import surface?

`app/platform/contracts.py` sab dataclasses ka **single import surface** hai. Har module
(`dev_workers.py`, `capacity_ledger.py`, `kpi_ledger.py`, `owner_notify.py`, …) isi se import
karta hai. Isse field-name drift structurally rok se aata hai. `contracts.py` **stdlib-only**
hai aur **kabhi raise nahi karta** import pe — koi DB/network/logging side-effect nahi.

> **Mirror-only rule:** `TaskRecord` aur `FeedEvent` **mirror** hain (DB/feed ke),
> naya store nahi. Canonical stores unchhe hain: execution ledger = `DurableTaskStore`
> (`data/orchestrator_ledger.db`), event feed = `data/owner_feed_events.jsonl`.

---

## 1. FeedEvent — event bus message (canonical: `app/utils/owner_feed.py`)

| Field | Type | Notes |
|---|---|---|
| `ts` | str | ISO-8601 UTC, trailing `Z` (auto-filled) |
| `source` | enum | `workbuddy,openclaw,hermes,prod,bot_fleet,guardian,workforce,telegram_egress` |
| `actor` | str | e.g. `nova` / `hermes-gui` / `bot:sales` / `agent:rohan` |
| `severity` | enum | `P0` \| `P1` \| `info` |
| `kind` | enum | `task_claimed,ack,blocked,done,incident,heartbeat` |
| `text` | str | ≤ 1000 chars, Hinglish OK |
| `evidence` | str | ≤ 500 chars — file/pid/url; `""` ⇒ treat as unverified |
| `verified` | bool | **TRUTH** — forced `False` for `source ∈ FORCE_UNVERIFIED_SOURCES` |
| `dedupe_key` | str? | optional; suppresses repeat events within tail lookback (200) |

**Enforced by `owner_feed.build_event()` (TEST-PROVEN, 24/24):** 8 required fields,
enum validation, `workforce` → force `verified=False`, never raises, tail-scan dedupe.

---

## 2. TaskRecord — execution ledger (canonical: `AutomationOrchestrator.TaskRecord`)

| Field | Type | Notes |
|---|---|---|
| `task_id` | str | `task_<8hex>` |
| `owner_bot` | str | MUST ∈ `HERMES_BOTS` (9) |
| `assigned_agent` | str | MUST ∈ `build_registry()` / `STAFF` (31) |
| `priority` | enum | `URGENT,HIGH,MEDIUM,LOW` |
| `status` | enum | `READY,RUNNING,BLOCKED,REVIEW,DONE,FAILED,DUPLICATE_SKIPPED` |
| `version` | int | CAS version (READY→RUNNING atomic bump) |
| `fencing_token` | str? | stale-writer guard (late worker return rejected) |
| `retry_count` / `max_retries` | int | DLQ path: `retry_count >= max_retries ⇒ FAILED`, `dlq_count++` |
| `idempotency_key` | str? | **`TEXT UNIQUE` in `task_records`** — real idempotency lives HERE |
| `input_payload` | dict | task args |
| `evidence` | dict? | `StructuredEvidence` — REQUIRED for DONE (Guardian gate) |
| `last_heartbeat` | float | stale > 60s ⇒ `recover_stale_running_tasks()` reaps |

**HARD rule:** idempotency is **DB-backed** (`idempotency_key TEXT UNIQUE`). A process-local
dict is a fast-path cache only — never truth. Restart ⇒ truth from DB.

---

## 3. DevWorkerRecord — execution proof (NEW: `app/platform/dev_workers.py`)

| Field | Type | Notes |
|---|---|---|
| `worker_id` | str | `dw_<task_id>` |
| `task_id` | str | FK → `TaskRecord.task_id` |
| `lease_token` | str | from `RedisGovernorAuthority` fencing token |
| `heartbeat_at` / `claimed_at` | float | epoch seconds |
| `state` | enum | `claimed` \| `running` \| `done` \| `failed` |
| `evidence` | str | REQUIRED — file/pid/url; empty ⇒ **not verified** |

**Rule:** a `dev_workers` row is written **only on real execution** (claim → run → done),
never on inference. Yehi P0 tha jo aaj `0 rows` hai.

---

## 4. KpiRecord — honesty-carrying KPI (NEW: `app/platform/kpi_ledger.py`)

| Field | Type | Notes |
|---|---|---|
| `ts` | str | ISO-8601 UTC |
| `metric` | str | `contacts_sent,paid_customers,mrr_inr,qualified_rate,tasks_done,capacity_gap,…` |
| `value` | float | the number |
| `verified` | bool | `True` ONLY if evidence observed |
| `evidence` | str | source file/query — **REQUIRED if verified** |
| `window` | enum | `1d` \| `7d` \| `30d` |
| `source` | str | `invoices.jsonl` \| `call_analytics` \| `dev_workers` \| `capacity_snapshot` \| `workforce` |

**HARD rule:** dashboards TWO series dikhate hain — `verified` aur `claimed` — **kabhi blend nahi**.
`KpiRecord.validate()` rejects `verified=True` with empty evidence (`verified_without_evidence`).
`workforce`-sourced KPIs ALWAYS `verified=False` (`source=workforce`).

---

## 5. AlertRecord — owner-facing alert (NEW: `app/utils/owner_notify.py`)

| Field | Type | Notes |
|---|---|---|
| `ts` | str | ISO-8601 UTC |
| `severity` | enum | `P0` \| `P1` \| `info` |
| `topic` | str | `payments` \| `health` \| `incidents` |
| `text` | str | ≤ 4096 (Bot API cap; truncated) |
| `evidence` | str | REQUIRED — missing ⇒ text tagged `UNVERIFIED` |
| `dedupe_key` | str | **per-hour** dedupe — owner never spammed |
| `chat_id` | str | from `config/telegram/setup_spec.yaml` — **never hardcoded** |
| `verified` | bool | mirrors source truth (workforce ⇒ False) |

---

## 6. CapacityRecord — honest bottleneck snapshot (NEW: `app/platform/capacity_ledger.py`)

| Field | Type | Notes |
|---|---|---|
| `ts` | str | ISO-8601 UTC |
| `channel` | enum | `email` \| `voice_outbound` \| `whatsapp_cold` |
| `cap_per_day` | int | email 25 (warmup) · voice `PLATFORM_DIAL_LIMIT` (100) · WhatsApp 0 |
| `contacts_week` | int | `cap_per_day × 7` |
| `compliance_blocked` | int | DND/consent/window-blocked count |
| `gap_to_target_x` | float | `required_per_week ÷ available_per_week` |
| `note` | str | e.g. `"cold WhatsApp OFF by design"` |

**Verified baseline:** total ≈ **875 contacts/week** vs required ≈ **85,000/week** ⇒ **≈ 97× gap**
(`CODE-PRESENT`). The ledger's job is to make that gap **honest and visible**, not hide it.
The ledger NEVER raises a cap.

---

## 7. Truth gate (M4 / M5)

1. `source = "workforce"` ⇒ **force `verified=False`** everywhere (feed, KPI, alert).
   Reason: `data/workforce_live_status.json` reports `active_workers=0`,
   `task_execution_verified=false`, `evidence_kind=inference_probe_only` (`CODE-PRESENT`).
2. KPI `verified` and `claimed` are **never summed / blended**.
3. `today_actions` (dashboard) derives **ONLY from real `log_event` rows** — the fabricated
   `cycle` fallback in `team.py` was removed in T01 (`CODE-PRESENT`).

---

## 8. Integration map (producer → consumer → field)

| From → To | Exact field/event | Frequency |
|---|---|---|
| M1 → M5 | `DevWorkerRecord.state` + `TaskRecord.status` → `KpiRecord(tasks_done, verified=True)` | per task |
| M1 → M4 | `FeedEvent(kind="done"/"blocked"/"incident")` → digest | per task |
| M1 → M3 | `TaskRecord(owner_bot="sales", assigned_agent="rohan")` on lead capture | per lead |
| M2 → M5 | `CapacityRecord.gap_to_target_x` → `KpiRecord(capacity_gap)` | daily |
| M2 → M4 | `FeedEvent(kind="blocked", text="channel cap hit")` | per cap event |
| M3 → M4 | `AlertRecord(severity="P0", topic="payments")` → `owner_alerts` | per payment |
| M3 → M5 | `gst_invoice.stats()` → `KpiRecord(mrr_inr, source="invoices.jsonl", verified=True)` | per invoice |
| M4 → Owner | `send_owner()` → Telegram `chat_id` (from setup_spec.yaml) | P0 immediate / else hourly |
| M5 → M4 | `"verified X / unverified Y"` digest line | hourly |
| M6 → M4 | `FeedEvent(source="prod", kind="done", text="deployed <sha>")` → `internal_admin` | per deploy |
| M6 → M5 | `/health.version == deployed sha` → `KpiRecord(prod_sha_match)` | per deploy |
