# growth.py — Route Deletion Candidates (read-only analysis, 2026-06-14)

`app/api/growth.py` defines **158 routes** (prefix `/growth`) — the single biggest router (~24% of all routes). Cross-referenced against 329 files (frontend/*.html, app/, tests/).

- **Likely KEEP (referenced): 138**
- **CANDIDATES to review for removal: 20**

> Heuristic only. "No reference" can be a false positive when the frontend builds the URL dynamically (template strings). VERIFY each before deleting, then deprecate-behind-flag → prod_check.py + run_tests.bat → /ship → /health=production → delete in small batches.

## Candidates (review these first)

| Method | Path | Handler | Line | Why flagged |
|---|---|---|---|---|
| POST | /growth/whatsapp/flow/send | whatsapp_flow_send | 92 | no reference in frontend/app/tests |
| POST | /growth/sms/send | sms_send | 266 | no reference in frontend/app/tests |
| POST | /growth/tools/missed-call-revenue | tool_missed_call | 349 | no reference in frontend/app/tests |
| POST | /growth/tools/google-score | tool_google_score | 375 | no reference in frontend/app/tests |
| POST | /growth/sales/run | sales_run | 469 | no reference in frontend/app/tests |
| POST | /growth/revenue/dunning/case | dunning_open_case | 514 | no reference in frontend/app/tests |
| POST | /growth/optimizer/run | optimizer_run | 742 | no reference in frontend/app/tests |
| GET | /growth/optimizer/runs | optimizer_runs | 750 | no reference in frontend/app/tests |
| DELETE | /growth/webhooks/{webhook_id} | webhooks_remove | 893 | no reference in frontend/app/tests |
| POST | /growth/crm/test | crm_test | 1102 | demo/debug/test name |
| POST | /growth/notify/test | notify_test | 1148 | demo/debug/test name |
| POST | /growth/prospects/find-email-batch | prospects_find_email_batch | 1241 | no reference in frontend/app/tests |
| POST | /growth/content/reel-video | content_reel_video | 1556 | no reference in frontend/app/tests |
| GET | /growth/content/templates | content_templates | 1600 | demo/debug/test name |
| POST | /growth/revenue/client-report | client_report_build | 1661 | no reference in frontend/app/tests |
| POST | /growth/revenue/client-reports/run | client_reports_run | 1669 | no reference in frontend/app/tests |
| DELETE | /growth/client-keys/{hash_prefix} | client_key_revoke | 1696 | no reference in frontend/app/tests |
| GET | /growth/nps/request-drafts | nps_request_drafts | 1741 | no reference in frontend/app/tests |
| GET | /growth/skills/pack | skills_pack_list | 1900 | no reference in frontend/app/tests |
| GET | /growth/process/run/{run_id} | process_run_detail | 2090 | no reference in frontend/app/tests |

## Verification command per candidate

```bash
PATHS='/api/growth/<path>'   # one candidate
grep -rn "$PATHS" frontend/ app/ tests/ --include='*.html' --include='*.py' | grep -v 'app/api/growth.py'
# zero hits = safe-ish to deprecate; any hit = keep (it's called)
```

## Recommended approach
1. Start with the `demo/debug/test`-named candidates — usually safe one-off endpoints.
2. For `no reference` ones, run the grep above to rule out dynamic callers.
3. Group confirmed-dead into one deprecation commit (return 410 or remove), keep the diff small.
4. `python scripts/prod_check.py` + `scripts\run_tests.bat` (read pytest_run.log) → /ship → verify `/health`.
5. Repeat. Target: growth.py from 158 → ~79 routes; consider splitting what remains into themed routers (growth_infra / growth_revenue / growth_experiments).
