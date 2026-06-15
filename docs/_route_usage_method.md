# Finding genuinely-dead routes — the right method (2026-06-14)

## Why static analysis is NOT enough
Cross-referencing route paths against the codebase flagged ~157 of 593 API routes as "no literal URL reference." That number is **not** a dead-route list:
- The frontend builds many URLs dynamically (`fetch(\`/api/${x}/${id}\`)`) — no literal to match.
- Webhooks, the MCP server, mobile/external API clients, and cron/curl callers live outside this repo.
- The only 2 routes matching a "debug/test" name (`/api/ai/ab-test-variant`, `/api/ml/ab-test`) are actually A/B-testing **features**, not junk.

So: **there is no reliable static "safe to delete" batch.** Deleting on static signals alone risks breaking live endpoints.

## The reliable method: real traffic
1. On the VPS, point the tool at your access log (uvicorn/Caddy), ideally >=30 days:
   ```bash
   python scripts/route_usage_audit.py --access-log /opt/leadgen/logs/access.log
   ```
   It prints every route with **0 hits** = real deprecation candidates.
2. If you have route-labeled Prometheus metrics, equivalently:
   ```promql
   sum by (handler) (increase(http_requests_total[30d])) == 0
   ```
   (or query Loki for the access-log stream).
3. For each 0-hit route: final grep (`grep -rn "<path>" frontend/ app/ tests/ scripts/ | grep -v app/api/`), then deprecate-behind-flag or remove.
4. Gate every batch: `python scripts/prod_check.py` + `scripts\run_tests.bat` (read pytest_run.log) -> `/ship` -> verify `/health`=production. Keep diffs small.

## Getting from 593 -> ~400 routes
Pure dead-route removal (0-hit) will only get part of the way. The rest is a **product decision**: retire whole legacy/duplicate feature areas (e.g. superseded marketing experiments, abandoned tool endpoints), not individual orphan handlers. Use the 0-hit data + the static starting points in `docs/_route_candidates_all.md` to drive those calls.

## Files
- `scripts/route_usage_audit.py` — traffic-based 0-hit finder (run on VPS).
- `docs/_route_candidates_all.md` — static starting points (review only, not delete-on-sight).
- `docs/AI_FIRSTIFY_REENGINEER_PLAN.md` — overall phased plan.
