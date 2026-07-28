# SESSION_HANDOFF - overwrite every session end

## Session objective
Reconcile control-plane docs (ACTIVE_WORK + SESSION_HANDOFF) with verified repository and host truth as of 2026-07-28.

## Outcome
Docs rewritten to match orchestrator-verified facts. No code, tests, CI, commit, push, or remote host contact.

## Head
- Running build: `dd193a69` (environment production, status healthy; direct HTTPS 2026-07-28T02:40:07Z)
- `origin/main`: `6a504321` (merge of PR #160 feat/runtime-data-a1-telephony)
- Local branch: `feat/runtime-data-a2-compliance` — 0 commits ahead of `origin/main`; uncommitted WIP on three compliance stores (`app/marketing/wa_campaign_runner.py`, `app/telephony/consent_ledger.py`); recovery patch `_recovery/wip_a2_compliance_20260728.patch`
- main is 36 commits ahead of the running build; running build is a direct ancestor of main (0 commits main lacks)
- Open PRs: 10 dependabot only (#149–#158); zero feature PRs open

## Safety
calling HARD OFF · `PLATFORM_DIAL_DAILY=0` · `WHATSAPP_AUTO_SEND=0` · `EXTERNAL_AGENT_ORCHESTRATOR` and `EXTERNAL_AGENT_RUNNER` both OFF on the host · sales autopilot present but INERT · Swara/voice FROZEN

## Verified truth
1. Host `/health` via direct HTTPS (no browser cache): version `dd193a69`, environment production, status healthy, fetched 2026-07-28T02:40:07Z. Any doc saying running build is `f096a08d` or `441cf37a` is STALE.
2. `dd193a69` is the merge commit of PR #147 (feat/external-agent-runner-v1), dated 2026-07-27. PR #147 is MERGED — not a draft, not waiting on owner merge.
3. `origin/main` is `6a504321`, the merge of PR #160 (feat/runtime-data-a1-telephony).
4. main is 36 commits AHEAD of the running build. The running build is a direct ancestor of main and contains 0 commits that main lacks. Only divergence: main is newer.
5. Ten open PRs, all dependabot (#149 through #158). Zero feature PRs open.
6. Local checkout on `feat/runtime-data-a2-compliance`, 0 ahead of `origin/main`, with uncommitted WIP moving three compliance stores onto the runtime-data authority resolver; recovery patch at `_recovery/wip_a2_compliance_20260728.patch`.
7. Preflight capture `_recovery/preflight_20260728.txt` (`scripts/runtime_data_preflight.py`, 2026-07-28, exit 0):
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
8. Truth hazard: Chrome load of `https://leadsgenai.in/health` returned a FIVE-DAY-OLD cached body (version `47d2fe3c`, timestamp 2026-07-23T14:02:19, uptime frozen at 0h 9m 10s); cache-busting query string was stripped — service worker answering `/health` from cache. Rule: confirm the running build version with a direct non-browser HTTPS request only.
