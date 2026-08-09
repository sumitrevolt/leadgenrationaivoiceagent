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

## WS-DV1 Daily video producer - CODE READY, OWNER FLAGS PENDING
- **ID:** WS-DV1
- **Business outcome:** marketing customer ko ROZ 1 video (classic ab, HyperFrames-advanced toolchain deploy ke baad)
- **Current state:** ADR-166 shipped local — `daily_video.py` + own beat job + backpressure + engine `auto`; 122 tests green, `prod_check` PASS; flags default OFF, not deployed
- **Next exact action:** Stage 1 of `docs/runbooks/RUNBOOK_DAILY_VIDEO.md` (`DAILY_VIDEO_ENABLED=1`, `DAILY_VIDEO_CLIENTS=jiya-makeover`, `ENGINE=classic`) + clear the 32 pending reviews
- **Out of scope:** auto-publish · daily WA blast · pricing copy "daily" claim before a week of proven delivery

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
