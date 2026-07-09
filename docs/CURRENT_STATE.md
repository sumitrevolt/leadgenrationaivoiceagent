# Current State - LeadGen AI

> Short current-state handoff for AI sessions. Code remains source of truth; this file is the reasoning/status layer.

## Date
2026-07-09

## Main Business Focus
Product One / AI Automated Marketing customer deliverability. The immediate goal is making real paid customers see clear delivery proof: onboarding, content, approvals, publishing proof, reports, admin cockpit, and automation logs.

## Graphify State
- Graphify is dev-only and configured through `.mcp.json`.
- Main graph path in this repo: `app/graphify-out/graph.json`.
- Main report path: `app/graphify-out/GRAPH_REPORT.md`.
- Current graph report: around 14k nodes and 25k edges; latest local HEAD after ADR-064 follow-up fixes is `5503256`.
- God nodes from the latest report include `User`, `Lead`, `_ctx()`, `VobizStreamSession`, `LLMBrain`, `VectorStore`, `TelecallerBrain`, `DataService`, and `CallManager`.

## Product One Delivery State
- Customer proof route exists: `GET /api/customer/delivery-proof`.
- Customer approval routes exist under `/api/customer/approvals/*`.
- Delivery ledger canonical post events are:
  - `post_draft_created`
  - `post_approved`
  - `post_published`
  - `post_failed`
- New customer Delivery view exists in `frontend/customer_dashboard.html`; backend/tests are verified, remaining work is live human eyeball QA.
- Delivery Command Center revenue display reads `data.revenue` and the plan breakdown shape now matches frontend expectations.
- Content approval lifecycle helpers now persist scheduled/published/failed states and write valid ledger proof events (`post_approved`, `post_published`, `post_failed`) in local verified code.
- Admin automation logs endpoint remains admin-gated; tests now explicitly prove unauthenticated access is blocked and mocked admin access returns logs.
- Scheduler automation-log wiring now avoids fake `running` rows for admin-paused jobs; paused jobs log `skipped/admin_paused`, enabled jobs log `running` plus finish with `start_log_id`.
- Delivery Command Center revenue plan breakdown now returns/render `{count, mrr}` per plan. Frontend also tolerates legacy numeric `by_plan` values.
- AutomationLog Alembic migration now aligns with the SQLAlchemy model for default/nullability/index naming; isolated temp SQLite upgrade verified table + indexes.

## Worktree Warning
ADR-064 code fixes are committed locally through `5503256`, but the worktree still has documentation changes and untracked helper/test files. Never use `git add -A`; stage exact files only if the user asks for commit.

## Safety State
- No deploy performed by this cleanup pass.
- No `.env` changes.
- No outbound send/call/post automation enabled.
- Compliance gates remain unchanged.
- `EMAIL_WARMUP` remains paused.

## Last Verified Gate
Latest local gates from this session:
- 42 focused Product One / automation-log tests passed
- 46 focused Product One / automation-log / scheduler tests passed after scheduler fix
- Latest 46 focused Product One / automation-log / scheduler tests passed after Delivery Command Center revenue fix
- 45 earlier customer-dashboard/delivery tests passed
- Ruff clean for touched Python files
- `prod_check.py` PASS with API docs in sync at 1072 ops
- `check_secrets.py` clean
- `git diff --check` clean
- Alembic single head `013_add_automation_logs`
- Isolated temp SQLite `alembic upgrade head` succeeded; filtered drift check has no `automation_logs` entries, though legacy repo-wide Alembic drift remains noisy.
