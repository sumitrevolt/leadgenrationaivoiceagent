# Skill Observation Log

Observations captured during task-oriented work. Each entry identifies a potential skill improvement or new skill opportunity.

**Status key:** OPEN = not yet actioned | ACTIONED = skill updated/created | DECLINED = user decided not to pursue

---

## 2026-09-21 — TypeSafe/Telegram production verification

### Observation 1: Distinguish network-unreachable from credential-invalid
**Status:** OPEN
**Type:** internal

**Issue:** `scripts/typesafe_status.py` maps a probe with no HTTP status plus a network/proxy error to `INVALID`, even though the same credential succeeds when network access is available. This can incorrectly trigger key-rotation work.

**Suggested improvement:** Add a distinct `UNREACHABLE`/`INDETERMINATE` probe result (or preserve `PRESENT` with a network warning) and test the blocked-network case separately from HTTP 401/403.

**Principle:** Credential validity may be concluded only from an authentication response; transport failure is an availability result, not an authentication result.

## 2026-09-22 — TypeSafe collection-ranking verification

### Observation 2: Collection ranking needs one typed judgment per item
**Status:** OPEN
**Type:** internal

**Issue:** A single batch-level `Score` was copied to every Hot Queue row. The integration made a real TypeSafe call, but the judgment could not distinguish items, so deterministic bonuses—not TypeSafe—performed the actual ranking.

**Suggested improvement:** Add a collection-pattern rule to the TypeSafe skill: use independently keyed questions (for example, `item_<idx>_score`) within one bounded request, map each answer back to its item, cap the candidate set, and test that opposing per-item answers can reverse the deterministic baseline.

**Principle:** A typed call is operational only when its output can change the downstream item it claims to judge; one batch answer copied across a collection is not item-level intelligence.
