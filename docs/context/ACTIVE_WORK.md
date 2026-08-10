# ACTIVE_WORK - max 3 workstreams

---

## WS-TRUTH Source/runtime/docs truth + auth reconciliation (CURSOR)
- **ID:** WS-TRUTH
- **Business outcome:** Kill stale SHA/docs drift; Owner OS remains sole prod authority; authorization packet ready before any mutation
- **Current state:** Isolated worktree `C:\Users\Ratanshila\Documents\leadgen-automation-max-live-20260810` · branch `cursor/automation-max-live-20260810` · base/prod/`origin/main` = **`a3fbc8bb`** (DIRECT_HOST_VERIFIED 2026-08-10 dual `/health` probes, timestamps advanced). Open PRs = **0**. Primary checkout LEFT DIRTY on Buzz branch (untouched).
- **Next exact action:** Land AMAX/DUNNING safe-enabler correction PR → Checkpoint 4 owner auth packet (no deploy without AUTH-DEPLOY)
- **Out of scope:** Primary checkout edits · Buzz · Vobiz rotate · Creative OS expansion

---

## WS-REV Revenue path honesty (#304 / #306) (CURSOR)
- **ID:** WS-REV
- **Business outcome:** Guest UPI bind→approve money-path proof; REPLY_AUTO_SEND effective-flag honesty without posture change
- **Current state:** #304 OPEN — code LIVE on `a3fbc8bb` (bind API + admin UI); **live guest→bind→approve proof still WAIT** (needs AUTH-UPI-LIVE-PROOF). #306 OPEN — source already exposes `effective_on`/`effective_overrides` on `/api/growth/infra/flags`; **authenticated runtime proof WAIT**; do not flip reply posture.
- **Next exact action:** After merge/deploy of truth PR only if needed; owner supplies real pending payment ref for #304 close gate; admin session for #306 effective_on probe
- **Out of scope:** Fake PAID · auto-activate · REPLY_AUTO_SEND / HARD_OFF mutation

---

## WS-AMAX Automation-Max safe enabler correction (CURSOR)
- **ID:** WS-AMAX
- **Business outcome:** Default Automation-Max script cannot arm `DUNNING_ENGINE` (#307 owner: stays OFF); typed OWNER_GATED classification + regression tests
- **Current state:** Fix in this worktree — `DUNNING_ENGINE` removed from `WANT_SAFE`, `OWNER_GATED` refuse-on-truthy, manifest overlay `owner_approval_required`, docs/matrix/lane reconciled
- **Next exact action:** Targeted tests + prod_check → PR → AUTH-MERGE only when green
- **Out of scope:** Enabling dunning · blanket flag flips · SAFE_PACK env arming until LEDGER_PAID

---

## Parked (not in active 3)
- **WS-SEC1** Vobiz credential rotation — OWNER BLOCKER (`/root/vobiz_new.env` missing)
- **WS-GTM1** Hot Queue → 2nd paid — revenue-generated WAIT without owner-confirmed UPI #2
- **WS-DV1** Daily video — CODE READY on prior deploys; owner `DAILY_VIDEO_*` still pending (INERT)
- Buzz multi-harness / Comb / OmniRoute lane C
- Creative OS expansion · Swara/voice (FROZEN)
- Stage B AMBER OpenClaw
