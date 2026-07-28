# SESSION_HANDOFF - overwrite every session end

## Session objective
Reconcile control-plane docs (ACTIVE_WORK + SESSION_HANDOFF) with verified repository and host truth as of 2026-07-28.

## Outcome
Docs rewritten to match verified facts. This branch changes documentation only — no code, tests, CI, flags, data or remote host.

## Evidence classes
Every fact below is tagged with how it was obtained, because the two classes are not equally checkable by a reviewer:

- **GIT_VERIFIED** — reproducible from this repository (`git`, `gh`) by anyone.
- **DIRECT_HOST_VERIFIED** — observed from the live host over direct HTTPS at a stated timestamp. NOT reproducible from the repo, and NOT confirmable from GitHub. Treat as a dated observation, not a repo invariant.

## Head
- Running build: `dd193a69` — **DIRECT_HOST_VERIFIED** (`GET https://leadsgenai.in/health` over direct HTTPS from a non-browser client, 2026-07-28T02:40:07Z: `environment: production`, `status: healthy`)
- `origin/main`: `6a504321` (merge of PR #160 feat/runtime-data-a1-telephony) — GIT_VERIFIED
- main is 36 commits ahead of the running build; the running build is a direct ancestor of main and holds 0 commits main lacks — GIT_VERIFIED
- Feature branches in flight (both pushed, both Draft):
  - `feat/ext-ctxtruth-0c09ee` → PR #161, this branch
  - `feat/runtime-data-a2-compliance` → PR #162, A2 compliance runtime-data authority wave

## Open pull requests
Named rather than counted — a total goes stale the moment the next PR opens, which is exactly how the previous version of this file became wrong.

- **PR #161** — control-plane truth reconciliation (this branch). Draft.
- **PR #162** — A2 compliance runtime-data authority wave. Draft. Blocking-count arithmetic unchanged at 21 by design. Its first head `18d80a0` received an independent review verdict of CHANGES_REQUIRED and failed `prod_check + pytest` twice with exit 139; both were addressed at head `8c974b3` (see the A2 note below). Read its live check state from GitHub, not from here.
- Dependabot PRs are also open; treat their count as volatile and read it from GitHub, not from here.

### A2 (PR #162) — what the review caught, recorded because it generalises
- The migration's own isolation claim was false: `consent_ledger.record_opt_out` cross-channel-propagates into `wa_campaign_runner.suppress()`, which the consent fixtures did not patch, so tests wrote the repository's real `data/wa_suppression.jsonl`. Four test numbers from `tests/test_consent_ledger.py` are still committed in that file. **Someone should check whether the VPS copy of `data/wa_suppression.jsonl` carries the same test rows** — this checkout being polluted does not prove production is clean.
- `pyproject.toml` sets `filterwarnings = ["ignore::DeprecationWarning", ...]`, so any deprecation tripwire is inaudible under pytest. Anything relying on `DeprecationWarning` to be noticed in this repo is not actually wired.
- CI exit 139 was a real SIGSEGV inside `ast.parse` during garbage collection, named to a specific test on the second attempt. Diagnosed and fixed by making the scan ~330× cheaper, not by re-running until green.

## Safety
calling HARD OFF · `PLATFORM_DIAL_DAILY=0` · `WHATSAPP_AUTO_SEND=0` · `EXTERNAL_AGENT_ORCHESTRATOR` and `EXTERNAL_AGENT_RUNNER` both OFF on the host · sales autopilot present but INERT · Swara/voice FROZEN · **no deployment is authorised by either open PR**.

## Verified truth
1. **DIRECT_HOST_VERIFIED** — `/health` over direct HTTPS (no browser in the path): version `dd193a69`, environment production, status healthy, 2026-07-28T02:40:07Z. Any doc saying the running build is `f096a08d` or `441cf37a` is STALE.
2. **GIT_VERIFIED** — `dd193a69` is the merge commit of PR #147 (feat/external-agent-runner-v1), dated 2026-07-27. PR #147 is MERGED: not a draft, not waiting on an owner merge decision.
3. **GIT_VERIFIED** — `origin/main` is `6a504321`, the merge of PR #160 (feat/runtime-data-a1-telephony).
4. **GIT_VERIFIED** — main is 36 commits AHEAD of the running build; the running build is a direct ancestor and contains 0 commits main lacks. The only divergence is "main is newer".
5. **GIT_VERIFIED** — two feature PRs are open (#161, #162), plus Dependabot PRs. See the Open pull requests section for why this is stated by name and not by count.
6. **GIT_VERIFIED** — the A2 compliance work that was uncommitted WIP earlier in this session is now committed and pushed as PR #162 (`feat/runtime-data-a2-compliance`). The recovery patch taken before it was committed remains at `_recovery/wip_a2_compliance_20260728.patch` (untracked, local only).
7. **GIT_VERIFIED (tool output)** — preflight capture `_recovery/preflight_20260728.txt` (`scripts/runtime_data_preflight.py`, 2026-07-28, exit 0):
   - mode: `LEGACY_CHECKOUT_BACKED`
   - manifest version: `2026-07-26.1`
   - cutover gate: `False`
   - marker: `ABSENT`
   - blocking stores: `21` (tier0×11, tier1×8, tier2×2)
   - Final verdict:
     ```
     DESTRUCTIVE DEPLOY: DENIED
         x LEGACY_AUTHORITATIVE_STORES_PRESENT(21)
         x MODE_LEGACY_CHECKOUT_BACKED
         x CUTOVER_GATE_DISABLED
         x MARKER_ABSENT
     ```
   PR #162 re-runs this after its change and the count is still `21`: six stores can now follow a cutover, but no bytes have moved, so nothing is safer yet. A count of 18 would be a false green.
8. **DIRECT_HOST_VERIFIED — truth hazard.** Loading `https://leadsgenai.in/health` in Chrome returned a FIVE-DAY-OLD cached body (version `47d2fe3c`, timestamp 2026-07-23T14:02:19, uptime frozen at `0h 9m 10s`) and the cache-busting query string was stripped from the URL — the signature of a service worker answering `/health` from cache. **Rule: confirm the running build version with a direct non-browser HTTPS request only.**
9. **DIRECT_HOST_VERIFIED — unresolved observation, not a diagnosis.** Two `/health` probes 76 seconds apart reported uptimes of `22h 28m` and `1h 43m` with the same version `dd193a69`. The straightforward reading is per-worker uptime under `WEB_CONCURRENCY=2`, meaning one worker restarted roughly 1h43m before the probe. **Why it restarted is unknown and was not investigated.** Recorded so the next session can check worker/container logs; do not cite it as a proven incident or a proven non-issue.

## Next session
Read this file, then re-probe `/health` directly (not in a browser) and re-run `git fetch` before asserting any SHA. Both open PRs are Draft; neither authorises a deployment.
