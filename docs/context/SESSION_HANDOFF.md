# SESSION_HANDOFF — 2026-08-12 (Cursor: PR #333 AUTH-MERGE DONE)

## Status
**31-AGENT BUS SETUP PARTIAL** — PR #333 **MERGED**. Comb NIP-OA `auth_tag=null` WAIT accepted (not COMPLETE).

| Field | Value |
|---|---|
| PR | https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/333 — **MERGED** |
| Merge commit | `760649429839d885656f1565de44f4cc875f5c34` |
| Tip merged | `e2bdd81ff37a93ef031e8e500b14e5b379fced17` (includes `d4accbd3` staff_bus + runtime-data classify/pin after CI ratchet) |
| Owner tip note | Named tip `97f6009b` superseded by required-CI fix commits `82bc4666` + `e2bdd81f` |
| Flag | **`STAFF_BUS_ENABLED` OFF / inert** — do not arm |
| Deploy | **None** — do not run `deploy_vps.sh` for this |

## GO / WAIT / NO-GO (post-merge)
| Gate | Result |
|---|---|
| Hosted relay NIP-11/HTTPS | **GO** |
| Local :3100 | **GO** |
| Boss / Fizz / Honey / Bumble harness + auth_tag | **GO** |
| Comb identity + correlated reply | **GO** |
| Comb Desktop NIP-OA auth_tag | **WAIT** (owner accepted) |
| Roster 31 / bus contracts / 31/31 synthetic | **GO** |
| Control 5/5 correlated | **GO** |
| Required CI on merge tip | **GO** (Gate A non-required FAILURE ignored) |
| Prod deploy / flag arm | **NO-GO** (by design this packet) |

## Rollback (do not execute unless merge wrong)
- `git revert 76064942` on main
- Runtime: `STAFF_BUS_ENABLED=0` / unset

## Optional owner-only next
Comb Desktop Save → mint NIP-OA `auth_tag` → re-declare **COMPLETE** (not required now).

## Do not
- Deploy / arm `STAFF_BUS_ENABLED` / Boss governance flags in prod
- Remint/export keys; invent STAFF identities
- Touch UPI / WA / email / calling / voice / prod DB
