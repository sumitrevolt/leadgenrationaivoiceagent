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
- **ADR-172 Agent Teams C1** — tip `d1042e69` FROZEN/GO; P1 window OPEN (`main=5ae5a4b9`, deliverables absent). **Sumit-only:** prune / Usage baseline / Claude Code paste. **Agents forbidden** to merge #283 or fake those steps. After Observed: agents may interpret + write handoff.
- **ADR-173 claw-orchestrator** — REJECT full vendor.
