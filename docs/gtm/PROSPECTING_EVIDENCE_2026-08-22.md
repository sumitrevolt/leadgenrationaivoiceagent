# Prospecting Evidence — 2026-08-22 (visible-browser + engineering session)

Evidence labels: LOCAL-DEMO | PRODUCTION-PROVEN | DIRECT_HOST_VERIFIED | CODE-PRESENT | GIT_VERIFIED | UNKNOWN

## What was verified (live host, DIRECT_HOST_VERIFIED 2026-08-22 ~18:07–18:22Z)
- `/health` = `healthy`, `environment:production`, SHA `2e292d07`.
- `/health/deep`: db 3.7ms, redis ok, llm configured (groq head), telephony vobiz, disk 50% free, cpu 30%, workers 4/4.
- Money path renders in a real browser (`agent-browser` v0.34.0): `/` → `/pricing` (plan cards + CTAs) → `/start` → `/audit` (lead-capture form). Screenshots: `docs/gtm/_hermes_pricing_live.png`, `_hermes_audit_live.png`, `_hermes_start_live.png`.
- `/start` is a deliberate alias of `/pricing` (`app/main.py:1882`), and "Shuru karo" opens the UPI QR modal (`app/config.py:180` `upi_vpa`) — by design, not a defect.

## Verification gate
- `scripts/prod_check.py` → **ALL CHECKS PASSED** (1336 routes, 51 pages 0 wiring gaps, 0 automation gaps).
- `tests/test_billing_truth_2026.py` → **green (15/15)**.

## Prospecting run (LOCAL-DEMO — read-only scrape, no outreach, no billing)
Tool: `scripts/run_prospect.py` → `prospector.run_prospecting()` (the same function the daily job runs).

| Run | Source | Queries | New | Duplicates | no_phone | Result |
|---|---|---|---|---|---|---|
| Default targets, limit=4 | `osm_overpass` | 3 | 0 | 0 | 0 | 3 empty — first/default target `solar installer` is NOT in `_OSM_TAG_MAP` → `name~` fallback → 0 on Indian OSM. |
| Mapped target `restaurant`, Pune+Mumbai, limit=5 | `osm_overpass` | 2 | **5** | 0 | 4 | **WORKED**. 5 real businesses (Copper Chimney, Cafe Andora, TIBBS Frankies, Good Luck Restaurant, A1 Bakery), 1 with a phone (`+912226422250`, type `fixed`). |

Files written: `data/prospects.jsonl` (5 rows, gitignored). This is the **local checkout** store — NOT the live VPS pipeline (that store lives on the host, reachable only via SSH/deploy). So: demonstration of a working compliant source, NOT a live-pipeline fill.

## Genuine finding (CODE-PRESENT — deferred, not the revenue blocker)
`app/platform/prospector.py` `_OSM_TAG_MAP` (line ~337) does NOT map several **default** prospect targets. Defaults (`_DEFAULT_TARGETS`, line ~145): `solar installer`, `real estate agency`, `coaching institute`, `interior designer`, `dental clinic`, `beauty salon`, `restaurant`, `gym fitness`.
- Mapped: real_estate (`office="estate_agent"`), dental (`amenity="dentist"`), beauty (`shop~"^(hairdresser|beauty)$"`), restaurant, gym, interior/boutique/pharmacy/hotel, etc.
- **NOT mapped → name-fallback → ~0 on Indian OSM:** `solar installer`, `coaching institute` (+ any keyword not in the map).
- **Impact:** the free OSM fallback starves exactly the first/primary solar target that `_DEFAULT_TARGETS` exercises first, so daily runs on default targets are heavily throttled even though the free source works for mapped niches. `PROSPECT_MAX_LOOKUPS`/`PROSPECT_MAX_QUERIES`/time-budget guards all worked (no runaway).

### Why deferred (BACKLOG with reason, not fixed now)
1. This is a **live production repo currently mid-parallel-work** (working tree already has ~25 modified files from an in-flight DSH migration, per `git status`). Adding to a chronically dirty tree risks stepping on the other session (AGENTS.md anti-mistake rules R7, R9, R12).
2. A code fix would require rebuild + **owner-gated deploy** (kill-fence + `deploy_vps.sh`). Deploy is explicit user-auth — not this session's call.
3. **It is not the revenue blocker.** Per the repo's own CURRENT_STATE verdict: the bottleneck is owner execution (UPI bind + bank-credit confirm = `ready_for_first_paid_customer=false`, `blocker_count=1`, `payments_ready=true`), and `paid_today=0`. Adding OSM tag mappings would let the free source return more *leads*, but it would NOT create a customer on its own.

Fix suggestion (when an owner-authorized engineering sprint is appropriate): add `("solar", ...)` and `("coaching", "tuition", ...)` filters to `_OSM_TAG_MAP` and re-run the daily target set — small, additive, test-covered (`tests` for `_osm_filters`).

## Anti-fabrication note
No leads, conversations, meetings, payments, or revenue were invented. All numbers above are real outputs of the running code against real endpoints/stores. `ready_for_first_paid_customer=false`, `paid_today=0`, and the single real paying customer remains **jiya-makeover** (₹1,999 MRR). The owner-gated UPI/bank-confirm unlock is unchanged and untouched.
