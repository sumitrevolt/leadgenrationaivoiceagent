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
