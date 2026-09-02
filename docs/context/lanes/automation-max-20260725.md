# Lane — Automation-Max + Harness Blueprint (2026-07-25)

## Done (prod)
- User chose safe-only (#1): flipped OPS_WATCHDOG, CADENCE_ENGINE, JOURNEY_ENGINE, APPROVAL_EMAIL_NOTIFY
- NEVER left OFF: WHATSAPP_AUTO_SEND, PLATFORM_DIAL_DAILY, REPLY_AUTO_SEND, SALES_AUTOPILOT_ENABLED
- Skew incident: recreate without APP_VERSION → `:latest` → rolled back to `441cf37a` same session

## Done (repo / this PR)
- Pin-safe VPS flag scripts (ADR-097)
- Agent Harness Standard skill + harness-conformance-auditor (Master Blueprint governance)
- Workforce doc truth: 11 Claude subagents / 31 STAFF

## Do not
- Auto-approve paid-client content
- Enable cold email without deliverability check
- Recreate compose without APP_VERSION pin
