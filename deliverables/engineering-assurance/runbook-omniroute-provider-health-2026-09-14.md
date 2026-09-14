# Runbook — OmniRoute Provider Health

**Date:** 2026-09-14
**Owner:** Ratanshila (Boss)
**Scope:** the local OmniRoute gateway (`leadgen_omniroute`) at `127.0.0.1:20128`
**Evidence labels used throughout:** `PRODUCTION-PROVEN` (observed on the live system) · `CODE-PRESENT` (read in source) · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

> **Why this runbook exists.** An audit finding published on 2026-09-14 claimed
> *"14 email accounts configured in OmniRoute"* was **FALSE**. That finding was
> **retracted**. It was derived from `~/.openclaw/workspace/omniroute_config.json` →
> `email_api_keys_created: 12`, a scalar that is (a) **outside the repo**, (b) **stale**,
> and (c) read by **zero lines of code**. The live gateway proves **14 emails** exist.
> **Rule: never assert this system's state from that JSON. Probe the API.**

---

## 1. The system in one paragraph

OmniRoute is a **local-only** LLM gateway (ADR-111 / ADR-189). It is an *optimization
lane*, **not** a 24×7 dependency — `app/voice_agent/free_ai.py` remains the real
round-the-clock path. It holds **14 combos** (`leadsgen combo 1..14`), each with **42
model slots**, fed by **294 provider connections = 14 email accounts × 21 providers**.
The app asks for a *combo*; the gateway rotates across that combo's internal slots.
`PRODUCTION-PROVEN` (live probe, 2026-09-14).

## 2. 🔴 The one trap: `isActive` ≠ usable

This is the single most important thing in this document.

| Field | What people assume | What it actually means |
|---|---|---|
| `isActive: true` | "this credential works" | **Only means the connection is *enabled*.** It says nothing about whether the credential is valid. |
| `testStatus: "active"` | — | **This is the one that means "works".** |
| `testStatus: "expired"` | — | Credential is dead. Rotation will still attempt it. |

Observed 2026-09-14: **294 / 294** connections had `isActive: true`, but only
**70 / 294** had `testStatus: "active"`. **224 silent failures.** `PRODUCTION-PROVEN`.

**Consequence:** the gateway wastes attempts on dead lanes before landing on a working
one, which is why p50 latency was **19–26 s** and why every probed combo resolved to the
same model (`nvidia/nemotron-3-super-120b-a12b`).

## 3. How to check health (exact commands)

Base URL: `http://127.0.0.1:20128` — `PRODUCTION-PROVEN`
Auth header: `Authorization: Bearer <master_api_key>`, read at runtime from
`C:/Users/Ratanshila/.openclaw/workspace/omniroute_config.json`.
**Never echo the key into a log, a file, or a chat message.**

### 3.1 Is the gateway up?

```
docker ps --filter "name=omniroute" --format "{{.Names}}\t{{.Status}}"
```
Expect `leadgen_omniroute  Up ...`. `PRODUCTION-PROVEN`

Note: `GET /health` returns **404** on this gateway. A 404 on `/health` does **not**
mean it is down. Use `docker ps`, or `GET /docs` → 200. `PRODUCTION-PROVEN`

### 3.2 Endpoint map

| Endpoint | Auth | Returns | Verified |
|---|---|---|---|
| `GET /api/combos` | required (401 without) | `{combos:[...]}` — 14 combos, 42 models each | `PRODUCTION-PROVEN` |
| `GET /api/providers` | required | `{connections:[...]}` — 294 rows | `PRODUCTION-PROVEN` |
| `GET /api/keys` | required | 200 | `PRODUCTION-PROVEN` |
| `POST /v1/responses` | required | OpenAI-style response object | `PRODUCTION-PROVEN` |
| `GET /docs` | no | 200 | `PRODUCTION-PROVEN` |
| `GET /status` | no | 200 (HTML UI) | `PRODUCTION-PROVEN` |
| `GET /health` | — | **404** — do not use as a liveness signal | `PRODUCTION-PROVEN` |
| `GET /api/emails`, `/api/accounts`, `/api/email-accounts` | — | **404 — no email concept exists in the API** | `PRODUCTION-PROVEN` |

> The "14 emails" are **not** a first-class API object. They are inferred from the
> `email` field on each of the 294 provider connections. That is why the stale `12`
> in the config file went unnoticed for so long.

### 3.3 The one health query that matters

```python
import json
from collections import Counter, defaultdict
d = json.load(open('prov.json', encoding='utf-8'))
cs = d['connections']
print('total', len(cs))
print(Counter(str(c.get('testStatus')) for c in cs))
per = defaultdict(lambda: [0, 0])
for c in cs:
    p = str(c.get('provider')); per[p][0] += 1
    if str(c.get('testStatus')) == 'active': per[p][1] += 1
for p, (t, a) in sorted(per.items(), key=lambda kv: -kv[1][1]):
    print(f'{p:<20} {a:>3}/{t:<3} working')
```

Healthy output (2026-09-14 baseline — **this is the degraded state, not a good one**):
`nvidia 14/14 · auggie 14/14 · aug 14/14 · xiaomi 14/14 · opencode 14/14`,
everything else `0/14`. `PRODUCTION-PROVEN`

### 3.4 End-to-end smoke

```
POST /v1/responses
{"model":"leadsgen combo 1",
 "input":[{"role":"user","content":"Reply with exactly: OK"}],
 "max_output_tokens":16}
```
Expect HTTP 200 with a `model` field showing which provider actually served it.
Observed: `nvidia/nemotron-3-super-120b-a12b`, 25.6 s. `PRODUCTION-PROVEN`

Only combos **1, 13, 14** were fired, so *"all 14 combos work"* is **`PARTIAL`**, not
`PRODUCTION-PROVEN`. Do not claim otherwise.

## 4. Known-good vs known-bad providers

**Working (5/21):** `nvidia`, `auggie`, `aug`, `xiaomi`, `opencode` — `PRODUCTION-PROVEN`

**Fully expired (16/21, 0 of 14 working):** `opencode-zen`, `huggingface`, `sensetime`,
`baidu`, `alibaba`, `volcengine`, `tencent`, `ppio`, `siliconflow`, `moonshotai`,
`minimax`, `deepseek`, `google`, `z-ai`, `thinkingmachines`, `qwen` — `PRODUCTION-PROVEN`

## 5. Remediation

### Step 1 — Disable the 16 dead providers (fast win, minutes)

This is the highest value/cost action available. It stops the gateway burning attempts on
224 dead lanes and should cut the 19–26 s latency sharply.

- Do it in the OmniRoute UI at `http://127.0.0.1:20128`, or per-connection via the
  provider API. **The exact toggle/endpoint is `UNKNOWN` — I did not find a documented
  disable endpoint during this audit.** Confirm in the UI before scripting.
- ⚠️ Do **not** flip `isActive` expecting it to change `testStatus`. They are separate;
  see §2.

### Step 2 — Re-auth the high-value providers (hours/days)

224 credentials at ~14 per provider. Prioritise by usefulness, not alphabetically:
`google` (Gemini — already used as the VOICE primary elsewhere in the stack, so
highest marginal value), then `deepseek`, `qwen`, `siliconflow`.

### Step 3 — Re-verify and re-baseline

Re-run §3.3 and §3.4. Record the new `testStatus` split and the new p50 latency in this
file with today's date. **Replace the §3.3 baseline above rather than adding another
section** — this file must stay a single source of truth.

## 6. How to tell if it broke again

Any of these means re-run §3.3:

1. A combo that previously returned 200 starts returning non-200.
2. p50 latency on `/v1/responses` drifts above ~30 s.
3. Every combo resolves to the **same** model — rotation has collapsed to one lane.
4. The `testStatus` active count drops below 70.
5. `docker ps` no longer shows `leadgen_omniroute` as `Up`.

## 7. Do NOT do these

- **Do not** trust `~/.openclaw/workspace/omniroute_config.json` counts. It is
  out-of-repo, stale, and has no readers. `CODE-PRESENT` (grep `email_api_keys` → no
  code hit).
- **Do not** add a 14-step combo loop to `app/platform/omniroute_client.py`. The 2-hop
  `primary → different combo` design in `_TASK_ROUTES` (`:106-165`) is **deliberate**:
  the gateway rotates the combo's 42 internal slots. Adding a loop would duplicate
  rotation that already exists. `CODE-PRESENT`
- **Do not** make OmniRoute a hard dependency. It must stay fail-open; `free_ai.py` is
  the 24×7 path.
- **Do not** treat port `18789` as OmniRoute. That is the OpenClaw tray. `STALE` claim
  corrected in `docs/openclaw/setup_verification_summary.md`.

## 8. Open questions (honest gaps)

- The disable/enable endpoint for a provider connection is **`UNKNOWN`**.
- Whether re-auth can be scripted or is GUI-only is **`UNKNOWN`**.
- Whether all 14 combos return 200 is **`PARTIAL`** (3 of 14 fired).
- Whether the gateway exposes a health-score or circuit-breaker state per provider is
  **`UNKNOWN`** — `backoffLevel` and `rateLimitProtection` fields exist on each
  connection and may be relevant, but their semantics were **not** established.
