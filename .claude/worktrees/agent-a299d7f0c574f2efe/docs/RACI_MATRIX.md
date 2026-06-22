# RACI Matrix — LeadGenAI

> **Context:** Solo founder (Sumit) + AI staff automation · **Updated:** 2026-06-20
> **Legend:** **R** = Responsible · **A** = Accountable · **C** = Consulted · **I** = Informed

---

## 1. Platform operations

| Activity | Sumit (Human) | AI Staff | Customer |
|----------|---------------|----------|----------|
| Deploy / VPS | **A/R** | Hermes/Kavya monitor **I** | — |
| Incident response | **A/R** | Kavya/Hermes detect **R** | **I** if client-facing |
| Secrets / `.env` | **A/R** | Arnav remind **C** | — |
| Backup / DR | **A** | Pranav verify **R** | — |
| Pricing change | **A/R** | — | **I** |
| DLT / Vobiz paperwork | **A/R** | Tara status **C** | **I** |

---

## 2. Product & engineering

| Activity | Sumit | Vikram | Guru | Arjun/Meera |
|----------|-------|--------|------|-------------|
| Feature code | **A/R** | Propose **C** | Skills **C** | QA voice **C** |
| Bug fix | **A/R** | Propose patch **C** | — | Repro **C** |
| godfile refactor | **A/R** | — | — | — |
| Voice tuning | **A** | — | — | **R** test |
| Security audit | **A** | — | — | Arnav **R** |

---

## 3. Revenue & sales

| Activity | Sumit | Rohan | Nikhil | Client |
|----------|-------|-------|--------|--------|
| Cold outreach | **A** | **R** (draft+send cap) | **I** | — |
| Reply handling | **A/R** approve send | Triage **R** | **I** | — |
| UPI payment verify | **A/R** | — | **I** | Pay **R** |
| Plan activation | **A/R** | — | Record **I** | **I** |
| Dunning / churn | **A** | — | **R** | **I** |
| Sales close | **A/R** | Cadence draft **C** | **I** | Respond **C** |

---

## 4. Client delivery (marketing)

| Activity | Sumit | Isha/Dev | Neha | Client |
|----------|-------|----------|------|--------|
| Onboarding | **A** | Auto **R** | **I** | Provide info **R** |
| Content creation | **A** | **R** draft | — | Approve/post **R** |
| Mini-site / widget | **A** | FDE **R** | — | Embed **R** |
| Lead routing | **A** | LD engine **R** | Rescore **R** | Team **R** |
| Support tickets | **A/R** | — | — | Raise **R** |

---

## 5. Voice / telephony

| Activity | Sumit | Swara/Tara | Compliance code |
|----------|-------|------------|-----------------|
| Outbound campaigns | **A** | Execute **R** | Gate **R** |
| DND / hours / disclosure | **A** (policy) | — | **R** enforce |
| Provider recharge | **A/R** | Tara monitor **I** | — |
| Call QA | **A** | — | Arjun **R** |

---

## 6. Compliance & legal

| Activity | Sumit | Arnav | System |
|----------|-------|-------|--------|
| TRAI/DND policy | **A/R** | Audit **C** | Enforce **R** |
| DPDP / privacy | **A/R** | Review **C** | Ledger **R** |
| GST invoicing | **A** | Vidya **C** | Auto **R** if flagged |
| WhatsApp policy | **A/R** | — | No bulk **R** |

---

## 7. Decision escalation

```
AI draft → Sumit approve → execute
AI detect critical → ntfy/email → Sumit **A** within 4h
Compliance block → never override without **A** + documented reason
```

---

## 8. When team grows (future humans)

| Role to hire first | Takes over **R** from |
|--------------------|----------------------|
| Sales rep | Rohan send (keep AI draft) |
| CS / onboarding | Sumit activate + training |
| DevOps | Sumit deploy (Pranav stays audit) |

Matrix review: quarterly or at 10+ paying clients.
