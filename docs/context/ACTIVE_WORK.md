# ACTIVE_WORK - max 3 workstreams

Fact tags: **GIT_VERIFIED** = reproducible from this repo. **DIRECT_HOST_VERIFIED** = observed from the live host over direct HTTPS at a stated time; not confirmable from GitHub.

---

## WS-1 GTM Hot Queue → 2nd paid customer - ACTIVE
- **ID:** WS-1
- **Business outcome:** Second Marketing paid customer
- **Current state:** Estique packet ready; human 1-click send
- **Next exact action:** Owner send decision
- **Out of scope:** cold auto-calls · bulk WA

---

## WS-2 External Agent Runner v1 - MERGED / IS THE RUNNING BUILD
- **ID:** WS-2
- **Business outcome:** Unattended GREEN Cursor→Claude invocation with lease/heartbeat/review on local canary
- **Current state:** PR #147 (feat/external-agent-runner-v1) MERGED 2026-07-27 as `dd193a69` (GIT_VERIFIED); that commit is the running host build (DIRECT_HOST_VERIFIED, `/health` over direct HTTPS 2026-07-28T02:40:07Z, environment production). `EXTERNAL_AGENT_ORCHESTRATOR` and `EXTERNAL_AGENT_RUNNER` are both OFF on the host. The local Windows GREEN canary has now run end to end — mission `msn_28f9cb4f2fe943a8`, executor cursor in an isolated worktree, reviewer claude read-only, verdict PASS, `scope_breach: false` — and it produced PR #161. Both runner flags were unset again after the invocation.
- **Next exact action:** None required. Do not flip host runner flags.
- **Out of scope:** prod runner enable · deploy · calling · Swara

---

## WS-3 Runtime-data authority — A2 compliance wave in review
- **ID:** WS-3
- **Business outcome:** Move stores onto the runtime-data authority resolver; cut over only when the preflight allows it
- **Current state:** A1 (telephony) is merged in `origin/main` `6a504321`. A2 (compliance) is committed and pushed as **PR #162** (`feat/runtime-data-a2-compliance`), Draft, moving `compliance.wa_suppression`, `compliance.consent_ledger` and `compliance.voice_suppression` onto the resolver. Six stores are now `DUAL_READ_PRE_CUTOVER` and the blocker count is **unchanged at 21** — resolver-ready is not data-safe, and a drop to 18 would be a false green. Preflight `_recovery/preflight_20260728.txt` (exit 0), re-run after A2 with the same result:
  ```
  mode              : LEGACY_CHECKOUT_BACKED
  cutover gate      : False
  marker            : ABSENT
  blocking stores   : 21
  DESTRUCTIVE DEPLOY: DENIED
      x LEGACY_AUTHORITATIVE_STORES_PRESENT(21)
      x MODE_LEGACY_CHECKOUT_BACKED
      x CUTOVER_GATE_DISABLED
      x MARKER_ABSENT
  ```
  A2 also surfaced an unclassified store: `data/wa_failures.jsonl` appears in no manifest row, yet three recorded failures auto-suppress a number. It is named in the A2 out-of-scope map and filed in `memory/backlog.md` rather than given an invented row; classifying it will move the count 21 → 22 as a discovery.
  Review history worth inheriting: an independent exact-head review of #162's first head `18d80a0` returned CHANGES_REQUIRED, and its `prod_check + pytest` job failed twice with exit 139 — a real SIGSEGV inside `ast.parse` during garbage collection, traced on the second attempt to the wave's own new test. Both the review findings and the crash were fixed at head `8c974b3`. The most transferable finding: the consent fixtures did not patch the WhatsApp store that `record_opt_out` cross-propagates into, so tests were writing the repository's real `data/wa_suppression.jsonl` — four test numbers are still committed there, and the VPS copy has not been checked.
- **Next exact action:** Confirm required checks on PR #162 head `8c974b3` and obtain a fresh exact-head review, then merge. Do not cut over while the verdict is DENIED.
- **Out of scope:** destructive deploy · cutover while the gate is False · voice/Swara edits · migrating `wa_failures.jsonl` bytes

---

## Open PRs (named, not counted)
- **#161** — this control-plane truth reconciliation. Draft.
- **#162** — A2 compliance runtime-data authority wave. Draft.
- Dependabot PRs are also open; read their count from GitHub, never from this file.
