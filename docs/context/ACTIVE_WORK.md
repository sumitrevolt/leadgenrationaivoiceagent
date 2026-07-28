# ACTIVE_WORK - max 3 workstreams

---

## WS-1 GTM Hot Queue → 2nd paid customer - ACTIVE
- **ID:** WS-1
- **Business outcome:** Second Marketing paid customer
- **Current state:** Estique packet ready; human 1-click send
- **Next exact action:** Owner send decision
- **Out of scope:** cold auto-calls · bulk WA

---

## WS-2 External Agent Runner v1 - MERGED / RUNNING BUILD
- **ID:** WS-2
- **Business outcome:** Unattended GREEN Cursor→Claude invocation with lease/heartbeat/review on local canary
- **Current state:** PR #147 (feat/external-agent-runner-v1) MERGED 2026-07-27 as `dd193a69`; that commit IS the running host build (environment production, status healthy, fetched 2026-07-28T02:40:07Z over direct HTTPS). `EXTERNAL_AGENT_ORCHESTRATOR` and `EXTERNAL_AGENT_RUNNER` both OFF on the host. Remaining work: local Windows GREEN canary only.
- **Next exact action:** Run local Windows GREEN canary; do not flip host runner flags.
- **Out of scope:** prod runner enable · deploy · calling · Swara

---

## WS-3 Runtime-data authority (A2 compliance WIP)
- **ID:** WS-3
- **Business outcome:** Move stores onto the runtime-data authority resolver; cutover only when preflight allows
- **Current state:** Local branch `feat/runtime-data-a2-compliance` is 0 commits ahead of `origin/main` (`6a504321`, PR #160 merge); uncommitted WIP moves three compliance stores onto the resolver (`app/marketing/wa_campaign_runner.py`, `app/telephony/consent_ledger.py`); not committed/pushed; recovery patch at `_recovery/wip_a2_compliance_20260728.patch`. Preflight `_recovery/preflight_20260728.txt` (2026-07-28, exit 0): mode `LEGACY_CHECKOUT_BACKED`; manifest version `2026-07-26.1`; cutover gate `False`; marker `ABSENT`; blocking stores `21` (tier0×11, tier1×8, tier2×2). Final verdict verbatim:
  ```
  DESTRUCTIVE DEPLOY: DENIED
      x LEGACY_AUTHORITATIVE_STORES_PRESENT(21)
      x MODE_LEGACY_CHECKOUT_BACKED
      x CUTOVER_GATE_DISABLED
      x MARKER_ABSENT
  ```
- **Next exact action:** Finish A2 compliance store wiring; re-run preflight; do not cut over while DENIED.
- **Out of scope:** destructive deploy · cutover while gate False · voice/Swara edits
