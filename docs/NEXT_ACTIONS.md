# Next Actions - LeadGen AI

> Action list for the next AI session. Start with Graphify; avoid full repo re-audit unless the graph or handoff docs are stale.

## Start Commands
```powershell
scripts\graphify_refresh.bat
graphify query "What is Product One customer delivery flow?" --graph app/graphify-out/graph.json --budget 1200
graphify query "Which admin/customer dashboard flows are incomplete or disconnected?" --graph app/graphify-out/graph.json --budget 1200
graphify query "What are the highest priority blockers before real customer delivery?" --graph app/graphify-out/graph.json --budget 1200
```

## Priority 1 - ADR-064 Batch Finalization - DONE
Local HEAD now includes ADR-064 follow-up fixes through `5503256`. Targeted tests are green, `prod_check.py` passes, API docs are in sync, and local revenue contract checks pass.

Verified:
- `/api/admin/delivery-cockpit` returns real `revenue.mrr_total`, `paying_customers`, and `by_plan`.
- `/api/customer/delivery-proof` is IDOR-safe through `require_customer`; tests are green.
- Admin sidebar is simplified; customer "My Delivery" tab exists.
- `automation_log_service` is wired into `team_scheduler._run_job()` with start/finish rows, DB-down JSONL fallback, and never-raise behavior.
- `013_add_automation_logs` migration shape is verified locally against the `AutomationLog` model.

## Priority 2 - Automation Log Wiring Decision - DONE
`automation_log_service` remains a passive helper but is now written from `team_scheduler._run_job()` on dispatch and finish. Append-only start/finish rows with `start_log_id` correlation are sufficient for now; no update-by-id API is required yet.

## Priority 3 - Customer Delivery UX Proof - DONE
- `GET /api/customer/delivery-proof` returns flattened `approvals_pending` fields.
- Published/approved rows read canonical `post_published` and `post_approved` ledger events.
- Empty state is honest; no fake sample data.

## Priority 4 - Delivery Command Center Revenue - DONE
- Backend returns `revenue.mrr_total`, `paying_customers`, and `{Plan: {count, mrr}}` in `by_plan`.
- Frontend plan pills read `b.mrr` and `b.count`, and tolerate legacy numeric `by_plan` values.

## Priority 5 - API Docs Sync - DONE
`docs/API.md` was synced to 1072 ops via `scripts/sync_api_docs.py`; `prod_check.py` confirms API docs are in sync.

## Next Highest Priority
1. **Customer Delivery tab live QA** - login as jiya-makeover on `/app/customer`, click "My Delivery", and verify progress bar, approval cards, 1-click approve/reject, and published proof render.
2. **Social setup delivery-stage proof** - confirm `_sync_social_delivery_stage()` fires on wizard save and `social_setup_completed` appears in the delivery timeline.
3. **Automation Logs UI** - consider surfacing `/api/admin/automation-logs` in admin dashboard; the API exists but there is no operator panel yet.

## Do Not Do Yet
- Do not deploy without explicit user approval.
- Do not resume `EMAIL_WARMUP`.
- Do not enable WhatsApp auto-send or platform dial.
- Do not merge broad dirty worktrees blindly.
- Do not add Graphify to runtime dependencies.

## End-Of-Session Checklist
1. Run targeted tests and gates.
2. Update `docs/AI_HANDOFF.md`.
3. Update `docs/CURRENT_STATE.md` if state changed.
4. Update `docs/NEXT_ACTIONS.md`.
5. Refresh Graphify:
   ```powershell
   scripts\graphify_refresh.bat
   ```
6. Append `progress.md` Loop Run if this was Loop Engineer work.
