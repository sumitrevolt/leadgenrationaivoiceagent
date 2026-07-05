---
name: data-retention-dpdp
description: DPDP Act 2023 data-retention + deletion runbook — consent ledger, 90-din recording retention, agent_memory purge, per-store delete (Postgres/Qdrant/Redis/logs/backups/Obsidian), customer data-deletion request handling. Use jab customer "mera data delete karo" bole, retention policy audit ho, DPDP compliance check ho, ya naya data-store add ho.
---

# Data Retention & DPDP (delete ka matlab HAR store se delete)

> Enterprise audit skill. DPDP Act 2023 rights + Grievance Officer `/privacy` me live. **Sabse common enterprise fail = "DB se delete kiya, backup/vector-store/logs me zinda hai".** Pehle `context-first`.

## Repo truth
- **Consent ledger** (`consent_ledger.py`): opt-out → INSTANT cross-channel suppression + **90-din recording retention**. Press-9 opt-out persisted (H2).
- **Agent memory purge (F.4)**: `agent_memory` inspect + DPDP purge — consent-ledger bridge wired.
- **DND fail-CLOSED** (TRAI): lookup fail = promotional block. Yeh retention ka cousin — consent state = compliance-critical data, KABHI casually delete mat karo (legal defense record hai).

## Data map (kahan-kahan personal data rehta hai)
| Store | Personal data | Retention | Delete path |
|---|---|---|---|
| Postgres (leads, clients, calls, invoices) | naam/phone/email/GST | active + legal (invoices 8yr GST) | SQL delete/anonymize per client_id |
| Qdrant `kb_main` (`client:<id>` ns) | client KB docs, lead context | client active tak | namespace filter delete |
| Redis | call state, cache, queues | transient (TTL) | TTL confirm; explicit del on purge |
| `data/` files (recordings, ai_images, obsidian_staging) | voice recordings = PII! | **recordings 90d ENFORCED?** verify job exists | cron purge + spot-check |
| Logs (Loki + container) | phone numbers in call logs? | Loki retention config check | PII-masking in log lines (best) |
| Backups (pg dumps 30d, data/ 7d offsite) | sab kuch | 30d/7d rolls off NATURALLY — deletion request me customer ko yeh window batao | document, roll-off wait |
| Obsidian brain (Leads/, github private repo) | qualified lead notes | indefinite — GAP! | purge script me include karo |
| Sentry | request context | Sentry retention (~90d) | PII-scrub config |

## Deletion request runbook (DPDP right)
1. Verify requester = data principal ya authorized (customer portal auth / email verify).
2. **Consent/opt-out records EXEMPT rakho** (suppression list me phone rehna CHAHIYE warna dobara call ho jayega = worse violation). Invoices = GST legal hold.
3. Purge sweep: Postgres anonymize → Qdrant ns delete → Redis keys → `data/` recordings/files → Obsidian notes → agent_memory purge (F.4).
4. Backups: naturally roll off (30d) — request log me note + date.
5. Evidence: deletion log entry (kya, kab, kaun) — yeh khud minimal-data ho (id, not content). 30-din SLA se pehle confirm to requester.

## Quarterly retention audit
1. Upar data-map walk — naya store aya? (naya feature = naya row, warna map jhootha).
2. Recording 90d purge job LIVE verify (file dates spot-check `data/` me).
3. Loki/Sentry retention config vs table match.
4. `/privacy` page text vs actual practice diff — drift = dono me se ek fix.

## Output
Data-map current · deletion runbook evidence · 90d recording purge proof · gaps shipped (Obsidian purge, log masking) · DPDP readiness /100.

## Related repo skills
`leadgen-voice-compliance` (consent/TRAI) · `tenant-isolation-audit` (per-tenant scope) · `dr-restore-drill` (backup windows) · `leadgen-security-rbac` (PII lens).
