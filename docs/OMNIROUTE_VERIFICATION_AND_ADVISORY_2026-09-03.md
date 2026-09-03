# OmniRoute Status — Independent Verification & Advisory
**Date:** 2026-09-03 09:00 IST
**Method:** every claim below was re-tested live. Nothing is taken on trust from the prior status summary.

---

## 1. Verification results

| Claim | Verified | Evidence |
|---|---|---|
| OmniRoute server running, port 20128 | ✅ TRUE | `LISTENING pid 21320` |
| `/v1/models` = 12 models | ✅ TRUE | HTTP 200, 12 entries |
| `/api/v1/combos` = 62 combos | ✅ TRUE | HTTP 200, 62 entries |
| Hermes Desktop running, 5 PIDs | ✅ TRUE | PIDs 22904, 30904, 16280, 12368, 35800 |
| Dashboard reachable | ✅ TRUE | `http://127.0.0.1:20128` |
| Leadgen combos = **14** | ❌ **FALSE — it is 13** | Enumerated from `/api/v1/combos` |
| "Hermes Profiles (12)" | ⚠️ **MISLEADING** | Only **9** combos are `hermes-*`. "12" is the `/v1/models` count, which adds `claude-code`, `vps-01`, `vps-02` |
| "62 combos" are all routing combos | ⚠️ **MISLEADING** | Only **22** are combos. 40 are individual model aliases and web tools |

### Actual composition of the 62 entries

| Bucket | Count | What they are |
|---|---|---|
| `leadgen-*` | **13** | Real routing combos |
| `hermes-*` | **9** | Real routing combos (owner, sales, engineer, voice, marketing, ops, qa, research, finance) |
| Other | **40** | Model aliases (`claude-3-5-sonnet`, `gpt-4o`, `o1-mini`, `o3-mini`, `claude-opus-4.8`, …) and web tools (`ddgw`, `duckduckgo-web`, `blackbox-web`, `veo-free`, `inner-ai`, `aug`, `auggie`, `chipotle`, `pepper`, `mcode`, `mimocode`, `default`) |

**The 13 leadgen combos** (not 14): `agent-ops`, `coding-fast`, `coding-primary`, `free-first`, `governor-review`, `marketing-content`, `outreach-email`, `project-best`, `prospect-enrich`, `repo-analysis`, `seo-keyword`, `swara-live`, `test-generation`.

### `leadgen-free-first` — the only mandate-aligned combo
Verified payload: `strategy: round-robin`, 5 models, **all free tier**:
`oc/laguna-s-2.1-free` · `oc/nemotron-3.5-lightning-free` · `groq/llama-3.3-70b` · `openrouter/deepseek/deepseek-v4-flash-0731` · `huggingface/deepseek-ai/DeepSeek-V4-Flash`

This is the single combo that matches the standing owner mandate in `AGENTS.md` §1: *"Entire AI stack = FREE providers only (no paid STT/TTS/LLM)."*

---

## 2. ADVISORY — do not add the 42 provider API keys

**Recommendation: skip it.** Three independent reasons.

### Reason 1 — it violates a standing owner mandate
`AGENTS.md` §1 is explicit: **free providers only, no paid LLM/STT/TTS.** The proposed list is dominated by paid commercial providers — SiliconFlow, Volcengine, Zhipu, Alibaba, Baidu, Tencent, iFlytek, Together, Cohere. Adding them inverts a decision the owner already made deliberately.

### Reason 2 — it has zero revenue impact
The local OmniRoute gateway is a **local dev / desktop tooling** gateway. It is not in the production AI path:

- Production runs in Docker on the Hostinger VPS (`/opt/leadgen`) and **cannot reach `127.0.0.1:20128` on this laptop**.
- `progress.md` (2026-08-31 loop) states the gateway is required *"for local dev API calls"*.
- Production's own free chain (Mistral → Groq → Cerebras → Gemini → NVIDIA NIM → SambaNova → OpenRouter) is already live; `7_DAY_REVENUE_PLAN.md` Day 0 recorded **5/5 providers healthy**, and `/health` returned `environment: production` today.

Adding 42 keys changes nothing on `leadsgenai.in`, produces no lead, and closes no invoice.

### Reason 3 — it costs the one resource the 7-day sprint is short of
The estimate is 15–20 minutes of owner time. In the same 20 minutes, the two moves that actually move the ladder are:

| Move | Value | vs 42 keys |
|---|---|---|
| Jiya Makeover Starter → Combo upsell | **+₹4,000** | Real, highest probability |
| Kamal Starter → Combo upsell | **+₹4,000** | Real, highest probability |
| **Combined** | **+₹8,000 = 50% of the ₹16,000 base target** | 42 keys = ₹0 |

---

## 3. What is actually worth doing (ranked)

| Priority | Action | Time | Why |
|---|---|---|---|
| **P0** | Jiya + Kamal Combo upsell conversations | 20 min | +₹8,000, highest probability revenue in the window |
| **P1** | Set the OmniRoute dashboard password | 2 min | Real security item; the gateway is reachable on loopback |
| **P1** | Restart Hermes via `scripts/start-hermes-omniroute.ps1` | 2 min | Moves the app off the fragile path (see §4) |
| **P2** | Set `leadgen-free-first` as the default combo for local work | 5 min | The only combo aligned with the free-only mandate |
| **P3** | Add provider keys — **only if** a specific free-tier gap appears later | — | Needs-based, not speculative |

---

## 4. Hermes: running, but on the fragile path

The app **is** up (5 PIDs, `desktop.log` actively writing `sessions.changed` events). But:

- Backend bound to **dynamic ports 49890 / 49899** — i.e. the `--port 0` path.
- **Port 9119 is still DOWN**, so the machine-level server is not in use.
- Today's `desktop.log` shows this path already failed three times: `01:48:56`, `01:59:19`, `02:04:15` — each ending `Hermes backend for profile "default" exited (1)`.
- The current session only came up at `03:19:12` after the desktop's own bootstrap repair: *"primary backend process has exited; restarting before escalating to reinstall."*

**Assessment:** it works, but it is self-rescuing from the same failure mode that killed three sessions earlier today. Restarting through the launcher puts it on the stable machine-level 9119 backend and removes the recurrence. Low urgency while it is up — do it at the next natural break, not mid-conversation.

---

## 5. Bottom line

The infrastructure is genuinely healthy: OmniRoute 62/12 verified, Hermes up, production green. That is the right place to be.

But **structural completeness is not the constraint** — the constraint is compliant channel capacity and two un-sent upsell messages. Do not spend the morning on 42 API keys. Spend it on Jiya and Kamal.
