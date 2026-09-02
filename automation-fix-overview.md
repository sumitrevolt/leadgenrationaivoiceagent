# Automation Setup Fix — Overview

## Summary
Comprehensive audit and fix of all automation setup issues in the LeadGen AI Voice Agent project, with MX (email verification) configuration prioritized first.

## Issues Found & Fixed (15 files modified)

### 1. MX Email Verification Configuration (Priority)
**Problem:** The MX verification flags `OUTREACH_VERIFY_MX` and `OUTREACH_SELECT_SKIP_MX` were used in `auto_outreach.py` but missing from the `automation_flags.py` registry — a wiring gap that the `automation_wiring_audit.py` script would flag as "declared-but-not-connected."

**Fix:**
- Registered both flags in `app/api/automation_flags.py`
- Added `OUTREACH_SELECT_SKIP_MX` to `app/platform/setup_status.py` FLAGS dict
- Fixed `email_verify.py` docstring to accurately reference the `check_deliverability` parameter

### 2. MCP Server Path Mismatch
**Problem:** All 6 MCP server paths in `.mcp.json` pointed to `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\` (original repo) instead of the current worktree path.

**Fix:** Updated all paths to `C:\Users\Ratanshila\WorkBuddy\Worktrees\leadgenrationaivoiceagent\main-aececa33\`

### 3. Stale Makefile Targets (Cloud Run → VPS)
**Problem:** `deploy-staging` used `gcloud run deploy` (Cloud Run) but project moved to Hostinger VPS. Three `setup-secrets*` targets referenced GCP Secret Manager. `test-coverage` used macOS-only `open` command.

**Fix:** Replaced with `scripts/deploy_vps.sh`, `.env`-based instructions, and cross-platform commands.

### 4. Gatus ntfy Alerting Gap
**Problem:** The ntfy last-resort alerting block in `gatus.yaml` was commented out, and the observability compose file didn't pass `NTFY_*` env vars — meaning if Prometheus went down, Gatus could detect issues but couldn't push alerts.

**Fix:** Uncommented the alerting block and added `NTFY_URL`, `NTFY_TOPIC`, `NTFY_TOKEN` environment variables to the gatus container.

### 5. Celery Beat Schedule Issues
**Problem:** 
- `process-voice-followups` (production-critical voice callback drain) was filtered out by the legacy beat gate
- 3 scheduling conflicts where multiple `run_staff_job` tasks fired at the same minute

**Fix:** 
- Added `_KEEP_KEYS` set to preserve critical non-staff tasks through the legacy filter
- Offset 3 conflicting schedules: finops (09:00→09:05), security (09:30→09:35), readiness-digest (08:30→08:35)

### 6. CI Workflow & Script Path Issues
**Problem:**
- ISSUE-237 diagnostic step in `tests.yml` was still running despite being falsified
- 5 Python scripts and `run_wiring_gaps.py` had hardcoded paths to the old repo location

**Fix:** Removed the diagnostic step, made all script paths relative using `__file__`-based resolution.

## Validation
All 9 modified Python files pass `py_compile`. All YAML/JSON files validate as well-formed.
