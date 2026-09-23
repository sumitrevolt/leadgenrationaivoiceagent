# TATA SmartFlo Live Test Call — 2026-09-23

**Status**: TEMPLATE — awaiting real test execution
**Author**: MiniMax-M3 (Mavis root session `mvs_e7426ec2280e4984bb6524705c20a20c`)
**Related TypeSafe decisions**: mm-telecom-001, mm-tata-hotqueue-006
**Compliance predecessor**: ADR-156 (Platform Dial LIVE), ADR-148 (Foreign Trunks Illegal)
**Deadline**: TATA SmartFlo API Authorization header **MANDATORY 30 Sep 2026** (7 days from today)

---

## 0. Purpose

Verify **before 30 Sep 2026** that the production TATA SmartFlo click-to-call path is still
working end-to-end. Code claim verified at `app/telephony/tata_smartflo_handler.py:90-100`
(`Authorization: Bearer {api_token}` always sent). Live confirmation requires a real call.

## 1. Required inputs (PENDING — owner directive)

- [ ] **TATA Console URL** (typically `https://console.smartflo.tatateleservices.com/`)
- [ ] **Login credentials / SSO** (owner-provided; **never** paste into repo)
- [ ] **Test destination phone number** (owner cell for one-ring confirmation is fine)
- [ ] **TATA SmartFlo plan confirmation** (Pro Plan ₹1,250/license per `tata_smartflo_handler.py:5`)
- [ ] **Preferred test window** — *must avoid 9am-7pm promo window*; pick 11:00 or 17:30 IST slot

## 2. Pre-call code-verification checklist

- [x] `app/telephony/tata_smartflo_handler.py:42` — endpoint correct
- [x] `app/telephony/tata_smartflo_handler.py:90-100` — Auth header always sent
- [x] `app/telephony/compliance.py:278` — TATA_SMARTFLO_DID env-driven
- [x] `app/telephony/compliance.py:444` — 9am-7pm promo window enforced
- [x] `app/utils/dnd_checker.py:334` — TELEPHONY_PROVIDER=tata_smartflo canonical
- [x] Vobiz REMOVED 2026-09-18 (per `compliance.py:258`)
- [ ] `.env` has valid `TATA_SMARTFLO_API_TOKEN` — **REQUIRES VPS-UP** (NOT YET VERIFIED)
- [ ] `.env` has valid `TATA_SMARTFLO_API_KEY` (C2C-support specific key) — **REQUIRES VPS-UP**
- [ ] `TATA_SMARTFLO_DID` is the correct display DID — **REQUIRES VPS-UP**

## 3. Verification probe (already executed this session)

| Probe | Result | Meaning |
|---|---|---|
| `curl -m 10 https://leadsgenai.in/health` | `curl: (28) Operation timed out after 10001 milliseconds with 0 bytes received, HTTP_CODE=000` | VPS unreachable from my network. "VPS UP at 2962d26e" claim from task message is **unverifiable / false** from here. |
| `git rev-parse --verify 2962d26e` | `2962d26ebad52cb1f3448b26c5680031f0d59fb9` | Commit exists in local repo. May or may not be deployed; deployment state cannot be probed while VPS unreachable. |
| `memory/decisions.md` tail | ADR-4 to ADR-1 (oldest entries) | No new ADR-202 granting autonomous TATA test / hot-queue drain authority. |

## 4. Test call execution record (TO BE FILLED AFTER REAL CALL)

**Call time (IST)**: TBD
**From DID**: TBD
**To number**: TBD
**Endpoint called**: `https://api-smartflo.tatateleservices.com/v1/click_to_call_support`
**HTTP method**: POST (form-encoded per Smartflo docs)
**Caller IP**: TBD (VPS egress)

### 4.1 Request (capture real headers — redact bearer token value)

```
POST /v1/click_to_call_support HTTP/1.1
Host: api-smartflo.tatateleservices.com
Authorization: Bearer <REDACTED>
Content-Type: application/x-www-form-urlencoded

api_key=<REDACTED>&from=<DID>&to=<NUMBER>&ref_id=<call_id>
```

### 4.2 Response (capture real)

- **HTTP status**: ___
- **Response time (ms)**: ___
- **ref_id returned**: ___
- **Smartflo call status (async, via webhook)**: ___
- **Error message (if any)**: ___
- **CDR / portal screenshot path**: ___

## 5. Failure diagnosis matrix

| Possible cause | Check |
|---|---|
| Auth token expired/regenerated | Verify `TATA_SMARTFLO_API_TOKEN` matches TATA portal → reset in `.env` |
| Wrong API key type | Smartflo uses different keys for different endpoints; C2C-support endpoint requires the **C2C-support** specific key, not the general API key |
| Network firewall | Check VPS egress to `api-smartflo.tatateleservices.com:443` (should be open by default) |
| Rate limit | TATA SmartFlo Pro allows bursty within Pro plan; check `X-RateLimit-*` headers in 429 response |
| Compliance gate blocked | `dial_gate.py` rejects if DND unverified; verify test number is in consent ledger as non-DND |
| API endpoint deprecated | TATA portal "Developers → API Reference" should match `tata_smartflo_handler.py:42` |
| Premature mandatory-Auth deadline | TATA portal may flip auth-optional → auth-required EARLIER than 30 Sep |

## 6. Post-success next steps

1. Capture screenshot from TATA portal showing the test call in CDR (redact number if not owner's)
2. Update `memory/decisions.md` with new ADR: `TATA_LIVE_TEST_VERIFIED_20260923`
3. Resolve the `TATA_AUTH_MANDATORY_30SEP2026` flag carried in mm-telecom-001
4. Schedule 2nd confirmation test post-30 Sep (regression check after the deadline flips)
5. Update `OPERATIONAL_PLAYBOOK` with the verified endpoint + token rotation cadence

## 7. Post-failure next steps

1. Diagnose per §5 matrix; capture full request/response with redacted token
2. Update `memory/decisions.md` with `TATA_TEST_FAILED_20260923_<cause>` ADR
3. If auth token expired: owner resets in TATA portal, regenerates `.env`, redeploys
4. If deadline is approaching (<3 days): escalate to owner for emergency test call

## 8. Hard fail-closed stance

If owner credentials / test phone number / VPS access are NOT provided by **27 Sep 2026 18:00 IST** (3 days before mandatory deadline):

- Escalate to owner-channel (Telegram) for manual test call execution
- Recommend owner personally runs test call from TATA portal before deadline
- Do NOT fabricate test-call results — production dial going silent on 30 Sep would cost more than admission of "test not yet executed"

## 9. Related hot-queue drain (PHASE 3 of task)

**Held** pending:
- VPS recovery + DB access via `docker exec leadgen_db psql`
- Owner directive on which 3 customers + which plan (Starter ₹1,999 / Growth ₹2,999 hidden / Advanced ₹5,999 per `packages.py` truth — NOT the stale task-template spec)
- Manual UPI rail per ADR-158 — no fabricated transaction IDs

Real UPI transaction IDs will only be reported from `data/upi_payments.json` after real customers pay.

---

🐦 pelican
