# Runbook — Security Incident

## Scenario
A leaked secret, suspected intrusion, abusive traffic, a DSAR/DPDP request, or a
dependency CVE that needs urgent triage.

## Standing controls
- **Secrets:** only in `.env` (gitignored); `scripts/check_secrets.py` is a CI gate
  (false positive → `nosecret` on the line). Never in committed files / CLAUDE.md / scripts.
- **AuthZ:** RBAC (`require_admin` / `require_super_admin` / module-grants), customer
  TOTP 2FA, IDOR closed on billing (`_authed_client_id`).
- **Edge:** `PlanTierRateLimitMiddleware` (60/200/500 rpm by tier, `PLAN_RATE_LIMIT`),
  SSRF block on `/site-audit` (private IPs), webhook signatures **fail-closed in prod**.
- **Host:** fail2ban + unattended-upgrades active; Sentry armed (`SENTRY_DSN`).
- **Owner:** Arnav (Security/Compliance agent) — DPDP/TRAI posture, secret-rotation
  reminders, CVE triage; Aryan — dependency CVEs (pip-audit, never auto-upgrade).

## Immediate Response
1. **Leaked secret:** rotate it immediately at the provider, update VPS `.env`, recreate
   the affected container. Treat the old value as compromised even if "only" in a private repo.
   ```bash
   git rm --cached <file>   # if committed; then rotate regardless
   ```
2. **Active intrusion / abuse:** identify source IP, block via fail2ban / firewall,
   preserve logs (do not wipe), check `fail2ban` jail status.
3. **DSAR / DPDP erase request:** use the agent-memory DPDP purge + consent-ledger
   suppression to honor it; log the request.

## Diagnosis
- Scope: what did the secret/credential grant access to? What is the blast radius?
- Confirm no secondary leakage (logs, error reports, Sentry breadcrumbs).
- For a CVE: is the vulnerable package on the hot path? `pip-audit` (Aryan's tool).

## Recovery
1. Rotate all potentially-exposed credentials, not just the one found.
2. Patch/upgrade the vulnerable dependency (lock-file pinned, `requirements.lock.txt`
   refresh via `scripts/vps_freeze.sh`), deploy, verify.
3. Run `python scripts/check_secrets.py` → exit 0 before declaring clean.

## Post-Incident
- RCA: how did it leak / how did they get in. Add the gap to `security-review` skill checklist.
- Regression: `tests/test_billing_auth_idor.py`, `test_impersonation.py`,
  `test_chatbot_guardrails.py`, `test_feature_flags.py`.
- Record as ADR; if customer data was involved, follow DPDP breach-notification duty.
