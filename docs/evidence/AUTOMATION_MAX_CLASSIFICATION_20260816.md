# Automation-Max classification — 2026-08-16

Source: current runtime posture, deploy smoke, queue/DLQ checks, and automation tests in PR #381/#382 lineage.

## Summary

This is an operational classification, not a flag-arm request. Default posture stays conservative: compliance gates, owner approval boundaries, tenant isolation, DND/DLT/consent, and cold-WhatsApp restrictions must not be weakened.

| Area | Classification | Evidence / reason | Safe action |
|---|---|---|---|
| Public funnel pages | KEEP | `/`, `/audit`, `/site-audit`, `/demo`, `/pricing`, `/start` smoke 200 after deploy. | Monitor conversion and cache freshness. |
| Manual UPI path | KEEP | `/api/public/pay-info` smoke 200; UPI/billing truth tests green. | Owner-confirmed bank credit remains required. |
| Authenticated Hot Queue | KEEP | Route/tests green; browser owner E2E still recommended. | Run authenticated browser check. |
| DSH runtime execution | INERT | Runtime/shadow flags OFF; direct executor authority. | Do not arm without owner promotion and canaries. |
| Swara/Ananya DSH migration | FROZEN | Hard-coded frozen identities; contract tests assert RED/hard-off. | Never route through DSH. |
| Cold/bulk WhatsApp automation | KILL | Ban/compliance risk; sales autopilot WhatsApp flag remains off. | Keep off unless explicit compliant path exists. |
| Voice/calling campaign | FIX | Voice kill engaged for safe deploy; compliance gates preserved. | Owner decides if/when to disengage kill switch and run canary. |
| Plugin runtime catalog | FIX | Tests/CI green, but final live catalog probe was inconclusive. | Fix probe and publish inventory. |
| API docs sync | FIX | prod_check reports endpoint index out of date. | Run docs sync in environment with FastAPI deps. |
| Dependency alerts | FIX | Dependabot open alerts remain. | Patch in separate scoped PRs. |
| Queue/DLQ health | KEEP | `celery=0`, `dlq:failed_tasks=0`, `dlq:dead=0` after deploy. | Continue deploy-gate checks. |

## Promotion rule

Only promote from FIX/INERT to KEEP/SCALE after: tests green, runtime evidence captured, owner approval if external/compliance/revenue-impacting, and rollback documented.
