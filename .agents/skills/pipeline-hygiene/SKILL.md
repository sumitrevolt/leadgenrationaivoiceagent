---
name: pipeline-hygiene
description: Weekly funnel-data safai — junk deals, stale "ready" prospects, reply-classifier drift, bulk-sender leaks. Use jab user bole "pipeline review/sweep karo", "deals junk lag rahe", "ready pile badh rahi", pipeline score kharab aaye, ya har hafte ek baar routine hygiene ke liye.
---

# Pipeline Hygiene (weekly sweep)

> 2026-06-12 review se born: score 31/100 — 464 "ready" stuck, 2 deals dono JUNK (PayU/Instamojo newsletters se reply_agent ne deals bana diye the). Guards ab code me hain; yeh sweep unhe VERIFY karta hai + naye leak pakadta hai.

## Sweep checklist (15 min, har Monday)
1. **Deals real hain?** `GET /api/growth/sales/deals` — har deal ka source prospect KNOWN hai? Unknown-sender deal = `_is_bulk_sender()` guard leak (`app/platform/reply_agent.py`) — sender pattern wahin add karo.
2. **Reply classifier drift**: reply triage stats — "other" bucket > 50% = classifier ya inbox noise problem. Sample 5 "other" replies padho: bulk/newsletter hain to guard; genuine hain to intent prompt tune (llm-error-analysis skill).
3. **Staleness**: prospects `created_at`/`updated_at` (ab store me hain) — "ready" 14+ din untouched = stale. Action: dialer-sprint list me daalo YA cadence re-enroll YA dead mark. "Ready" pile ko GROW mat hone do.
4. **Dunning/lifecycle stores**: `GET /api/growth/revenue/dunning` + `/revenue/lifecycle` — zombie cases (resolved par open)? Manual close.
5. **Channel attribution sanity**: `GET /api/growth/experiments` — outcomes credit sahi channels ko ja raha? UTM-less inbound spike = attribution gap.
6. **Re-score**: `POST /api/growth/leads/rescore` sweep ke baad — fresh data pe scores.

## Junk-source patterns (guard registry)
Newsletters/transactional senders jo LEAD NAHI hain: payment gateways (PayU/Instamojo/Razorpay notifications), no-reply@, marketing digests. Naya junk mile → `app/platform/reply_agent.py` `_is_bulk_sender()` me pattern + yahan note. (reply triage `run_reply_triage`, gated `REPLY_AGENT=1`; unknown+bulk = skip by design.)

## Output
Har sweep ka 3-line summary SESSION_LOG me: deals checked / stale count / naya guard (agar koi). Pipeline score re-run karke delta note karo. Score 3 hafte improve na ho = funnel-level problem (growth_optimizer analysis dekho), data-safai ka nahi.

## Enterprise gate

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`).

**Change-risk tier:** Read-only sweep = **Standard**. Lekin jaise hi guard code chhua (`_is_bulk_sender()` pattern add, classifier prompt, ya koi auto-send wire) = **High-risk** (ban-risk + CRM/deal writes) — neeche ke gates lock.

- **Idempotency/dedupe (junk-source guards leak na ho):** har naya `_is_bulk_sender()` pattern additive ho, existing known-prospect deals KABHI block na ho. `run_reply_triage` design = unknown+bulk skip; deal sirf KNOWN prospect pe — yeh invariant todna mat. `POST /api/growth/leads/rescore` idempotent (re-run pe duplicate deal nahi).
- **Reliability:** classifier/triage background work — pattern change ke baad `REPLY_AGENT` loop kabhi raise na kare (never-raise wrapper), fail pe lead skip (drop nahi). DLQ `dlq:failed_tasks` me triage failures dikhe.
- **Observability:** sweep delta + naya guard SESSION_LOG me; loop liveness `/api/growth/infra/flags` (REPLY_AGENT on?) + `automation_health` Neha pipeline-job gap. "other" bucket spike = drift signal, sweep me note.
- **Compliance (fail-CLOSED):** auto-send KABHI default-on mat karo — `_is_bulk_sender` guard ban-safety hai, weaken karne se WhatsApp/email number ban. Reply auto-send OFF rehne do (ban-safe), draft-only. DPDP: opt-out reply = consent-ledger suppression, fresh deal mat banao.
- **Rollback (NAMED):** guard regression (genuine prospect block ho gaya) → pattern git-revert + `REPLY_AGENT=0` flag OFF (loop inert) → fix → re-enable.

**Evidence (done):** `.venv\Scripts\python.exe scripts\prod_check.py` + guard change pe `pytest tests\test_reply_agent.py -q` (ya touched-area suite) green + pipeline-score re-run delta + sweep 3-line SESSION_LOG. Bina re-score + score-delta done mat bolo.
