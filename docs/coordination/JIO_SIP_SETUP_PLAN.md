# Jio Mobile SIP Trunk — Setup Plan (2026-08-27)

> Status: **IN-NEGOTIATION with Sai Service Centre (provider, +91 90293 41515, Indiamart lead). Plan locked; awaiting provider reply with KYC docs + SIP creds + activation timeline.**

## Why Mobile SIP Trunk (not Standard, not Cloud Call Center)

3 options provider gave. 1000-engineer review:

| Option | Fit | Verdict |
|---|---|---|
| **Standard SIP Trunk (Fiber)** | Needs Jio Fiber at physical office | ❌ REJECTED — we are cloud-only (Hostinger VPS Mumbai), no physical office |
| **Cloud SIP / Cloud Call Center** | SaaS panel, recording, auto-dial | ❌ REJECTED — duplicates existing FreeSWITCH + Vobiz stack, no technical benefit, adds monthly cost + 3rd-party panel we don't control |
| **Mobile SIP Trunk** | IP-based, integrates with our server | ✅ **WIN** — same architecture as Vobiz, no office needed, portable, IP-auth |

## Plan: 10 channels × ₹999/channel = **₹9,990/month** unlimited domestic (REVISED 2026-08-27 9:46 AM)

## ✅ Provider reply received (9:44-9:57 AM) + 6-min voice call at 9:50 AM

Provider corrected pricing (9:44-9:46 AM):
- Mobile SIP = **₹999/ch × 10 = ₹9,990/month** (5 days activation)
- Cloud SIP = ₹1,250/ch × 10 = ₹12,500/month
- Standard SIP Fiber = 20ch min (requires office fiber, 20 days)

User (Sumit) took a 6-min voice call at 9:50 AM, explained everything on call. Provider asked for "installation address" (9:57 AM). Sumit replied at 10:00 AM.

10:08 AM: Reply sent with VPS details (Hostinger Mumbai, IP 72.61.245.204, domain leadsgenai.in) + 3 follow-up asks (KYC docs list, agreement format, payment UPI/NEFT).

- **Provider:** Sai Service Centre, Mumbai (Indiamart-verified) — Jio/Vodafone/Airtel distributor
- **Provider GST:** 27ARAPP6458L3Z6 (they invoice us; no own GSTIN needed)
- **Our entity:** LeadGen AI Solutions, sole-prop, Nagpur
  - PAN: BONPD6321P
  - Udyam: registered (DLT entity-proof accepted)
  - No own GSTIN (reseller GST used)
- **Use case:** AI voice calling agent on FreeSWITCH + Hostinger VPS
- **Activation:** 5 days (Mobile SIP), 20 days (Standard SIP)
- **Need:** 1 DID mobile number (outbound + inbound)
- **Payment:** UPI/NEFT to provider

## Cost comparison (with Vobiz baseline)

| Plan | Price | Capacity | Activation | Our fit |
|---|---|---|---|---|
| Standard SIP Fiber (20ch min) | ₹499/ch × 20 = ₹9,980/mo | 20 ch unlimited | 20 days | ❌ needs office fiber, 20ch overkill |
| **Mobile SIP 10ch** | **₹999/ch × 10 = ₹9,990/mo** | 10 ch unlimited | 5 days | ✅ **our pick** |
| Cloud SIP 10ch | ₹1,250/ch × 10 = ₹12,500/mo | 10 ch + web panel | ? | ❌ duplicates FreeSWITCH stack |
| Vobiz (current) | ₹0.45/min PAYG | metered | LIVE | at 3000 calls/day = ~₹40K/mo (worse) |

**At 5000+ calls/day target → Jio Mobile SIP = ₹10K wins. At <2000 calls/day → Vobiz PAYG wins.** Per user target 5000/day, Jio Mobile is the right play. Keep Vobiz as failover (parallel trunks, round-robin).

## Provider ask sent (WhatsApp 9:37–9:41 AM 2026-08-27) — provider replied 9:44-9:46 AM

1. 10 channel Mobile SIP Trunk — ₹9,990/month (10 × ₹999) ✅ confirmed
2. SIP credentials: host/username/password — **need: IP-auth OR registration?**
3. 1 DID mobile number — **need: area-code preference (Mumbai/Nagpur/Delhi?)**
4. KYC process — **need: full docs list (PAN + Udyam + GST + ?sole-prop affidavit)**
5. Activation: 5 days (Mobile) ✅ confirmed
6. Payment: UPI/NEFT details pending — **need: provider UPI/NEFT**

## Admin work — pre-cred scaffold (no secrets, no live wiring)

These can be done NOW without provider creds. INERT by default.

### 1. `.env.example` (planned, not yet added)
```bash
# Jio Mobile SIP Trunk (Sai Service Centre reseller, GST 27ARAPP6458L3Z6)
# Plan: 10 channel × ₹499/month unlimited domestic
# INERT until JIO_TRUNK_ENABLED=1 AND all 3 creds set
JIO_SIP_HOST=                       # e.g. sip.jio-saibc.in
JIO_SIP_USER=                       # SIP registration username (provider will give)
JIO_SIP_PASS=                       # SIP registration password
JIO_SIP_REALM=                      # SIP realm (provider will give)
JIO_SIP_DID=+91XXXXXXXXXX           # 1 mobile DID for outbound/inbound
JIO_SIP_TRANSPORT=udp               # udp or tls
JIO_TRUNK_ENABLED=0                 # INERT default
JIO_SIP_CPS_LIMIT=2                 # calls-per-second cap (conservative start)
JIO_SIP_MAX_CONCURRENT=10           # matches 10-channel plan
```

### 2. FreeSWITCH gateway template (planned)
`sip-gateways/jio-mobile.xml` with IP-auth OR registration (provider will confirm which). 5060/UDP, RTP 10000-20000/UDP.

### 3. Trunk selector
`app/telephony/trunks.py` (NEW, provider-agnostic):
```python
PROVIDERS = {
    "vobiz": {"weight": 1, "caller_id_env": "VOBIZ_CALLER_ID"},
    "jio_mobile": {"weight": 0, "enabled_env": "JIO_TRUNK_ENABLED"},
}
def pick_trunk(lead) -> str:
    # Round-robin or LCR; jio_mobile = primary once enabled
    ...
```

### 4. Readiness gate
`app/telephony/telephony_readiness.py` add Jio check (mirrors vobiz_trunk check).

### 5. Tests
`tests/test_jio_sip_tenant.py` — fake creds → load gateway config → assert schema. No real call.

## Activation sequence (after provider reply)

1. Provider sends KYC form + UPI/NEFT details
2. Owner submits KYC (PAN + Udyam + GST declaration + sole-prop affidavit) — owner-only step
3. Owner pays ₹499 + GST (one-time or first month) — owner-only step, UPI manual
4. Provider activates trunk, sends SIP host/credentials/DID
5. @platform sets VPS env vars (`JIO_SIP_HOST/USER/PASS/REALM/DID`)
6. @engineering merges FreeSWITCH gateway config, recreates container
7. Test call: FreeSWITCH CLI `originate sofia/gateway/jio_mobile/918261030181 &echo`
8. Verify caller-ID shows Jio DID
9. Set `JIO_TRUNK_ENABLED=1`, `TELEPHONY_PROVIDER=jio_mobile` (or round-robin)
10. Mirror Vobiz in `app/telephony/call_manager.py` — both trunks live, jio_mobile primary

## Decision points (owner)

- DID area code: Mumbai (022/91-22) vs Nagpur (0712) vs Delhi? (default: 91-22 — closer to Vobiz trunk geography)
- Backup trunk: keep Vobiz live in parallel (recommended — fall-back resilience), or hard-cutover?
- CPS cap: 2 (Vobiz-comparable) or 1 (more conservative)?

## Files (planned)

- `.env.example` — JIO_SIP_* block (INERT default)
- `app/telephony/trunks.py` (NEW) — provider-agnostic dispatcher
- `app/telephony/telephony_readiness.py` — add `jio_mobile` check
- `app/telephony/sip-gateways/jio-mobile.xml` (NEW) — FreeSWITCH gateway template
- `tests/test_jio_sip_tenant.py` (NEW) — config + readiness tests
- `docs/coordination/JIO_SIP_SETUP_PLAN.md` — this file

## Open follow-ups

- [ ] Provider reply with KYC form + payment UPI/NEFT
- [ ] Owner (Sumit) submits KYC + pays first invoice
- [ ] Provider activates trunk, sends SIP creds + DID
- [ ] @platform wires VPS env
- [ ] @engineering ships FreeSWITCH gateway
- [ ] Live test call + caller-ID verify
- [ ] Activate `JIO_TRUNK_ENABLED=1`
- [ ] DLT registration on the new Jio DID (140/1600) for outbound compliance

## References

- Vobiz trunk provisioning (template): `scripts/vobiz_provision.py` (mirrored pattern)
- Existing Vobiz env: `.env.example:89-94`
- Existing readiness: `app/telephony/telephony_readiness.py:67`
- Provider thread: WhatsApp `+91 90293 41515` chat (Sai Service Centre, Mumbai)
- Decision memory: `memory/integrations.md` (new Jio entry 2026-08-27)
