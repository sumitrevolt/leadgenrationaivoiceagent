#!/usr/bin/env python3
"""Phase 3 — P0 playbook generator (operational format, no generic prose).

Writes ops/playbooks/PB-*.md for the 6 P0 workflows the master prompt
prioritizes: Sales, Payment Verification, Voice Calling, Deployment,
Customer Onboarding, Provider Failover. Each follows the playbook schema:
purpose/trigger/scope/prereqs/inputs/strategy/decision tree/allowed+
prohibited/escalation/KPIs/guardrails/linked runbooks/evidence/owner approval.

Run: python scripts/gen_p0_playbooks.py   (idempotent refresh)
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ops" / "playbooks"

PB = {}
PB["PB-SALES"] = """# PB-SALES — Sales Execution Playbook (P0)

- **Purpose**: Close verified revenue. Every action must move a lead toward
  owner_confirmed_upi with evidence at each step.
- **Trigger**: lead enters pipeline / hot lead surfaces / revenue sprint active.
- **Scope**: prospecting -> qualification -> outreach -> follow-up -> close.
- **Prereqs**: lead eligible (no opt-out, no DND, deduped), channel approved.

## Strategy
1. Hot Queue first: `/app/inbox` + daily 09:00 IST owner pack (CSV+MD+ntfy).
2. Qualification by niche/ICP fit — only qualified leads enter outreach.
3. Outreach via approved channels (WA 1-click human default; email ≤25/day; calling LIVE under gates).
4. Follow-up cadence until reply or 3-touch stop (consent-aware).
5. Close: manual UPI (canonical) -> owner confirms bank credit -> ledger + invoice.

## Decision tree
```
Lead surfaces
├─ opted out / DND?  -> SUPPRESS instantly (RB-SALES-005), no contact
├─ duplicate?        -> dedupe/merge (RB-SALES-004)
├─ high intent?      -> Hot Queue for OWNER 1-click close (RB-SALES-007)
├─ cold but in ICP?  -> nurture (email ≤25/day / call within window)
└─ not in ICP?       -> park (do NOT burn outreach budget)
```

## Allowed actions
- Query Hot Queue, dedupe, suppress opt-outs, log every message, record outcome.
- Email/WA/call via approved, rate-limited, consent-aware rails only.

## Prohibited actions
- Cold/bulk WhatsApp auto-send (ban risk) — 1-click human default.
- Claiming revenue without owner_confirmed_upi + ledger id.
- Contacting opted-out / DND numbers (compliance).

## Escalation
- Hot lead stuck >24h -> owner via Hot Queue pack.
- Conversion blocked by product/pricing -> raise to owner (WS-3 ACV decision).

## KPIs
- Verified collected revenue/day (only confirmed payments).
- Hot Queue close rate; reply rate; qualified lead cost.

## Guardrails
- Rate limits (email 25/day; calls in TRAI window 10-19 IST; concurrency=1 for dialer).
- All automation owner-armed; manual recovery path always available.

## Linked runbooks
RB-SALES-001..007 (WA send / auth / email / dedupe / opt-out / payment / hot lead).

## Evidence requirements
- Every outreach: message id, channel, timestamp, lead id.
- Every close: ledger entry + invoice id + owner confirmation.

## Owner approval conditions
- Revenue counted only after owner confirms bank credit.
- Any new paid acquisition channel.
"""

PB["PB-PAYMENT-VERIFICATION"] = """# PB-PAYMENT-VERIFICATION — Payment Verification Playbook (P0)

- **Purpose**: Turn UPI proofs into VERIFIED REVENUE — the only revenue that counts.
- **Trigger**: UPI proof received / invoice raised / ledger row pending.
- **Scope**: invoice -> proof -> owner confirm -> ledger -> revenue truth update.
- **Prereqs**: invoice raised (Rule-46 sequential `INV/2026-27/xxxx`), UPI_VPA set.

## Strategy
1. Invoice raised on close intent (packages.py = pricing single source).
2. Customer sends UPI proof (bank ref / screenshot via WhatsApp/phone).
3. **OWNER confirms bank credit** — `payment_verification_method = owner_confirmed_upi`.
4. Ledger updated with invoice id + confirmation -> revenue truth reflects it.
5. PROVIDER_VERIFIED is UNREACHABLE BY DESIGN (Stripe/Razorpay removed) — never fake it.

## Decision tree
```
UPI proof
├─ bank credit CONFIRMED by owner -> ledger VERIFIED -> revenue truth update
├─ proof unclear / pending      -> owner follow-up (Hot Queue pack)
└─ no proof, invoice stale      -> dunning per nikhil (Revenue Ops) — owner-armed
```

## Allowed actions
- Raise/void invoices (append-only markers), reconcile ledgers, push owner reminders.

## Prohibited actions
- Marking revenue verified without owner confirmation.
- Treating proposals/verbal yes/unpaid invoice as revenue.

## Escalation
- Invoice unpaid >48h -> owner via revenue digest.

## KPIs
- Verified ₹/day; invoice-to-confirm cycle time; dunning recovery rate.

## Guardrails
- Ledger append-only; VOID markers not deletes; backups before reconciliation.

## Linked runbooks
RB-SALES-006 (payment not verified), RUNBOOK_BILLING_INCIDENT.

## Evidence requirements
- Ledger id + invoice id + owner_confirmation timestamp.

## Owner approval conditions
- Revenue truth update is OWNER-CONFIRMED ONLY (human gate = manual UPI confirm).
"""

PB["PB-VOICE-CALLING"] = """# PB-VOICE-CALLING — Voice Calling Playbook (P0)

- **Purpose**: Run compliant outbound calling that converts — without breaking TRAI/carrier rules.
- **Trigger**: auto-dial run (11:30 IST daily) / manual call / voice campaign.
- **Scope**: lead feed -> DND/consent check -> call -> outcome -> follow-up.
- **Prereqs**: DLT_APPROVED=1, VOICE_LAUNCH_KILL=0, PLATFORM_DIAL_DAILY=1, cap=100/run, concurrency=1.

## Strategy
1. Feed: qualified leads from Hot Queue/prospect store (niche=all).
2. Compliance spine BEFORE anything: DND fail-closed, phone-type gate, AI-disclosure at start, 10-19 IST window.
3. Dial with Swara (Gemini voice LLM primary, EdgeTTS hi-IN, Groq STT) — free stack only.
4. Outcome capture: interested -> owner hot queue; not interested -> suppress; callback -> schedule.
5. Post-call owner-armed WA send (WHATSAPP_AUTO_SEND + POST_CALL_WHATSAPP) if interested.

## Decision tree
```
Lead before dial
├─ DND/consent/opt-out?     -> BLOCK (fail-closed) RB-VOICE-006
├─ outside window?          -> wait (10-19 IST)
├─ call fails: busy/auth/bal -> per runbook class (RB-VOICE-00x)
└─ call connects            -> Swara conversation -> outcome -> follow-up rail
```

## Allowed actions
- Dial within caps/window, log states, train pause (>30 failures), provider failover.

## Prohibited actions
- Cold auto-calls without DLT; calling outside window; AI-disclosure removal; concurrency>1; paid providers.

## Escalation
- Sustained high failure -> pause + RB-VOICE-008 (AMBER gate).

## KPIs
- Connect rate, qualified-interested rate, calls-to-close, ₹ per connected call.

## Guardrails
- DND fail-closed (lookup fail = block); recording gate; learned IVR blocklist; circuit breaker.

## Linked runbooks
RB-VOICE-001..010 (trunk, busy, auth, balance, stuck, rejection, provider outage, failure rate, latency, webhook).

## Evidence requirements
- Per call: session id, state, duration, outcome, audio (90-day retention rule).

## Owner approval conditions
- Any change to DLT/window/cap/compliance spine; provider wallet recharge.
"""

PB["PB-DEPLOYMENT"] = """# PB-DEPLOYMENT — Deployment Playbook (P0)

- **Purpose**: Ship code to prod safely with provenance + rollback, every time.
- **Trigger**: any production deploy request.
- **Scope**: verify -> build -> deploy -> probe -> record.
- **Prereqs**: kill fence for voice (VOICE_LAUNCH_KILL TRUE_TOKEN), prod_check --deployment PASS, secrets scan clean.

## Strategy
1. REPO TRUTH: fetch origin, confirm target sha on main (branch protection; PR-only).
2. CI green: pytest (targeted + billing truth), prod_check.py, check_secrets.py.
3. Deploy via CANONICAL script only: `scripts/deploy_vps.sh` (sets APP_VERSION=<sha>, deploys all 5 app-image services, pipefail).
4. Probe: /health .version == deployed sha, per-container skew = 0, smoke verify.
5. Record: progress.md Loop Run + SESSION_HANDOFF.

## Decision tree
```
Deploy request
├─ CI red / secrets dirty   -> STOP, fix first (RB-INFRA-008)
├─ APP_VERSION unset        -> refuse (:-latest = UNKNOWN provenance — landmine)
├─ health mismatch post-deploy -> rollback (RB-INFRA-009, RED)
└─ all green                -> record + ntfy
```

## Allowed actions
- deploy_vps.sh (DRY_RUN=1 for plan), targeted pytest, probes, rollback via previous sha.

## Prohibited actions
- Manual docker commands outside deploy script; reset --hard / blind rebuild on VPS; committing secrets; deploy without APP_VERSION.

## Escalation
- Deploy gate failure -> owner (kill fence missing/UNSET -> BLOCK).

## KPIs
- Deploy success rate; mean time to green; rollback rate.

## Guardrails
- Kill fence BEFORE deploy; `-f docker-compose.vps.yml` explicit; never deploy during active incident.

## Linked runbooks
RB-INFRA-007 (regression), RB-INFRA-009 (rollback), RB-INFRA-008 (CI failed), RB-INFRA-010 (config mismatch).

## Evidence requirements
- /health .version, dep.log tail, container skew table, smoke result.

## Owner approval conditions
- Owner arms deploy (kill-fence + script). Any hotfix outside normal PR flow.
"""

PB["PB-CUSTOMER-ONBOARDING"] = """# PB-CUSTOMER-ONBOARDING — Customer Onboarding Playbook (P0)

- **Purpose**: First paid customer -> activated, delivered, referenced (jiya makeover = template).
- **Trigger**: payment verified (owner_confirmed_upi) for a new customer.
- **Scope**: welcome -> setup -> first delivery -> feedback -> renewal path.
- **Prereqs**: ledger verified, invoice id, customer record with consent + isolation.

## Strategy
1. Welcome within 24h (brand-consistent, owner-approved copy).
2. Tenant isolation FIRST: customer-scoped KB namespace, no cross-client data access (DPDP).
3. Deliver the promised package (activation + first deliverables) — tracking in delivery ledger.
4. Collect feedback + consent updates (opt-out = instant suppression).
5. Nurture to renewal + reference/upsell (nikhil Revenue Ops).

## Decision tree
```
Payment verified
├─ deliverable package ready? -> activate + deliver + record evidence
├─ blocker (data/branding)    -> owner escalation + RB-VIDEO-004 if asset issue
└─ feedback received          -> store + feed product backlog (memory/backlog.md)
```

## Allowed actions
- Create customer-scoped records, deliver assets, log interactions, schedule follow-ups.

## Prohibited actions
- Cross-tenant data access; contacting after opt-out; promising unagreed deliverables.

## Escalation
- Delivery blocker >24h -> owner; churn-risk signals -> nikhil dunning/nurture.

## KPIs
- Time-to-first-delivery; activation rate; NPS/feedback; renewal likelihood.

## Guardrails
- Customer isolation invariant; consent ledger; 90-day recording retention.

## Linked runbooks
RB-SALES-006 (payment), RB-VIDEO-004 (branding), RUNBOOK_BILLING_INCIDENT.

## Evidence requirements
- Delivery record + customer-facing artifact + feedback log.

## Owner approval conditions
- Custom-package commitments; anything outside the sold plan.
"""

PB["PB-PROVIDER-FAILOVER"] = """# PB-PROVIDER-FAILOVER — Provider Failover Playbook (P0)

- **Purpose**: Keep the free AI stack alive when a provider degrades — automatically, cheaply.
- **Trigger**: provider 429 / quota exhaust / 5xx / latency spike.
- **Scope**: detection -> confirm -> failover -> recover -> record.
- **Prereqs**: circuit-breaker chain live (free_ai.py), llm_metrics, provider status source.

## Strategy
1. DETECT: llm_metrics ok-rate drop; circuit-breaker cooldowns; voice scorecard regression; Sentry burst.
2. CONFIRM it's the provider, not the app (check breaker state; check error series END timestamp — ADR-097).
3. FAILOVER is AUTOMATIC per-call: Mistral -> Groq -> Cerebras -> Gemini -> NVIDIA -> SambaNova -> OpenRouter; voice: Gemini 9-key rotation -> free chain; STT Groq -> Gemini -> local.
4. RECOVER: key rotation/add keys (owner), or wait cooldown; never fight the breaker.
5. RECORD: incident entry + prevention rule.

## Decision tree
```
Provider degraded
├─ 429/quota -> breaker cooldown auto (60s..30min) — usually NO action
├─ primary flapping -> chain routes around; watch ok-rate recover
├─ voice Gemini pool exhausted -> add keys via admin (AMBER)
└─ all providers down (rare) -> owner + RB-VOICE-007
```

## Allowed actions
- Rotate keys (scripted), watch metrics, add Gemini keys via admin API, escalate.

## Prohibited actions
- Adding PAID providers (free-stack mandate); disabling the breaker; claiming fix without error-series end timestamp.

## Escalation
- Multi-provider outage or voice deaf/silent -> owner immediately (RB-VOICE-007/009).

## KPIs
- Provider ok-rate; breaker recovery time; voice scorecard; cost per outcome.

## Guardrails
- Free providers ONLY; circuit-breaker never disabled; keys in env/data (never committed).

## Linked runbooks
RB-VOICE-007 (provider outage), RB-AGENT-005 (quota exhausted).

## Evidence requirements
- Metrics window (before/during/after), breaker state, decision log.

## Owner approval conditions
- Introducing ANY paid provider; manual intervention in a live call system.
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in PB.items():
        p = OUT / f"{name}.md"
        if p.exists() and p.read_text(encoding="utf-8") == content:
            print(f"  [unchanged] {p.relative_to(ROOT)}")
        else:
            p.write_text(content, encoding="utf-8")
            print(f"  [written] {p.relative_to(ROOT)}")
    print(f"P0 PLAYBOOKS: {len(PB)}")


if __name__ == "__main__":
    main()