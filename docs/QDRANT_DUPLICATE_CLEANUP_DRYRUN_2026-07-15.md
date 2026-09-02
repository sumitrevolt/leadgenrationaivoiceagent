# Qdrant Historical Duplicate Cleanup — Dry Run Report

**Date:** 2026-07-15
**Scope:** Non-destructive audit only. No deletion has been executed.
**Instance:** production Qdrant (`leadgen_qdrant`, `http://qdrant:6333`, accessed via `leadgen_app`'s bare `QdrantClient`, bypassing the embedder per ADR-104 addendum #6)

## Headline finding: the ~215,000 premise does not match current production state

The brief for this task assumed approximately 215,000 historical duplicate points were sitting in
Qdrant awaiting cleanup. Live measurement shows this is no longer accurate:

| Collection | Points |
|---|---|
| `kb_main` (the niche/catalog KB collection) | **1,481** |
| `agent_memory` | 10 |
| `code_index` | 0 |
| `llm_semantic_cache` | 56 |
| **Total, all collections** | **1,547** |

There is no collection anywhere near 215,000 points in this Qdrant instance. This is almost
certainly because earlier work in this same session (`app/voice_agent/kb_loader.py`'s
duplicate-vector-write fix, plus `replace_source=True` delete-before-reseed runs across the
niche catalog — the same mechanism that collapsed `solar_residential` from 1,674 points, ~185x
duplicate bloat, down to 9) already resolved the large-scale duplication this task was written
to address, before this dry-run was run. Rather than force the original number to match reality,
this report states the true, current, measured count.

## What duplication actually remains (measured, not estimated)

Scanned all 1,481 points in `kb_main` (full scroll, payload-only, no vectors loaded).
Deterministic duplicate-identification criteria: two points are duplicates of each other iff
they share the exact same `(namespace, source, text)` triple (SHA-1 fingerprint of the
concatenation, collision-negligible at this volume).

- **Unique fingerprints:** 1,473
- **Duplicated fingerprints:** 7
- **Extra duplicate points** (points beyond the first/canonical copy of each fingerprint): **8**

Every single duplicated fingerprint is confined to two namespaces:

| Namespace | Source | Duplicated fingerprints | Extra points |
|---|---|---|---|
| `ab:ragquality` | `ab_gate` | 6 | 7 |
| `ab:ragtest` | `ab_seed` | 1 | 1 |

These namespaces are written by `app/platform/eval_hub.py`'s `run_rag_ab_gate()` (backing an
admin endpoint in `growth_deliverability.py`), which calls `scripts/rag_retrieval_ab.py` to
A/B-test retrieval strategies. Each manual/admin-triggered run of this quality gate reseeds its
test namespace without first deleting the prior run's points — a minor duplicate-write pattern
in an internal QA/test harness, not customer or catalog data.

**Proof of exclusion (required by the brief):**
- **Zero** duplicated fingerprints appear in `_global` or in any of the 39 real niche-catalog
  namespaces (`solar_residential`, `insurance`, `ai_marketing`, `home_loans`, etc.).
- **Zero** duplicated fingerprints appear in any customer/client-scoped namespace
  (`client:<id>` pattern) — none were present in the scan at all.
- All 8 extra points are in `ab:ragquality`/`ab:ragtest`, both test-harness namespaces owned by
  an internal RAG quality-gate tool, never served to a real customer or a live voice call.

## Retained vs. deleted (exact point IDs, ready for review — not yet executed)

For each duplicated fingerprint, the **first-encountered point ID is retained** (canonical copy);
all later IDs sharing the same fingerprint are the deletion candidates:

| Fingerprint (short) | Namespace | Keep (canonical) | Drop (duplicates) |
|---|---|---|---|
| `df07a21be4ad` | ab:ragquality | `0c54070c-361a-5be4-ab3c-af2a00ebbb6b` | `e6a6e099-2164-4d48-832b-9190c3e6c4fd` |
| `ea3a0cfb889b` | ab:ragquality | `111b3ab5-9a90-518f-a107-b64d112c2358` | `450f4c6f-fb5a-4c9c-9e9e-7805a134758d`, `a870bf1f-1685-4205-a6ea-18de6b57adc7` |
| `f49bc13997ca` | ab:ragquality | `357291d2-c89a-4c81-ab5e-1dc72e0008e1` | `9ff5d624-9a21-534b-a0e5-25c7a85d2c21` |
| `1df386f90e64` | ab:ragquality | `4d012ae5-858b-5ae9-be6b-cfd18cf7e3e1` | `51da46e5-011c-4cda-8154-bc5571b039eb` |
| `5b7a96305ca9` | ab:ragquality | `531c04e8-4a79-5a1b-a215-336f63c004b5` | `7ac06641-a726-4ecc-ae83-8e386c728920` |
| `759ce6691241` | ab:ragquality | `5bcad415-4b13-56b7-83c7-7ee7bf72c994` | `e54603b0-4df8-4eab-bdae-e21a65425703` |
| `4877dc02a5d7` | ab:ragtest | `617fd6f4-2027-5c94-aafc-0e8324ff1b7d` | `d401da52-a431-4067-bd66-03a0e0d2f336` |

Total points proposed for deletion: **8**. Total points retained catalog-wide: **1,473** (unchanged).

## Expected storage/performance benefit

Negligible. 8 points out of 1,481 (0.5% of the collection) in test-harness namespaces that are
never queried by a real customer request or a live voice call. This is a hygiene action, not a
performance or storage fix — there is no meaningful benefit to production latency, memory, or
disk from removing these 8 points. (The earlier, much larger cleanup — collapsing
`solar_residential` from 1,674 to 9 points — already captured the real storage/performance win
this task was originally scoped to find.)

## Operational risk

Effectively zero. `ab:ragquality`/`ab:ragtest` are internal admin-triggered RAG quality-gate test
namespaces (`run_rag_ab_gate()`), never read by the customer-facing voice/reply path
(`TelecallerBrain._kb_facts()` only ever queries a real niche namespace or `_global`, never an
`ab:` prefixed one). Deleting these 8 points cannot affect any live call, any customer's KB
content, or the `_global` shared namespace.

## Backup / recovery strategy

Before executing any deletion: `qdrant` supports point-level retrieval by ID, so the 8 payloads
+ vectors can be dumped to a local JSON file first via `client.retrieve(collection_name="kb_main",
ids=[<drop_ids>], with_vectors=True)` (bounded, 8 points, trivial size). Given these are
disposable test-harness artifacts regenerated by re-running the RAG gate, a full Qdrant snapshot
is not necessary for an action this narrow — but the existing rclone→Google Drive offsite backup
(already LIVE, restore already proven per this project's standing infrastructure) covers the
collection as a whole regardless.

## Exact scoped deletion command (not executed)

```python
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

client = QdrantClient(url="http://qdrant:6333", timeout=15)
drop_ids = [
    "e6a6e099-2164-4d48-832b-9190c3e6c4fd",
    "450f4c6f-fb5a-4c9c-9e9e-7805a134758d",
    "a870bf1f-1685-4205-a6ea-18de6b57adc7",
    "9ff5d624-9a21-534b-a0e5-25c7a85d2c21",
    "51da46e5-011c-4cda-8154-bc5571b039eb",
    "7ac06641-a726-4ecc-ae83-8e386c728920",
    "e54603b0-4df8-4eab-bdae-e21a65425703",
    "d401da52-a431-4067-bd66-03a0e0d2f336",
]
client.delete(
    collection_name="kb_main",
    points_selector=qmodels.PointIdsList(points=drop_ids),
)
```

This deletes exactly the 8 listed point IDs — no filter-based bulk delete, no namespace-wide
delete, no risk of touching an ID outside this explicit list.

## Post-cleanup verification plan

1. `client.get_collection("kb_main").points_count` must read **1,473** (1,481 − 8).
2. Re-run the duplicate-detection scan above — `duplicated_fingerprints` must be **0**.
3. Per-namespace count for `ab:ragquality`/`ab:ragtest` should each drop by their respective
   counts, confirming no other namespace was touched.
4. Confirm all 5 app-image containers remain healthy with no restart (this operation touches
   only Qdrant, never a container).
5. Optional: a quick `/api/voice/niches` smoke check, though the voice path never reads `ab:`
   namespaces so no functional regression is expected.

## Approval question

Approximately **8** duplicate Qdrant points are ready for scoped production cleanup. The dry run
excludes customer/contextual data and retains one canonical copy of each catalog record — in this
case all 8 duplicates are confined to an internal RAG quality-gate test namespace
(`ab:ragquality`/`ab:ragtest`), not real niche-catalog or customer content. **Note that this is
far smaller than the ~215,000 originally assumed** — that number does not match current
production state; the true count is 8. Approve production cleanup?

---

## EXECUTION EVIDENCE — 2026-07-15 (approved and executed same session)

Approved by the user with explicit safety requirements (delete only the 8 verified points,
restrict to the internal test namespace, retain one canonical copy each, never touch
customer/catalog/`_global`/Jiya/other-tenant data, record before/after counts, verify
collection+app health, abort if live scope differs from approved scope, append rather than
overwrite this report).

**Script:** `scripts/qdrant_dedupe_cleanup_2026-07-15.py` — hardcodes the exact 7 approved
fingerprint→(keep, drop-ids) pairs from this report, re-scans production `kb_main` live,
aborts with no deletion if the live drop-id set doesn't exactly equal the approved set or if
any drop id falls outside `ab:ragquality`/`ab:ragtest`, then deletes via an explicit
`qmodels.PointIdsList(points=DROP_IDS)` — never a filter-based or namespace-wide delete.
Executed via `docker exec leadgen_app python /tmp/qdrant_dedupe_cleanup_2026-07-15.py`.

**Pre-execution baseline (unchanged from dry-run):**
- `kb_main.points_count` = 1481, `status` = green
- All 5 app-image containers + `leadgen_qdrant`: healthy, app uptime 36m (no restart pending)
- `/health` → 200, `version: 5f65979c`

**Live revalidation (before deleting anything):**
- Live duplicate fingerprints: **7** (matches approved: 7)
- Live extra/duplicate point count: **8** (matches approved: 8)
- Live drop-id set == approved drop-id set: **True** — exact match, proceeded
- All 8 drop ids confirmed confined to `ab:ragquality`/`ab:ragtest` — no scope drift

**Deletion executed:** explicit `PointIdsList` delete of exactly these 8 ids —
`450f4c6f-fb5a-4c9c-9e9e-7805a134758d`, `51da46e5-011c-4cda-8154-bc5571b039eb`,
`7ac06641-a726-4ecc-ae83-8e386c728920`, `9ff5d624-9a21-534b-a0e5-25c7a85d2c21`,
`a870bf1f-1685-4205-a6ea-18de6b57adc7`, `d401da52-a431-4067-bd66-03a0e0d2f336`,
`e54603b0-4df8-4eab-bdae-e21a65425703`, `e6a6e099-2164-4d48-832b-9190c3e6c4fd`.

**Post-execution counts and verification:**

| Check | Before | After | Result |
|---|---|---|---|
| `kb_main.points_count` | 1481 | 1473 | delta = 8, exactly as expected |
| `kb_main.status` | green | green | unchanged |
| Duplicate fingerprints remaining | 7 | **0** | fully resolved |
| Canonical (keep) points present | — | **7/7** | all retained copies confirmed still present |
| `solar_residential` namespace count | 25 | 25 | **unchanged** |
| `insurance` namespace count | 25 | 25 | **unchanged** |
| `ai_marketing` namespace count | 27 | 27 | **unchanged** |
| `home_loans` namespace count | 25 | 25 | **unchanged** |
| `_global` namespace count | 379 | 379 | **unchanged** |
| `ab:ragquality` namespace count | 13 | 6 | −7, matches approved scope |
| `ab:ragtest` namespace count | 5 | 4 | −1, matches approved scope |
| `/health` | 200, `5f65979c` | 200, `5f65979c` | unchanged |
| App container | Up 36m, healthy | Up 36m, healthy | **no restart occurred** |
| Qdrant container | Up 6d, healthy | Up 6d, healthy | **no restart occurred** |

**Outcome:** exactly the 8 approved points deleted, nothing else. No customer, catalog, `_global`,
Jiya, or other-tenant data touched. No container restart, no OOM, no app degradation. Cleanup
complete and fully verified.
