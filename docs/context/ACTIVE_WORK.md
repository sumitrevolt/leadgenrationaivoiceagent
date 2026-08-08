# ACTIVE_WORK - max 3 workstreams

---

## WS-PRF1 PR Factory Wave 1 - MERGE+DEPLOY IN FLIGHT
- **ID:** WS-PRF1
- **Business outcome:** Spec Kit constitution + thin `tools/pr_factory` dispatcher onto existing Owner OS `external_agents` (no second control plane); draft CI-repair Action + non-required Gate A
- **Current state:** Fixing Gate A pin contract (`pip install --upgrade pip` refused); rebase onto `main` @ `084cd990`
- **Next exact action:** CI green → undraft #248 → merge → kill-fence deploy; flags stay OFF
- **Out of scope:** vendoring openai/symphony · 100-PR claims · Merge Queue · auto-deploy · prod flag flips

---

## WS-GTM2 Admin Manual Call + Voice Dead-Air Fix - LIVE
- **ID:** WS-GTM2
- **Business outcome:** Owner `/app/admin` manual AI call + OmniRoute dead-air breaker
- **Current state:** Prod `/health`=`084cd990`
- **Next exact action:** admin login canary → optional real call `llm_first` verify
- **Out of scope:** env flips · compliance bypass

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** HQ empty; owner prospect pick
- **Next exact action:** Real ₹1999 UPI → LEDGER_PAID
- **Out of scope:** fake PAID

---

## Parked
- WS-AM1 Safe Pack (after LEDGER_PAID)
- Estique `removed`
- **ADR-172 Agent Teams C1** — PR #283: Cursor PROTOCOL-PASS. Claude AT canary **NOT-RUN**. **Do not merge #283 before Claude AT canary** or P1 is contaminated (remediated doc+test already on base). Predictions + confound gate: `docs/coordination/C1_CLAUDE_AT_PREDICTION.md`. Record `base_ref` in Observed. Windows: prune → baseline → paste on clean `origin/main`.
- **ADR-173 claw-orchestrator** — REJECT full vendor.
