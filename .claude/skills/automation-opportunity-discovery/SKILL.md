---
name: automation-opportunity-discovery
description: Use when deciding which manual process to automate next on LeadGen, mapping a workflow before building, scoring automation opportunities by frequency, effort, risk and revenue impact, or reviewing a running automation for canary-kill — selects the highest-value compliance-safe slice with evidence, rollback and owner gates.
---

# Automation Opportunity Discovery (LeadGen)

> Front-of-pipeline decision procedure: **kaunsa manual process automate karein (ya skip), score kya hai, pre-flight gates kya hain, canary kaise, kill kab, rollback kya.** Ye existing engines ko INVOKE karta hai — naya control plane nahi, 32nd agent nahi, scheduler/CRM/billing duplicate nahi.
> Source discipline: book principles (The Goal, Lean Startup, Running Lean, Phoenix Project, Accelerate, Checklist Manifesto, E-Myth, Traction) → `references/book-sources.md` (attribution + evidence tiers). Copyright-safe: sirf independently rewritten principles, koi copied prose/template nahi.

## When to use

- Owner/agent: "ab kya automate karein?", "ye kaam automate karna chahiye?", "ye automation band kar dein?"
- Self-improve loop: next opportunity pick se pehle (opportunity scoring).
- Post-incident: "kaunsa unplanned work baar-baar aata hai?" (work-type triage).
- Naya automation feature propose karne se pehle (discovery → score → gate).

**NOT for:** feature-change on existing code (`feature-change-flow`), flag flip (`automation-flags`), loop death/restart (`agent-loop-design`), full launch gate (`production-ready`), strategic roadmap (`executive-council`, `advancement-roadmap`).

## 1. Pre-flight (Checklist-Manifesto discipline — 5 items, kabhi skip nahi)

- [ ] Constraint confirm: bottleneck kahan hai? **Current sprint constraint canonical context se padho** (`CLAUDE.md` → Current State sprint goal, `docs/context/`) — ye change hota rehta hai, kisi specific surface ko hardcode mat karo. Naya top-funnel loop tab tak waste hai jab tak mid-funnel constraint clear na ho.
- [ ] Overlap check: existing skill/capability grep (`.claude/skills/`), duplicate route grep (`duplicate-route-guard`) — pehle se hai to EXTEND, rebuild nahi.
- [ ] Active-writer check: `docs/context/ACTIVE_WORK.md` — file kisi active lane ka hai to `WAIT — OVERLAPPING WRITER`.
- [ ] Compliance posture: TRAI window/DND fail-closed/AI-disclosure/consent, DPDP retention, WhatsApp cold-send OFF, manual-UPI owner gate — automations inhe weaken NAHI kar sakte.
- [ ] Free-stack check: koi paid STT/TTS/LLM add nahi; provider budget (Groq TPD, Cerebras 429, email 25/day, `PROSPECT_MAX_LOOKUPS`) respect karo.

## 2. Discover — manual process map (Running Lean + Phoenix Project)

1. Current manual workflow ko document karo — steps, owner (human role ya STAFF agent), data touched, decision points, frequency.
2. **Work-type triage** (Phoenix Project): Business-project? Internal improvement? Change? **Unplanned** (recurring incident/rework)? — Unplanned = pehle fix, automate mat karo.
3. Evidence of real demand: is manual step ka repeat count/₹ impact hai? (e.g. Hot Queue leads sitting uncontacted, follow-ups missing, report builds by hand.)
4. "Automate the proven": ye step pehle 5-10 baar manually karke conversion/revenue dikha chuke ho? Nahi → automate mat karo (platform_dial IVR-burn lesson).
5. Result: 1-page process map (steps → owner → data → gate). Ye map hi contract hai.

## 3. Score — opportunity matrix

Har opportunity ko 1–10 score karo, phir rank by composite:

| Axis | 1 = low | 10 = high | Why |
|---|---|---|---|
| Frequency | roz nahi | daily/high | recurring = compounding |
| Effort (inverse) | multi-week build | half-day slice | small vertical slice first |
| Risk (inverse) | ban/DLT/compliance | draft-only/no side-effect | tail-risk fatal (WhatsApp ban, TRAI ₹10L) |
| Revenue impact | vanity (emails sent) | paying-customer distance | north-star = paid customer, not activity |
| Owner-time saved (E-Myth) | agent/automation does it | owner manually does it | buy back founder time |

**Direction (explicit):** Frequency, Revenue impact, Owner-time saved = *higher-better* (10 = best). Effort, Risk = *lower-better* (10 = worst) — isliye wo denominator me jaate hain.

**Composite = (Frequency × Revenue impact × Owner-time saved) ÷ (Effort + Risk)** — higher = better.
**Normalize (zaroori):** composite ko isi opportunity set ke max se divide karo (max = 1.0) tabhi rank karo — absolute numbers cross-set compare karna misleading hai.
Sort descending. Ban-risky or compliance-touching outbound → automatically owner-gated (never auto-run).

Existing repo levers to score against: `sales_autopilot` refill, Hot Queue chase, `auto_content`/`content_schedule` due-run, follow-up D3/D7, report delivery, dunning, lifecycle warmup, inbox triage.

## 4. Gate — approval + kill-switch (pre-flight, fail-closed)

Har naya/expanded automation ke paas:

- **Typed flag** default OFF → `AUTOMATION_FLAGS` in `app/api/growth.py` + `automation_flag_manifest.py` kind (owner/provider/compliance/disabled) → visible at `/api/growth/infra/flags`. "All flags ON" FORBIDDEN.
- **Idempotency/replay**: dedupe (success-pe-hi-mark state) — duplicate email/call/bill/post kabhi nahi.
- **Retry/DLQ**: bounded retry + `dlq:failed_tasks` fail-record; per-iteration timeout (`asyncio.wait_for` 240s pattern).
- **Observability**: heartbeat (`data/<loop>_state.json` + `automation_health.EXPECTED_GAP_MIN` entry) + `team.log_event` + operator surface (admin UI tab SAATH — API-only adhoora).
- **Rollback (NAMED)**: flag OFF + container recreate; `.env.bak-*` restore; migration rollback path.
- **Owner gate**: money/reputation side-effect (UPI confirm, send/call/post enable) = automation PREPARE kare, human FIRE kare (1-click).

## 5. Run — canary slice (Lean Startup)

1. Smallest vertical slice: `inspect → contract → implement → targeted test → verify → self-review → next slice`.
2. Canary first: allowlist/1-client/test-mode (e.g. `DIAL_TEST_MODE` pattern, single-client allowlist) — evidence pe hi sab pe.
3. Tests: happy + failure branch + duplicate/idempotency + refusal (gate off) — naya behaviour = naya test.
4. **Verify** (exact commands + exit codes ledgered in `docs/research/GAP_MANIFEST_AND_VERIFICATION.md`):

```bash
.venv/Scripts/python.exe scripts/prod_check.py
.venv/Scripts/python.exe scripts/check_secrets.py
git diff --check
```

Targeted pytest bhi chalao for any new behaviour (happy + refusal + retry + duplicate paths).

## 6. Measure + Kill (Accelerate + Lean Startup)

- Define success metric BEFORE canary: revenue/customer outcome, not "job ran"/"queue empty"/"HTTP 200".
- Cadence (Traction): fixed review point — weekly ops review (`automation_health_audit --daily-check` + `/api/growth/infra/automation-health`) pe KEEP / KILL / SCALE / FIX.
- **Kill-fast, no sunk cost**: 2 hafte me signal nahi → flag OFF + `memory/backlog.md` park + 1-line postmortem `memory/incidents.md`/`decisions.md`. Zombie loop = quota/attention/risk kha raha hai.
- Change-failure evidence: `dlq:failed_tasks` weekly inspect + replay runbook (har dropped task = dropped lead/₹).

## 7. Output contract

Har run ye deliver kare (10-field — repo ke `docs/LOOP_ENGINEER.md` 9-field style + opportunity score; count intentionally 10): Goal · Inspected (process map) · Opportunity score + rank · Problems found · Changed (flag + slice) · Tests Run (exit codes) · Verification Evidence (artifacts) · Risks · Rollback (NAMED) · Next Highest Priority.
Hinglish Roman reply, end me canary line `🐦 pelican`.

## 8. Verification of this skill

```bash
.venv/Scripts/python.exe scripts/skill_evals/check_repo_skills.py --skill automation-opportunity-discovery --added automation-opportunity-discovery
.venv/Scripts/python.exe -m pytest tests/test_skill_tree_canonical_guard.py -q
.venv/Scripts/python.exe scripts/check_secrets.py
.venv/Scripts/python.exe scripts/prod_check.py
git diff --check
```

All five must exit 0; a timeout is UNVERIFIED, never PASS. Only mission-owned files in the diff.

## References

- `references/book-sources.md` — attribution ledger (sources → synthesis → LeadGen adaptation).
- Trigger cases: skill ka `trigger-cases.json` (11 cases — 5 positive lexical, 1 semantic, 5 negative; repo evals root me registered).
- Related skills (invoke, don't duplicate): `feature-change-flow` · `automation-flags` · `agent-loop-design` · `automation-pipeline` · `leadgen-automation-reliability` · `fable-operating-manual` (Part C) · `verify-ship` · `production-ready` · `leadgen-revenue-readiness` · `advancement-roadmap`.
