# OmniRoute A-Z completion plan

## Goal and approach

Finish the local WSL OmniRoute gateway without changing LeadGen's production customer
LLM/voice path. Preserve the existing optional adapter, validate only connected
providers with sanitized requests, and make the true provider/routing/rollback state
explicit in focused documentation. Any production wiring remains disabled unless a
separate, evidence-backed opt-in is authorized.

## Change-risk tier

Standard for local gateway configuration and documentation; high-risk if any future
change attempts to route LeadGen customer data, voice, billing, or automation traffic.
Rollback is restoring `/root/.omniroute_backups/a2z-20260713T170103Z/omniroute` and
leaving `OMNIROUTE_ENABLED=0`.

## File map

| File | Owner | Change |
| --- | --- | --- |
| `docs/plans/2026-07-13-omniroute-a2z.md` | main session | This execution contract and evidence plan. |
| `docs/omniroute/*` | main session | New, focused, secret-free architecture, provider matrix, policy, runbook, and evidence. |
| `progress.md` | main session | Final loop evidence only. |

No shared runtime file is edited in this phase. Existing `app/platform/omniroute_client.py`
and privacy controls are inspected and tested, not rewired.

## Tasks and evidence

1. Preserve a rollback snapshot outside Git and record version, ports, process count,
   tmux session and restore steps. Evidence: readable manifest and backup data directory.
2. Inventory the actual running gateway using its Node 22 binary; separate the stale
   `/usr/bin` copy from the running nvm binary. Evidence: doctor output, listener map,
   dashboard inventory and provider detail pages.
3. Re-test each existing useful API-key connection with a non-sensitive gateway health
   request. Evidence: no browser console errors, connected state, and discovered model count.
4. Do not add providers or credentials. Classify browser-cookie providers as excluded;
   leave unavailable OAuth/IDE providers unconnected pending a human credential action.
5. Verify LeadGen remains inert by default with the existing tests and privacy tests;
   run `prod_check.py` and secret scan. Evidence: command output.
6. Write secret-free architecture, provider matrix, policy, operations, rollback and
   verification docs. Add the loop result to `progress.md` only after all evidence is
   collected.

## Gates

- No secret reads, writes, or screenshots.
- No provider discovery or web-cookie/cookie extraction.
- No customer, voice, billing, compliance, CRM, or production traffic through OmniRoute.
- No commit, push, or deploy.

## Loop amendment — 2026-07-13 provider safety hardening

Goal: Correct the stale local-gateway evidence and fail closed when synthetic or
customer PII is accidentally directed to the newly verified credential-free
providers.

Risk: Standard. This changes only the reusable provider privacy classifier; no route,
flag, credential, scheduler, or production deployment changes. Rollback is removing
the two provider identifiers from `_UNSAFE_PROVIDERS` while leaving `OMNIROUTE_ENABLED=0`.

File ownership: `app/platform/safe_ai_payload.py` (privacy classification),
`tests/test_safe_ai_payload.py` (red-first regression contracts),
`app/platform/omniroute_client.py` (truthful developer-state documentation),
`docs/omniroute/VERIFICATION_EVIDENCE.md` and `progress.md` (evidence ledger).

Tasks:
1. Add failing contracts that require PII rejection for `opencode` and `duckduckgo`.
2. Add only those two opaque no-auth gateway provider identifiers to
   `_UNSAFE_PROVIDERS`; do not alter approved direct-provider behavior.
3. Replace the stale claim that the local gateway has no admin/data-plane setup with
   the observed truth: it is authenticated locally but remains disabled in LeadGen.
4. Run the privacy, OmniRoute, and free-AI gate suites; then `prod_check.py`, secret
   scan, and a sanitized authenticated completion smoke. No routing/combos are created.

## Loop amendment — 2026-07-13 readiness-gate performance repair

Goal: Restore the deterministic `prod_check.py` frontend-wiring gate without changing
application routes or frontend behavior.

Risk: Trivial tooling-only. `scripts/deep_wiring_audit.py` keeps its existing route
matching semantics; only its dynamic-route regex compilation is cached. Rollback is
removing the cache decorator and returning to per-call compilation.

File ownership: `scripts/deep_wiring_audit.py` (compiled dynamic route matcher) and
`tests/test_deep_wiring_audit.py` (dynamic-route and cache contracts).

Tasks:
1. Add a failing contract that requires a compiled matcher cache while preserving a
   dynamic FastAPI-style route match.
2. Cache compiled dynamic-route patterns and use full matching in `route_exists`.
3. Run the new audit test, then `prod_check.py` with a 60-second bound, plus the
   OmniRoute privacy regression suite and secret scan.

## Loop amendment — 2026-07-14 Responses API adapter repair

### Goal and risk

Make the existing optional LeadGen OmniRoute adapter usable against the verified
OmniRoute 3.8.46 Responses API without changing any live LeadGen caller. This is a
**high-risk external-AI boundary**, mitigated by the existing default-off feature flag,
mandatory local API key, privacy classification, bounded retries, and no direct
provider-chain rewrite. Rollback is `OMNIROUTE_ENABLED=0` (the normal default) plus
reverting only the adapter and its tests.

### Evidence that motivates the change

- Current `POST /v1/chat/completions` is HTTP 404, while `POST /v1/responses` is live.
- Sanitized Groq and Mistral Responses calls returned their expected text.
- `gemini/gemini-2.5-flash` is catalogued but rejected upstream as retired; it is not
  eligible for the adapter registry.

### File ownership and exact tasks

| Path | Owner | Work | Proof |
| --- | --- | --- | --- |
| `app/platform/omniroute_client.py` | main session | Add a task registry, privacy-class admission, Responses API call, response validation, bounded retryable fallback, and safe structured result. | New isolated client contracts. |
| `tests/test_omniroute_client.py` | main session | Test default-off behavior, task/privacy rejection, response parsing, retryable fallback, and no fallback on non-retryable failures. | Focused pytest suite. |
| `docs/omniroute/{ARCHITECTURE,ROUTING_POLICY,PROVIDER_MATRIX,VERIFICATION_EVIDENCE}.md` | main session | Replace stale chat-endpoint/Gemini claims with current verified state and rollback notes. | Source review + runtime evidence. |
| `progress.md` | main session | Append only the final evidence block. | Fresh test/readiness output. |

The adapter will expose only `leadgen.coding_primary`, `leadgen.coding_fast`,
`leadgen.repo_analysis`, and `leadgen.test_generation`, all as
`INTERNAL_SANITIZED`. Customer, billing, compliance, telephony, destructive, and
`PROHIBITED_EXTERNAL` tasks are rejected. No scheduler, worker, route registration,
environment value, provider credential, or deployment file is edited.

## Loop amendment — 2026-07-14 local health and browser-bridge repair

Goal: make the local health signal time-aware and restore the bundled Chrome-control
runtime without changing provider credentials, production routing, or LeadGen flags.

Risk: Standard local tooling. Rollback is restoring the cached Chrome skill on the next
plugin refresh and reverting the healthguard script; the running gateway stays independent.

| Path | Owner | Work | Proof |
| --- | --- | --- | --- |
| `scripts/omniroute-healthguard.sh` | main session | Count only recent timestamped LiveWS connections, not arbitrary historical log lines. | Fixture-style shell contract and a live zero-client guard run. |
| `tests/test_omniroute_scripts.py` | main session | Lock the time-window contract against regression. | Focused pytest. |
| Chrome bundled `browser-client.mjs` | main session | Preserve the runtime-provided process shim when its property is non-redefinable. | Fresh Chrome runtime bootstrap and tab UAT. |
| `docs/omniroute/VERIFICATION_EVIDENCE.md`, `progress.md` | main session | Record only observed final evidence. | Fresh verification output. |

No `.env` value, credential, provider, production endpoint, scheduler, or LeadGen
feature flag is modified. The required 2 GB memory setting is retained only through the
verified non-secret `OMNIROUTE_MEMORY_MB=2048` launcher environment, then checked by
OmniRoute Doctor after restart.
