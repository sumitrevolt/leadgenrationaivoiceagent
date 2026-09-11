# PHASE 3 — Q4/Q5 truth layer (worker identity + combo health)

**Date:** 2026-09-10 · **Author:** Nova (coordinator, Agent mode — per owner "tum hi karo")
**Evidence label:** CODE-PRESENT + TEST-PROVEN (44 tests green) · **NOT** PRODUCTION-PROVEN (nothing deployed)

---

## TL;DR

Do Owner-Command-Center questions jinhe aaj tak **koi row source hi nahi tha** — Q4 ("kaunsa
bot/agent stuck hai") aur Q5 ("kaunsa combo dead hai") — unke liye ab **honest backing source**
maujood hai. Dono abhi **unpopulated** hain, isliye tile abhi bhi "not instrumented" dikhayega —
yehi sach hai. Source banana aur data dalna alag baat hai.

Dono modules **read-side adapters** hain: maine naya prober nahi banaya, kyunki prober pehle se
maujood aur TEST-PROVEN hai. Dusra competing truth banana isi migration ka failure mode hai.

---

## 1. `dev_workers` — worker identity + liveness (Q4)

### Files

| File | Change | Evidence |
|---|---|---|
| `app/platform/worker_health.py` | **NEW** — pure stdlib-only liveness math | 22 tests green |
| `app/models/dev_worker.py` | **NEW** — `dev_workers` ORM table + async registry | AST shape tests green; `py_compile` OK |
| `alembic/versions/027_add_dev_workers.py` | **NEW** — `down_revision = 026_add_dev_task_events`, idempotent + downgrade implemented | AST contract tests green |
| `app/models/__init__.py` | +2 lines (import + `__all__`) — additive only | `grep` verified |

### Contract (architecture record §3)

heartbeat 60 s · lease TTL 600 s (lockstep with `app/dev_control/claims.py:29`) ·
degrade at 180 s (3 missed beats) · dead at 600 s (10 missed beats) · reap sweep 60 s.

### Design decisions that matter

1. **Math alag module mein kyun?** `app/dev_control/ledger_hash.py` wala pattern — is repo ka
   `.venv` aksar missing rehta hai, aur SQLAlchemy ke bina test na hone wala rule chupke se sadta
   hai. Isliye `worker_health.py` stdlib-only hai, aur `dev_worker.py` sirf persistence adapter hai.
2. **`unknown` chautha state** (healthy/degraded/dead ke alawa). Abhi register hua worker jisne pehla
   beat nahi bheja — wo **dead nahi hai**. Usko dead bolna har restart pe false alarm dega.
3. **Clock skew = alive.** Future-stamped beat ko healthy maana (age clamped to 0) — future beat
   zindagi ka saboot hai, sirf clock aage hai.
4. **Desktop rows kabhi authoritative nahi** (`is_authoritative()`), HMAC attestation tak.
5. **Counters reset nahi hote re-register pe** — crash-looping worker apni failure history chhupa
   nahi sakta.
6. **Zero secret columns** — table mein koi token/key/credential column hai hi nahi; render-safe by
   construction. `check_secrets.py` 60 files → clean.
7. **`reap_stale()` `dev_tasks` ko touch nahi karta** — lease release `app/dev_control/reconcile` ka
   kaam hai (single writer). Do writers ledger kharab kar denge.

### `snapshot()` truth gate

`instrumented=False` jab zero rows. UI ko "24×7 plane not instrumented" dikhana hai, fake green tile
nahi. `stuck` list sirf un workers ko deta hai jinke paas `current_task_id` hai **aur** health
dead/degraded hai.

---

## 2. OmniRoute combo health (Q5) — **adapter, not a prober**

### Discovery (isse plan badla)

- `scripts/omniroute_combo_watchdog.py` **pehle se maujood** hai (wrapper → real impl
  `docs/openclaw/scripts/omniroute_combo_watchdog.py`, 290 lines) aur `progress.md` ke hisaab se
  **4/4 hermetic tests green** hai.
- Ye 14 combos ko usi `/v1/responses` path se probe karta hai jo app use karta hai, aur state
  `data/omniroute_combo_state.json` mein likhta hai (gitignored).
- Schema: `{combo_id: {"fails": int, "alerted": bool, "last_ok": iso, "last_error": str}}`.
- **Lekin** `data/omniroute_combo_state.json` aaj **exist hi nahi karta** → watchdog chala hi nahi
  (ya state clean ho gaya). Isliye Q5 aaj sach mein "not instrumented" hai.

Toh maine prober **nahi** banaya. Sirf read-side adapter banaya.

### File

`app/platform/omniroute_combo_health.py` — **NEW**, stdlib-only. 20 tests green.

### 🔴 Real drift mila — aur reconcile ho gaya

**Do alag combo namespaces hain:**

| Source | IDs |
|---|---|
| `app/platform/omniroute_client.py` | `leadsgen combo 1` … `leadsgen combo 14` |
| `config/desktop_apps/combo_distribution.yaml` | `leadgen-free-first`, `hermes-engineer`, … (14) |

Ye **same 14 combos** hain — seed script friendly ids ko **aliases** declare karta hai
(`scripts/seed_omniroute_14combos.py` `COMBOS_14`). `resolve_combo()` dono namespaces ko canonical id
pe map karta hai. Ek unknown id `None` deti hai — typo silently combo 1 se attach **nahi** hoga.

### Truth rules

- State file missing → `instrumented=False`, sab `unknown`.
- State file 900 s se purana → **stale**, aur `ok` wale combos bhi `unknown` pe demote. 2 ghante
  purana "all ok" green tile nahi banega.
- Record mein `fails` key absent → `unknown`, **not ok**.

### 🐛 Bug jo test ne pakda (review ne nahi)

`classify_combo({})` pehle `ok` return karta tha — matlab "kabhi probe hua hi nahi" ko "sab theek"
samajh raha tha. Ye exactly woh fabrication hai jise rokne ke liye ye module hai. Fix: `fails` key
ka hona zaroori; absent = `unknown`.

---

## 3. ❌ Change jo maine **REJECT** kiya (evidence ke saath)

**Stale todo:** "`config/desktop_apps/combo_distribution.yaml:72,82` — openclaw + verdant
`project_only` → `vps_and_project`."

**Reject kiya.** Owner directive kehta hai desktop apps **OWNER-MANUAL ONLY** hone chahiye aur 24×7
orchestration ke liye **kabhi required nahi**. `project_only → vps_and_project` karna unhe VPS-side
routing ka hissa bana deta hai — **ultimate disha galat**. File khud kehti hai "project-only combos
are desktop-only by design".

Asli galti ye assumption hai ki combo→app ownership = combo→runtime availability. **Nahi hai** — app
`leadsgen combo N` pe route karta hai chahe kaunsi desktop app us combo ko "own" kare. Koi change
zaroori nahi.

---

## 4. Tests — kaise chalayein

```bash
python -m unittest tests.test_dev_worker_registry tests.test_omniroute_combo_health
# Ran 44 tests — OK (skipped=2)
```

`skipped=2` = `RegistryDbTests` (async SQLite round-trip) — SQLAlchemy/aiosqlite unavailable kyunki
`.venv` missing hai. **Fake pass nahi kiya**, skip kiya. `.venv` rebuild hone par ye apne aap chalenge.

Pure math + AST schema-contract tests dono stdlib hain, isliye **aaj hi** green hain.

---

## 5. Abhi kya pending hai (aur kyun)

| Item | Status | Blocker |
|---|---|---|
| Q4/Q5 tiles dikhana | source ready, **data nahi** | supervisor ko `register()` call karna hai; watchdog ko run karna hai |
| `dev_workers` rows | 0 | koi bhi abhi register nahi karta — ye **next implementation step** hai |
| Watchdog scheduling | `scripts/register_omniroute_watchdog.ps1` maujood | Task Scheduler registration = machine-local, owner-gated |
| Q8 (fleet event log) | `DevTaskEvent` Phase 2 mein | concurrent worker ke paas |
| Q9 (owner gates) | seeding chahiye | **owner-gated DB write** |
| Q10 (ranked queue) | queue khali | DevTask population |
| `omniroute_combo_health` **table** | adapter JSON file padhta hai, DB table nahi banaya | deliberate — pehle dekhte hain ki file-based kaafi hai; history chahiye to table add hoga |

### 🔴 Deployment lineage warning (baar-baar)

Production `0b848b34` local HEAD `d0183bf1` ka ancestor **nahi** hai (merge-base `79291e2b`,
HEAD +30 / prod +15). Migration 027 `026_add_dev_task_events` pe chain karta hai — jo abhi
**git mein untracked** (`??`) hai. Agar 026 commit hue bina 027 deploy hua to Alembic chain tootega.
**Deploy se pehle dono ek saath commit hone chahiye** (owner approval ke baad).

---

## 6. Collision status

Concurrent worker **abhi bhi active** tha (`app/main.py` 15:34:39, mere edits 15:33). Maine uske
kisi bhi file ko touch nahi kiya. `app/models/__init__.py` sirf 2 additive lines badla — verified
survived.

**Finding (concurrent worker ke liye):** `DevTaskEvent` `app/models/__init__.py:45` pe import to hai
par `__all__` mein **nahi** hai — `from app.models import *` use `DevTaskEvent` export nahi karega.
Unki file hai, maine fix nahi kiya.
