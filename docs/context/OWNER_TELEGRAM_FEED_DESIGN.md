# OWNER TELEGRAM FEED — current topology + design

**Coordinator:** Nova (WorkBuddy) · **Date:** 2026-09-10 13:05 IST
**Owner ask:** "desktop workers, bots, 31 agents — sab kaise chat kar rahe hain, sab owner ke
Telegram me dikhne chahiye."

---

## 1. Seedha jawab

**Aaj owner ke Telegram me agent/worker activity bilkul nahi jaati.** Telegram sirf **marketing
video publishing** ke liye wired hai. Owner ko abhi notifications **ntfy** (phone push) se milti
hain, aur worker/agent ki baat-cheet **3 alag jagah** chal rahi hai jo aapas me baat nahi karti.

| Surface | Kahin chat hoti hai | Owner Telegram me? |
|---|---|---|
| 9-bot fleet | `command_center/data/tasks.json` + `messages.jsonl` → web page `/app/bot-command-center` | ❌ Sirf web page (Telegram-**styled**, Telegram nahi) |
| 31 agents / workforce | `data/workforce_live_status.json` | ❌ |
| Desktop workers (OpenClaw / WorkBuddy / ChatGPT / Hermes / Codex) | repo `docs/context/` + Buzz relay | ❌ |
| Marketing video bot | `app/social_engine/providers.py`, `app/marketing/video_ad_cycle.py` | ✅ **haan** (sendVideo/sendMessage) |
| Ops / incidents | `scripts/send_owner_ntfy.py` + `scripts/leadgen_daily_brief.py` | ❌ ntfy pe jaata hai |

**Evidence:**
- `app/api/bot_command_center.py:3` — "Telegram-**style** chronological feed" (page hai, bot nahi).
- `app/api/social_oauth.py:136` — `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` readiness; `:10` "Telegram is NOT OAuth".
- `app/social_engine/providers.py:77` — `sendMessage` sirf social publishing me.
- `scripts/send_owner_ntfy.py`, `app/agents/lifecycle_hooks.py` — owner alerts ntfy/webhook se.
- `app/api/ops_mcp_tools.py` — Hermes Desktop ke 54 MCP tools (isliye "Telegram me dikhta hai"
  wali baat **Hermes app ke andar** sach hai, Telegram app me nahi).

---

## 2. ⚠️ Pahle ye theek karna hoga — truth gap

`data/workforce_live_status.json` (cycle 709):

```
status                  = RUNNING_24_7_PARALLEL
actions_today           = 592
active_workers          = 0      <-- koi worker verify nahi
working_members         = 0
active_members          = 0
task_execution_verified = False
evidence_kind           = inference_probe_only
desktop_apps            = hermes/claude/workbuddy/openclaw/verdant/buzz  → sab "UNVERIFIED (no desktop execution probe)"
```

**Matlab:** feed dikhata hai "24/7 chal raha hai, aaj 592 actions", par execution verify hi nahi hua.
Ise jaisa hai Telegram me bhejenge to owner ko **jhoota confidence** milega — aur ye
`AGENTS.md` §7 ke CAUSAL-CLAIM DISCIPLINE landmine ka exact case hai.

**Gate:** jo bhi source `task_execution_verified=false` ho, uski har line `UNVERIFIED` label ke
saath jayegi — ya bilkul nahi jayegi. Pehle probes, phir feed.

---

## 3. Design — 4 layers

### L1 · Egress (ek hi jagah se baat nikle)
Naya `app/utils/owner_notify.py`:
```python
def send_owner(text, *, severity="info", evidence=None, dedupe_key=None) -> bool
```
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` env se (kabhi file/const me nahi — secrets rule).
- **Fail-open**: Telegram gire to app na gire; failure queue me jaye.
- Rate-limit + dedupe (`dedupe_key` se 1 ghante me duplicate nahi).
- Har message me `evidence` field **anivarya** — bina evidence `UNVERIFIED` tag lagta hai.

### L2 · Event schema (sabki bhasha ek)
Naya append-only `data/owner_feed_events.jsonl`:
```json
{"ts":"2026-09-10T07:35:00Z","source":"workbuddy","actor":"nova",
 "severity":"P0|P1|info","kind":"task_claimed|ack|blocked|done|incident",
 "text":"...","evidence":"<file/pid/url>","verified":true}
```
Yahi wo jagah hai jahan **har** worker likhta hai — chahe wo Python ho, PowerShell ho ya koi
desktop app.

### L3 · Sources
| Source | Method | Notes |
|---|---|---|
| 9-bot fleet | **pull** `command_center/data/*.jsonl` | sabse pakka source, pehle isi ko lagao |
| Desktop workers | **push** — worker `data/owner_feed_events.jsonl` me line append kare | yehi wo channel hai jo `COORDINATION_BROADCAST.md` ne already establish kiya |
| Hermes | **push** (backend 9119 / GUI / OmniRoute health) | health sweep ka result |
| Workforce 31 agents | **pull** `data/workforce_live_status.json` | ⛔ tab tak nahi jab tak probe fix na ho (§2) |
| Prod | **pull** `https://leadsgenai.in/health` | `/health.version` = drift detector |

### L4 · Routing (spam nahi chahiye)
- **P0 / incident → turant** Telegram.
- Baqi sab → **hourly digest** (ek message).
- Quiet hours + per-source cap.
- Har digest me ek line: `verified X / unverified Y` — taaki owner ko pata rahe kya sach hai.

---

## 4. Task breakdown + ownership

| ID | Task | Owner | Gate |
|---|---|---|---|
| T-01 | `app/utils/owner_notify.py` (L1 egress) | **UNCLAIMED** | owner: `TELEGRAM_BOT_TOKEN`/`CHAT_ID` set + test chat |
| T-02 | `data/owner_feed_events.jsonl` schema + append helper (L2) | **Nova / WorkBuddy** | ✅ **DONE 13:35 IST** — `app/utils/owner_feed.py` + `tests/test_owner_feed.py`, **24/24 tests green** |
| T-03 | Bot-fleet → Telegram bridge (L3 pull #1) | **UNCLAIMED** | T-01 |
| T-04 | Worker push bridge (workers → JSONL → Telegram) | **Nova / WorkBuddy** | T-02 |
| T-05 | Workforce probe fix — `active_workers` sach me count karo (§2) | **OpenClaw** (automation domain) | pehle T-06 nahi chalega |
| T-06 | Workforce → Telegram (L3 pull #4) | **UNCLAIMED** | T-05 + verified=true |
| T-07 | Hourly digest + routing (L4) | **UNCLAIMED** | T-03 |
| T-08 | Verdant + Buzz + Claude ko roster me shamil karna | **Nova / WorkBuddy** | ✅ kar diya (roster updated) |

**Naye workers mile (pehle miss ho gaye the):** `data/workforce_live_status.json` 6 desktop apps
track karta hai — **Verdant** (abhi koi process nahi mila → DOWN) aur **Buzz** (sirf Docker infra:
buzz-postgres/redis/prometheus/keycloak/minio; Buzz agent app khud nahi mila). Roster update ho gaya.

---

## 5. Rollout order

1. **T-02** (schema) — koi risk nahi, abhi ho sakta hai.
2. **T-01** — owner se Telegram creds confirm karwake (agar set hain to bas test message).
3. **T-03** bot-fleet bridge — sabse tez dikhega.
4. **T-04** worker push.
5. **T-05 → T-06** workforce — sirf probe fix ke baad.
6. **T-07** digest.

**Abhi kuch bhi deploy/commit nahi hua.** Ye design hai; implementation owner ke go-ahead pe.

---

## 6. Coordination reconcile — 2026-09-10 13:20 IST (NEW)

While writing this design I found that **another worker edited the repo during this session**:
`HERMES_CONTROL_PLANE.md` (+27 lines) and `docs/coordination/desktop_registry.json`
(+3 app entries). That edit introduces contracts that bind this design. Verified facts:

### 6.1 Canonical ledger — this design must not become a second ledger

`docs/coordination/CENTRAL_LEDGER.md` header, verbatim:

> **CANONICAL MACHINE SOURCE:** `command_center/data/tasks.json` (+ `bots.json` + `messages.jsonl`
> + `pinned.json`) … **Do NOT create a second ledger, second Kanban, or second dashboard** — edit
> the canonical files via `scripts/council_ledger_sync.py --apply`.

Verified: `command_center/data/tasks.json` holds **44 tasks**; `grep -i telegram` returns **zero
matches** in both `tasks.json` and `CENTRAL_LEDGER.md`. So the T-01…T-08 board above is **not**
duplicating existing work, but it is **outside the canonical source**.

**Correction:** T-01…T-08 are a *coordination-local scratch board*. Before any of them starts they
must be registered into `command_center/data/tasks.json` via `council_ledger_sync.py --apply`.
The same applies to the C-01…C-12 board in `WORKER_ROSTER.md`. I will not run `--apply` without an
owner ask (it mutates canonical state).

### 6.2 Hermes owns Telegram ingress — we only build egress (CONFLICT AVOIDED)

New text in `HERMES_CONTROL_PLANE.md`:

> **Hermes owns Telegram ingress and owner replies.** Exactly one process may poll Telegram
> updates. OpenClaw, WorkBuddy, and ChatGPT/Codex must not create a second `getUpdates` consumer.

Verified: `grep -rn "getUpdates|long_pol" --include=*.py .` → **zero hits**. No poller exists today.
This design (§3) is **egress-only** (`sendMessage`), so there is **no conflict**. Recorded as a
hard constraint: **T-01 must never add a `getUpdates` consumer.**

Also verified: `owner_bot.py` (108 lines) is a **WhatsApp** text interface, not Telegram — zero
Telegram references. So "owner bot" today ≠ Telegram.

### 6.3 Registry vs auth mismatch — enrollment is structurally impossible today (BLOCKER)

`docs/coordination/desktop_registry.json` now declares `buzzlock_tool: OPENCLAW`, `WORKBUDDY`,
`CODEX` with `buzzlock_enrolled: false`. But the enrolment gate is
`app/platform/coordination_hub_auth.py:23`:

```python
_KNOWN_TOOLS = ("cursor", "claude", "monkeycode", "opencode", "bolt", "buzz", "hermes")
```

and line 169 rejects anything else: `if not _TOOL_RE.fullmatch(tid) or tid not in _KNOWN_TOOLS:`

**`openclaw`, `workbuddy`, `codex` are not in `_KNOWN_TOOLS`.** Therefore those three registry
entries can **never** reach `buzzlock_enrolled: true` — and the new contract says workers stay
`observed-not-attested` until enrolled. Net effect: the registry is currently **decorative**.

**Escalation E-02:** either extend `_KNOWN_TOOLS` (code change, owner-gated) or the three workers
remain permanently un-attested. This must be decided before T-06 (31-agent feed) — otherwise
Telegram would show workers that the system structurally refuses to trust.

### 6.4 Owner-facing status format (adopted from the new contract)

`HERMES_CONTROL_PLANE.md` now fixes this format — T-07 must emit exactly this:

```
[task_id] [owner] [worker] [state] [next action] [evidence/blocker]
```

### 6.5 Fail-closed enrolment — reinforces the §2 truth gate

> **Enrollment is fail-closed.** A desktop process being present is not a live heartbeat.

This is the same discipline as §2, stated independently by another worker. Two independent
derivations → treat as confirmed: **process-presence is not liveness.** T-05 (probe fix) is
therefore not optional polish; it is the gate for T-06.

### 6.6 T-02 shipped — 2026-09-10 13:35 IST (TEST-PROVEN)

**Delivered:** `app/utils/owner_feed.py` (stdlib-only) + `tests/test_owner_feed.py`.
**24/24 tests green** under managed Python 3.13.12 via `python -m unittest tests.test_owner_feed`
(0.314 s) — deliberately stdlib-only so it runs **without the missing repo `.venv`**.
Reuses the project's own `app/utils/file_lock.py:locked_append` (never raises), so it inherits the
existing multi-worker corruption fix rather than reinventing locking.

Public API: `emit(...)` / `append_event(event)` / `build_event(...)` / `read_events(path, limit)`.
All three write/validate paths are **exception-free by contract** and tested for it.

**The §2 truth gate is now enforced in code, not just in prose:**

```python
FORCE_UNVERIFIED_SOURCES = frozenset({"workforce"})
DEFAULT_TRUSTED_SOURCES = frozenset({"hermes", "prod", "guardian", "workbuddy", "openclaw"})
```

`build_event()` downgrades `verified=True` → `False` for any untrusted source, and unconditionally
for `workforce`. Live smoke test on the real feed path:

```
emit hermes    -> True    {"source":"hermes",    "verified":true}
emit workforce -> True    {"source":"workforce", "verified":false}   <- asked for True, got False
corrupt lines: 0
```

So even if a future worker carelessly passes `verified=True` for workforce data, the store refuses
it. **Remove `workforce` from `FORCE_UNVERIFIED_SOURCES` only after T-05 makes
`task_execution_verified` genuinely true — owner sign-off required.**

Also enforced: 8 required fields, `severity ∈ {P0,P1,info}`, `kind ∈ {6 values}`, `verified`
must be a real bool, text ≤ 1000 chars, evidence ≤ 500 chars, tail-scan dedupe by `dedupe_key`,
corrupt lines counted (never silently dropped).

**Not done:** no egress yet (T-01 still needs `TELEGRAM_BOT_TOKEN`/`CHAT_ID`).
**Nothing committed or deployed** — `app/utils/file_lock.py` verified untouched; change is additive.

### 6.7 Net effect on the plan

| Item | Change |
|---|---|
| T-01 | + constraint: egress only, no `getUpdates` |
| T-02 | **✅ DONE** — 24/24 tests green; truth gate now enforced in code (§6.6) |
| T-03…T-07 | unchanged, but must be registered in canonical `tasks.json` first |
| **NEW E-02** | `_KNOWN_TOOLS` gap → owner decision (blocker for enrolment, not for egress) |
| **NEW E-01** | Two task boards exist (mine + canonical) → mine demoted to scratch, pending sync |
