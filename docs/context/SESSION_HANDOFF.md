# SESSION_HANDOFF — 2026-08-12 (Cursor: PR #333 AUTH-MERGE review pack)

## OWNER REVIEW CARD — AUTH-MERGE PR #333

| Field | Value |
|---|---|
| PR | https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/333 |
| State | **Draft** · OPEN · base `main` |
| Exact head | `d4accbd31397d6621faf45ac12915266beefcd5b` (`d4accbd3`) |
| Diff scope | `app/platform/staff_bus/*` · `scripts/staff_bus_canary.py` · `tests/test_staff_bus_2026_08_12.py` · `STAFF_BUS_ENABLED` flag registry · runbook/evidence · SESSION_HANDOFF/progress — **no UPI/voice/prod env** |
| Declaration | **31-AGENT BUS SETUP PARTIAL** (owner-accepted WAIT below) |

### Merge checklist (owner)
1. Confirm Draft → Ready only after reading this card.
2. AUTH-MERGE exact SHA `d4accbd3…` (normal merge; no squash/bypass if policy forbids).
3. **Do not arm `STAFF_BUS_ENABLED` in prod without separate AUTH** — flag stays OFF/inert after merge.
4. **Do not deploy** under this packet.
5. Optional later: Comb Desktop Save → mint NIP-OA `auth_tag` → re-declare COMPLETE (not required for this merge).

### Rollback
- Code: close/revert PR or `git revert d4accbd3`.
- Runtime: leave / set `STAFF_BUS_ENABLED=0` (unset = inert).
- No prod DB / customer outbound / payment surface in this diff.

### GO / WAIT / NO-GO
| Gate | Result |
|---|---|
| Hosted relay NIP-11/HTTPS | **GO** (recheck 200) |
| Local `:3100` | **GO** (recheck 200) |
| Boss / Fizz / Honey / Bumble harness + auth_tag | **GO** |
| Comb identity + Cursor harness + correlated reply | **GO** |
| Comb Desktop NIP-OA `auth_tag` | **WAIT** — **owner ACCEPT as WAIT** (reply already SUCCESS; mint deferred) |
| Roster 31 / 7-team / Comb ∉ STAFF | **GO** |
| Bus contracts + 31/31 synthetic | **GO** (`254971bb491b`) |
| Second Brain + Boss enforcement | **GO** |
| 5/5 control correlated (`CNY20260812104913-63660547`) | **GO** |
| Protected side-effects / secrets / prod mutate | **GO** (zero) |

### Evidence pointers
- `docs/evidence/STAFF_BUS_20260812.md`
- `docs/runbooks/STAFF_BUS_31.md`
- Tests: `tests/test_staff_bus_2026_08_12.py` (7 passed)
- Prod read-only last probe: `/health` `9c47647c` production (untouched by this work)

## Done
- Staff bus package + Draft PR #333 @ `d4accbd3`
- 31/31 synthetic + 5/5 control canaries
- Owner accepted Comb `auth_tag=null` as WAIT for merge-readiness

## Do not
- Merge/deploy without owner AUTH-MERGE
- Arm `STAFF_BUS_ENABLED` / `BOSS_DECISION_GOVERNANCE` in prod without AUTH
- Remint/export keys; invent Boss/STAFF identities
- Touch UPI / WA / email / calling / voice / prod DB

## Owner decision needed (pick one)
**A)** `AUTH-MERGE #333` now @ `d4accbd3` (PARTIAL accepted), **or**
**B)** Desktop Comb Save → `auth_tag` mint first → then COMPLETE + AUTH-MERGE
