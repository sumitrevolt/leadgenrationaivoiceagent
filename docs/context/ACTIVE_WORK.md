# ACTIVE_WORK - max 3 workstreams

---

## WS-OKF1 Knowledge-stack polish (ADR-119 Phase-1) - IN PROGRESS
- **ID:** WS-OKF1
- **Business outcome:** Curated OKF readable + optional Qdrant ingest (flag OFF) — not a second RAG OS
- **Current state:** Code on `cursor/okf-knowledge-stack-polish-2026-08-05` — bundle loader, `/okf/`, admin dry-run/ingest gate
- **Next exact action:** Targeted tests + prod_check → PR → merge → deploy code-only (do **not** flip `OKF_INGEST_ENABLED` until owner arms)
- **Out of scope:** BGE-M3/hybrid sparse · replace Qdrant · voice · Safe Pack mutate · fake PAID

---

## WS-GTM1 Hot Queue → 2nd paid - CODE SHIPPED / REVENUE PENDING
- **ID:** WS-GTM1
- **Business outcome:** Real ₹1999 UPI → LEDGER_PAID → onboard once → first-value
- **Current state:** Prod `f0bdb4ee`. HQ=0 · paychase=0 · Estique=`removed`. Owner pick needed.
- **Next exact action:** After OKF ship (or parallel owner ops): pick real prospect → `/start` ₹1999 → approve → prove PAID
- **Out of scope:** fake PAID · Safe Pack with payment · #248 force

---

## WS-AM1 Safe Pack - SEPARATE / NOT THIS PATH
- **ID:** WS-AM1
- **Current state:** Keys may be =1; canary verification pending
- **Next exact action:** Only after LEDGER_PAID + owner canary gate
- **Out of scope:** payment-path env flips

---

## Parked
- WS-R3 Estique — `removed` (owner re-open only if intentional)
- #248 PR Factory Draft (CI fail)
