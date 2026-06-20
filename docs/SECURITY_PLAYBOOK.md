# Security Playbook — LeadGenAI

> **Updated:** 2026-06-20 · **Related:** [`SECRETS_MANAGEMENT.md`](SECRETS_MANAGEMENT.md) · [`ADMIN_RBAC_DESIGN.md`](ADMIN_RBAC_DESIGN.md) · DPDP in `/privacy`

---

## 1. Principles

1. **Secrets never in repo** — only `.env` (gitignored); `scripts/check_secrets.py` in verify loop
2. **Fail-closed in production** — webhook signatures, DND, billing IDOR
3. **Least privilege** — RBAC via `/app/team-access`; customer JWT scoped to own `client_id`
4. **DPDP Act 2023** — consent ledger, 90-day retention, purge APIs

---

## 2. Access control

| Role | Auth | Scope |
|------|------|-------|
| **Super admin** | `/app/admin-login` JWT | Full platform |
| **Sub-admin** | Team access RBAC | Module-scoped |
| **Customer** | `/app/login` JWT | Own client_id only |
| **Public** | Rate-limited | `/api/public/*`, mini-sites |
| **API keys** | `X-API-Key` + plan tier RPM | MCP product, integrations |

Enforcement: `require_admin` · `require_customer` · `_authed_client_id` on billing mutations.

UI: `/app/team-access` · Skill: `backend-rbac`, `team-access-ops`

---

## 3. Secret management

| Secret type | Storage | Rotation |
|-------------|---------|----------|
| DB password | VPS `.env` `POSTGRES_PASSWORD` | Manual + pg backup |
| JWT / admin | `.env` `SECRET_KEY`, `JWT_*` | On compromise |
| Vobiz / Groq / Mistral keys | `.env` | Provider dashboard |
| UPI VPA | `.env` or `data/platform_upi.json` | Business change |
| Customer webhook HMAC | Per-client in DB | UI rotate |
| Stripe | `.env` international only | Stripe dashboard |

**Future:** SOPS+age or Infisical — see `INFRA_HARDENING_GUIDE.md` (not deployed).

**Never:** commit secrets to CLAUDE.md, scripts, or docs (use placeholders).

---

## 4. Network & infra

| Control | Status |
|---------|--------|
| TLS | Caddy on VPS |
| fail2ban | Active |
| unattended-upgrades | Active |
| Optional WAF | Cloudflare Tunnel (`CLOUDFLARE_TUNNEL_TOKEN`) |
| Plan rate limits | `PLAN_RATE_LIMIT=1` — Starter 60 / Growth 200 / Advanced 500 rpm |
| SSRF guard | `/site-audit` blocks private IPs |

---

## 5. Application security

| Area | Control |
|------|---------|
| Billing IDOR | `_authed_client_id` on all mutations (2026-06-16 audit) |
| Webhooks | Twilio/Vobiz/WhatsApp signature verify; prod 503 if secret unset |
| Turnstile | `TURNSTILE_*` optional bot gate on public forms |
| Customer 2FA | TOTP (`customer` portal) |
| Impersonation | Admin-only, audit-logged |
| SQL | SQLAlchemy ORM; raw SQL only in ops scripts with timeouts |

Agent: **Arnav** (`SECURITY_AGENT=1`) — daily posture + CVE triage proposals via Vikram.

---

## 6. Telephony & compliance (legal security)

| Gate | Behavior |
|------|----------|
| DND | Lookup fail → promotional **BLOCK** |
| Calling hours | 10am–7pm IST promotional |
| AI disclosure | Wired in greeting |
| Opt-out | Press-9 / consent ledger → instant suppress |
| Foreign trunks | India-domestic = **illegal** — Vobiz only domestic |

**Never disable compliance code** for convenience.

---

## 7. Incident response

### Severity levels

| Sev | Example | Response time |
|-----|---------|---------------|
| **S1** | Site down, DB lost | Immediate — `OPERATIONAL_RUNBOOKS` RB-001 |
| **S2** | Celery flood, LLM 429 storm | <1h — RB-003, circuit breaker |
| **S3** | Single feature 500 | <4h — logs + hotfix |
| **S4** | Suspicious login | Review audit log |

### Steps

1. **Detect** — Kavya/Hermes watchdog, Sentry (`SENTRY_DSN`), ntfy alerts
2. **Contain** — stop worker, `del celery` if flood, disable flag
3. **Eradicate** — patch + targeted tests
4. **Recover** — deploy loop, health 2× verify
5. **Post-mortem** — append to `SESSION_LOG.md` + runbook footer

On-call (solo founder): Sumit · escalate via ntfy → phone push.

---

## 8. Data privacy (DPDP)

| Right | Implementation |
|-------|----------------|
| Consent | `consent_ledger.py` |
| Access/export | Admin APIs + client request |
| Erasure | `agent_memory` purge + anonymized audit hash |
| Retention | Call recordings 90 days default |

Public policy: https://leadsgenai.in/privacy

---

## 9. Security verification checklist

```bash
python scripts/check_secrets.py      # no leaked keys in repo
python scripts/prod_check.py         # wiring + routes
# Optional: Trivy image scan in CI
curl /api/activation/readiness       # probe blockers
```

---

## 10. Reporting vulnerabilities

Email: admin@leadsgenai.in · Subject: `[SECURITY]` — do not disclose publicly until patched.
