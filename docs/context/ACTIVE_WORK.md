# ACTIVE_WORK - max 3 workstreams

Fact tags: **GIT_VERIFIED** = reproducible from this repo. **DIRECT_HOST_VERIFIED** = observed from the live host over direct HTTPS at a stated time; not confirmable from GitHub. **LOCAL_ARTIFACT** = read from an untracked file on the machine that ran the session, so nobody else can open it. **ASSUMED** = carried forward from an earlier session and NOT re-checked.

---

## WS-1 GTM Hot Queue → 2nd paid customer - ACTIVE
- **ID:** WS-1
- **Business outcome:** Second Marketing paid customer
- **Current state:** Estique packet ready; human 1-click send — **ASSUMED**, carried over unchanged and not re-checked this session
- **Next exact action:** Owner send decision
- **Out of scope:** cold auto-calls · bulk WA

---

## WS-2 External Agent Runner v1 - MERGED / IS THE RUNNING BUILD
- **ID:** WS-2
- **Business outcome:** Unattended GREEN Cursor→Claude invocation with lease/heartbeat/review on local canary
- **Current state:** PR #147 (feat/external-agent-runner-v1) MERGED 2026-07-27 as `dd193a69` (GIT_VERIFIED); that commit is the running host build (DIRECT_HOST_VERIFIED, `/health` over direct HTTPS 2026-07-28T02:40:07Z, environment production). `EXTERNAL_AGENT_ORCHESTRATOR` and `EXTERNAL_AGENT_RUNNER` are OFF on the host — **ASSUMED**: `/health` returns no flags, so this was not probed. The local Windows GREEN canary has now run end to end — mission `msn_28f9cb4f2fe943a8`, executor cursor in an isolated worktree, reviewer claude read-only, verdict PASS, `scope_breach: false` (**LOCAL_ARTIFACT**, `_recovery/mission_ctxtruth_v2.log`, untracked) — and it produced PR #161. Both flags were set only inside that one local process and unset after it; the host was never touched.
- **Next exact action:** Explain the worker-uptime split recorded in `SESSION_HANDOFF.md` (owned follow-up 2) — it is the only open host question this session produced. Do not flip host runner flags.
- **Out of scope:** prod runner enable · deploy · calling · Swara

---

## WS-3 Runtime-data authority — A2 compliance wave in review
- **ID:** WS-3
- **Business outcome:** Move stores onto the runtime-data authority resolver; cut over only when the preflight allows it
- **Current state:** A1 (telephony) is merged in `origin/main` `6a504321`. A2 (compliance) is committed and pushed as **PR #162** (`feat/runtime-data-a2-compliance`) — read its state from GitHub, not from here — moving `compliance.wa_suppression`, `compliance.consent_ledger` and `compliance.voice_suppression` onto the resolver. Six stores are now `DUAL_READ_PRE_CUTOVER` and the blocker count is **unchanged at 21** — resolver-ready is not data-safe, and a drop to 18 would be a false green. Preflight (**LOCAL_ARTIFACT** `_recovery/preflight_20260728.txt`, re-run after A2 as `_recovery/preflight_after_a2.txt` with identical numbers; both untracked — re-run `python scripts/runtime_data_preflight.py` yourself):
  ```
  mode              : LEGACY_CHECKOUT_BACKED
  manifest version  : 2026-07-26.1
  cutover gate      : False
  marker            : ABSENT
  blocking stores   : 21
  DESTRUCTIVE DEPLOY: DENIED
      x LEGACY_AUTHORITATIVE_STORES_PRESENT(21)
      x MODE_LEGACY_CHECKOUT_BACKED
      x CUTOVER_GATE_DISABLED
      x MARKER_ABSENT
  ```
  A2 also surfaced an unclassified store: `data/wa_failures.jsonl` appears in no manifest row, yet three recorded failures auto-suppress a number. It is named in the A2 out-of-scope map and filed in `memory/backlog.md` **on the #162 branch** (that entry does not exist on main until #162 merges) rather than given an invented row; classifying it will move the count 21 → 22 as a discovery.
  Review history worth inheriting: an independent exact-head review of #162's first head `18d80a0` returned CHANGES_REQUIRED, and its `prod_check + pytest` job failed twice with exit 139 — a real SIGSEGV inside `ast.parse` during garbage collection, traced on the second attempt to the wave's own new test. Both the review findings and the crash were fixed at head `8c974b3`. The most transferable finding: the consent fixtures did not patch the WhatsApp store that `record_opt_out` cross-propagates into, so tests were writing the working copy's `data/wa_suppression.jsonl` — four of its rows are test numbers. That file is gitignored and was never committed, so the pollution is local; whether the VPS copy carries the same rows is unchecked and is owned follow-up 1 in `SESSION_HANDOFF.md`.
- **Next exact action:** Confirm required checks on PR #162 head `8c974b3` and obtain a fresh exact-head review, then merge. Do not cut over while the verdict is DENIED.
- **Out of scope:** destructive deploy · cutover while the gate is False · voice/Swara edits · migrating `wa_failures.jsonl` bytes

---

## Open PRs (named, not counted)
- **#161** — this control-plane truth reconciliation.
- **#162** — A2 compliance runtime-data authority wave.
- Dependabot PRs are also open.

Draft/merged/check state is deliberately NOT recorded here. A file cannot describe its own merge status correctly — the previous version of this document called an already-merged PR an open draft — so read every PR's live state from GitHub.
