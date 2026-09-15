# Smartflo Account Escalation Email

**To:** support@cloudphone.tatateleservices.com / Smartflo Support (tatatelebusiness.com)
**CC:** aapka email
**Subject:** URGENT: Smartflo account showing INACTIVE – Click-to-Call API returns "Unable to process this request" for all calls

---

Dear Smartflo Support Team,

We are escalating an issue that is fully blocking our outbound AI voice calling on the Smartflo (Tata Tele Business Services) platform. We have completed extensive testing on our side and isolated the problem to the account level — kindly assist with activation/provisioning.

## 1. Account details

- **Account:** Smartflo demo account ("TATA DEMO 29...", portal: cloudphone.tatateleservices.com)
- **API token subject (sub):** 816673
- **Token status:** valid — issued 2026-09-08, expires 2026-12-07 (JWT verified)

## 2. Configuration verified on portal (all correct)

- **Click-to-Call Support API keys:** 2 keys, both Enabled, both bound to DID `918069879757`, destination **"LeadGen AI Voice Streaming" (Voice Streaming)**:
  - `c30ab34b-03cc-4df6-9fc7-0a7175c577e4`
  - `b5bcfb1c-acc9-468a-a21a-d1394ca6236d`
- **DID:** `918069879757` → assigned to LeadGen AI Voice Stream (Voice Streaming) — saved
- **Voice Streaming endpoint 2265:** Enabled, WSS URL exact (`wss://leadsgenai.in/api/telephony/smartflo/stream`)
- **IP Pool Whitelist:** `72.61.245.204` present in 4 pools (Extension/LeadGen AI Solutions)

## 3. The problem

Every Click-to-Call Support API request with a **valid** Bearer token and a **valid** API key returns:

```
HTTP 200
{"success": false, "message": "Unable to process this request"}
```

- The failure is exactly the same for **both** enabled API keys.
- It happens even when the customer number is invalid (8 digits) — i.e. we never get a parameter-validation error (a random/invalid key correctly returns `422 {"success":false,"message":"Invalid details provided."}`), which proves the key and token are being **authenticated**, then processing fails.
- No `ref_id` is ever returned, so no call is ever executed, no webhook is ever fired, no CDR is generated.

## 4. The critical finding (account inactive)

The management API `GET /v1/destinations` (authenticated with the same valid token) returns:

```
HTTP 200
{"success": false, "message": "Looks like your account is not active. Please contact our customer support team to activate your account."}
```

This strongly indicates the account itself is **not active / deactivated** on the platform, which would explain the generic execution-level rejection on every C2C request.

## 5. Action requested

1. **Activate the account** (or confirm current account status — the "extension" we applied on 2026-09-12 appears not to have activated it).
2. **Confirm the C2C → Voice Streaming destination is executable** for this account (entitlement for the "LeadGen AI Voice Streaming" destination type as the second leg).
3. **Fix the stale failover reference** on endpoint 2265 — its failover currently points at a **"Deleted Destination (Voice streaming)"**.
4. Provide an SR/ticket number so we can track.

## 6. Supporting facts

- Every C2C request is made exactly per the official documentation (`customer_number`, `api_key`, `async:1`, plus optional `caller_id`/`custom_identifier`; `Authorization: Bearer <token>` + `Content-Type: application/json`).
- Test timestamps (UTC): 2026-09-12 09:26Z, 09:31Z, and management-API probe 09:50Z.
- Business impact: total blockage of outbound AI voice calls via C2C; no calls placed, no billing incurred — but zero throughput since the account became unavailable.

Please activate the account and confirm the destination entitlement. Happy to provide any further logs or request details.

Best regards,
LeadGen AI Solutions
(Admin: leadsgenai.in · admin@leadsgenai.in)