# ADR-146 — `INTERACTION_LOG=0` silently freezes the lead pipeline

- **Date:** 2026-07-26
- **Status:** ACCEPTED (defect recorded, fix deferred to its own atomic PR)
- **Severity:** LATENT — production currently has `INTERACTION_LOG=1` (verified read-only 2026-07-26)
- **Labels:** `MISLEADING_SAFETY_FLAG` · `PIPELINE_STATE_COUPLED_TO_TELEMETRY_FLAG` ·
  `BLOCKS_SAFE_USE_OF_INTERACTION_LOG=0`

## The defect

`app/platform/interaction_log.py` gates on `INTERACTION_LOG` at line 47-48 and returns
**before both writes**:

```
INTERACTION_LOG=0
  -> return {"skipped": "INTERACTION_LOG off"}
  -> no JSONL write
  -> no Postgres write
  -> AND no Lead.mark_contacted("outreach")   (:144-150)
```

`mark_contacted()` is not telemetry. It performs the `new -> contacted` lead
transition **and** writes the `lead_status_history` row in the same commit. So a
flag whose name promises "logging" also owns a required pipeline state change.

Turning it off would silently freeze every lead at `status='new'` for as long as
it stayed off, with no error, no alert, and no backlog — the touches simply never
get recorded as having happened. Recovery would require a backfill against a
JSONL that was also never written.

## Why this is not a P0 today

Production has `INTERACTION_LOG=1`. The defect is reachable only by an operator
who believes they are disabling logging. That belief is exactly what makes it
worth recording: the flag's name actively invites the mistake.

## Why it is not fixed here

The Runtime-Data Foundation PR is about *where mutable state lives*. Changing
what a flag controls is a behavioural change to the lead pipeline and belongs in
its own atomic change-set with its own tests.

## Required fix (separate PR)

Separate the two concerns:

```
interaction persistence policy   (optional, flag-controlled)
lead lifecycle transition        (required, always runs)
```

Optional logging must never suppress a required state change. Suggested shape:

- keep `INTERACTION_LOG` governing the JSONL/DB persistence only;
- hoist `mark_contacted()` above the flag check, or move it to the caller;
- add a test asserting that with `INTERACTION_LOG=0` an outbound touch **still**
  promotes `new -> contacted` and still writes `lead_status_history`.

## Related

- `communications.interactions` is classified `DUAL_WRITE_DRIFTED`
  (`app/platform/runtime_data_manifest.py`) — neither the DB nor the JSONL may be
  deleted, and neither can be rebuilt from the other.
- No production flag was changed while recording this.
