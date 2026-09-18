## Summary

Migrate TypeSafe integration from obsolete HTTP endpoints to the canonical **System One API contract**.

## Root Cause

The existing `typesafe_integration.py` called obsolete endpoints:
- `POST /choice`
- `POST /noul`
- `POST /score`
- `GET /health`

These all return **HTTP 404** against the current TypeSafe API.

The official TypeSafe SDK source confirms the current contract:
- Base URL: `https://api.typesafe.ai` (NOT `/v1` suffix)
- Endpoint: `POST /v1/systemone`
- Payload: `{model, state, questions}`
- Response: `{model, answers, usage}`
- Choice/Noul/Score are **question types** inside `questions`, not separate HTTP paths.
- Default model: `jev-latest`

## Semantic Fix

### New API Contract
- `TypeSafeClient.system_one(state, questions)` — canonical entry point
- `Choice`, `Noul`, `Score` — question primitive builders
- Compatibility wrappers: `typesafe_choice()`, `typesafe_noul()`, `typesafe_score()` — delegate to `system_one`
- No separate `/choice`, `/noul`, `/score`, `/health` HTTP calls remain

### Fail-Closed Guard
- Missing `TYPEsafe_API_KEY` → ZERO HTTP calls
- `initialize()` returns `TypeSafeResponse(success=False, error="INERT: ...")`
- `system_one()` / `choice()` / `noul()` / `score()` all return inert when key absent

### Model Configuration
- Default: `jev-latest`
- Configurable via `TYPESAFE_MODEL` env var
- Resolved at client construction time (not module import time)

## Scope

**2 files changed:**
1. `app/platform/typesafe_integration.py` — full System One migration (~220 lines)
2. `tests/test_typesafe_jev_latest_model.py` — 12 focused tests (new file, replaces `test_typesafe_jevlATEST_model.py`)

**Changes:**
- ~220 insertions, ~100 deletions
- No new dependencies
- Backward-compatible public API (`typesafe_choice`, `typesafe_noul`, `typesafe_score` still work)

## Test Status

12 focused tests covering:
- Fail-closed: no key → zero HTTP calls (initialize, system_one, choice, noul, score)
- Default model = `jev-latest`
- Model override via env var
- Exact URL: `https://api.typesafe.ai/v1/systemone`
- Payload shape: `{model, state, questions}`
- Question type serialization: `type=choice`, `type=noul`, `type=score`
- Compatibility wrappers parse answers correctly
- No old endpoint strings in source
- Secret scan clean

All tests mock `requests.post` — no live API calls.

## CI Status

- Gate A: PENDING (branch just pushed)
- Required checks: `Lint + syntax + secrets`, `prod_check + pytest`, `harness real-redis integration`
- Secret scan: GREEN (no keys in source)

## Live Smoke Test Evidence (2026-09-18)

```
Endpoint: POST https://api.typesafe.ai/v1/systemone
Requested model: jev-latest
HTTP status: 200
Resolved model: jev-1.13.0
Latency: 1.04s
Response keys: ['model', 'answers', 'usage']
Noul (has_enough_evidence): 0.85
Choice (next_workstream): hot_queue_followup (confidence: 0.78)
```

**Status: `TypeSafe jev-latest API VERIFIED`**

## Deployment Acceptance

- No deployment risk — fail-closed guard is backward compatible
- Existing callers already treat `success=False` as "judgment unavailable"
- Activation requires owner to:
  1. Rotate TypeSafe API key (key in git history `7317f990`)
  2. Set `TYPEsafe_API_KEY` in VPS `/opt/leadgen/.env`
  3. (Optional) Set `TYPESAFE_MODEL=jev-latest` — already default

## Rollback

Revert commits in this PR. Safe because:
- No schema migration
- No config change
- No API surface change (backward-compatible wrappers)

---
**PR #521** — TypeSafe System One API contract migration.
**Not a model rename only** — the entire HTTP contract has changed.
**Live verified:** `POST https://api.typesafe.ai/v1/systemone` returns HTTP 200 with `jev-latest`.
