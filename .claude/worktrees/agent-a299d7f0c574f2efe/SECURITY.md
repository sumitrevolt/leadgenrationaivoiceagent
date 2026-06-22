# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously at LeadGen AI. If you discover a security vulnerability, please report it responsibly.

### How to Report

1. **DO NOT** create a public GitHub issue for security vulnerabilities
2. Email security concerns to: **security@leadgenai.com**
3. Include the following in your report:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 24 hours
- **Initial Assessment**: Within 72 hours
- **Resolution Timeline**: Depends on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2 weeks
  - Low: Next release

### Security Measures in Place

#### Application Security
- [x] API key authentication for protected endpoints
- [x] Rate limiting (100 req/min per IP)
- [x] Input validation with Pydantic
- [x] SQL injection prevention (SQLAlchemy ORM)
- [x] XSS protection headers
- [x] CSRF protection
- [x] Secure session management

#### Infrastructure Security
- [x] HTTPS/TLS 1.2+ enforced
- [x] VPC with private subnets
- [x] Database with private IP only
- [x] Secrets in Google Secret Manager
- [x] Workload Identity for CI/CD
- [x] Container image scanning
- [x] Non-root container user

#### Data Security
- [x] Encryption at rest (Cloud SQL)
- [x] Encryption in transit (TLS)
- [x] DND registry compliance (India)
- [x] Call recording consent disclosure
- [x] PII handling guidelines

#### Monitoring
- [x] Security logging enabled
- [x] Anomaly detection alerts
- [x] Failed authentication tracking
- [x] Rate limit violation alerts

### Security Best Practices for Deployment

1. **Never commit secrets** - Use `.env.example` as template
2. **Rotate API keys** regularly (every 90 days)
3. **Use strong passwords** - Minimum 16 characters
4. **Enable 2FA** on all cloud accounts
5. **Review access logs** weekly
6. **Update dependencies** monthly

### Dependency Security

We use the following tools to monitor dependencies:
- `pip-audit` for Python vulnerability scanning
- `detect-secrets` for secret detection
- Dependabot for automated updates

Run security checks locally:
```bash
pip install pip-audit
pip-audit

# Check for secrets
detect-secrets scan
```

### Compliance

- **GDPR**: Data privacy controls implemented
- **TRAI DND**: Do-Not-Disturb registry integration
- **SOC 2**: In progress

---

Thank you for helping keep LeadGen AI secure!
