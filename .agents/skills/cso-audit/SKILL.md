---
name: cso-audit
description: Security + India-compliance audit (OWASP Top 10 + TRAI + DPDP). Use jab user bole "security audit karo", naya public endpoint/auth-route add ho, customer data ya payment handle ho, TRAI/DPDP/DLT compliance check chahiye, ya sensitive feature ko /ship karne se pehle. IDOR/SSRF/secret-scan/rate-limit + AI-disclosure/DND/consent checks built-in.
---

# Skill: cso-audit
**Adapted from gstack (CSO skill) by Garry Tan (YC) + India-specific additions. MIT License.**

## When to invoke
- "Security audit karo"
- Naya public endpoint add kiya
- Customer data handle hota hai
- TRAI/DPDP compliance check chahiye
- `/ship` se pehle (sensitive features)

---

## Phase 0: Stack + Attack Surface

```bash
# Public routes count
python scripts/prod_check.py 2>&1 | tail -3

# Auth-required routes
grep -rn "require_admin\|require_customer\|Depends(get_current" app/api/ | wc -l

# No-auth routes (PUBLIC — every one needs justification)
grep -rn "@router\.\(get\|post\|put\|delete\)" app/api/ | grep -v "require_admin\|require_customer\|Depends" | head -30

# Rate limits applied?
grep -rn "rate_limit\|RateLimiter" app/api/ | wc -l
```

---

## Phase 1: OWASP Top 10 Check

### A01 — Broken Access Control
- [ ] Har admin endpoint pe `require_admin` hai?
- [ ] Customer sirf apna data dekh sakta hai?
- [ ] `demo-client` fallback NAHI hai prod mein? (data.py fix check)

### A02 — Cryptographic Failures
- [ ] `.env` mein secrets hain, code mein nahi?
- [ ] `scripts/check_secrets.py` green hai?
- [ ] Passwords `pbkdf2-sha256` se hashed?
- [ ] JWT secret strong hai?

### A03 — Injection
- [ ] ORM use hota hai raw SQL ki jagah?
- [ ] User input file paths mein jaata hai? (path traversal risk)
- [ ] `/ai-img-file/{name}` regex-locked hai?

### A05 — Security Misconfiguration
- [ ] Debug mode OFF hai prod mein?
- [ ] Stack traces user ko nahi jaate?
- [ ] CORS properly configured?

### A06 — Vulnerable Components
```bash
pip list --outdated | grep -E "fastapi|uvicorn|sqlalchemy|pydantic" | head -10
```

### A07 — Auth Failures
- [ ] Login brute-force protection? (rate limit on `/api/admin/auth/login`)
- [ ] Session tokens expire karte hain?
- [ ] 2FA available hai (TOTP, `ADMIN_TOTP_SECRET`)?

### A10 — SSRF
- [ ] User-provided URLs fetch karta code? → whitelist/validate domain
- [ ] `web_extract.py` kya URLs sanitize karta hai?

---

## Phase 2: India-Specific Compliance

### TRAI Compliance
- [ ] AI disclosure greeting in voice calls? (`vobiz_stream.py`)
- [ ] DND check fail-CLOSED? (compliance.py)
- [ ] Call timing 9am-7pm enforced? (promo code-default; TRAI actual 9am-9pm)
- [ ] DLT registration pending? (kab tak manage without DLT?)
- [ ] 140-series number for promotional SMS?

### DPDP Act 2023
- [ ] Privacy policy updated with Access/Correction/Erasure rights?
- [ ] Grievance Officer contact mentioned?
- [ ] Consent collected before marketing calls? (`consent_ledger.py`)
- [ ] Opt-out INSTANT suppression working?
- [ ] Recording retention 90 days, then delete? (`RECORDING_RETENTION` flag)

### WhatsApp
- [ ] Auto-send gated behind `WHATSAPP_AUTO_SEND=1`?
- [ ] No baileys/unofficial API?

---

## Phase 3: Rate Limit Audit

```bash
grep -rn "rate_limit\|RateLimiter" app/ --include="*.py" | grep -v "#"
```

Har PUBLIC endpoint ke liye:
- `/api/public/*` → 10-15/60s ✓?
- `/api/growth/tools/*` → 20/60s ✓?
- `/api/ai/*` → 30/60s + auth ✓?
- `require_admin` pe rate limit karna zaroori nahi (auth hi guard hai)

---

## Phase 4: Secret Scan

```bash
python scripts/check_secrets.py --all 2>&1
```
Expected: 0 findings (nosecret comment = intentional exception).

---

## Phase 5: Report

```
## 🔒 Security Audit Report — [Date]

### Critical (fix before ship):
- [Issue] — [file:line] — Fix: [solution]

### High (fix this week):
- [Issue]

### Medium (backlog):
- [Issue]

### ✅ Passing:
- Auth: [N] admin endpoints protected
- Secrets: clean
- Rate limits: [N] applied
- TRAI disclosure: present

### TRAI/DPDP Status:
- [Compliant items]
- [Pending user action]
```
