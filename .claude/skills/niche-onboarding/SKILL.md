---
name: niche-onboarding
description: Naya niche add karna ya naya client onboard karna LeadGen platform pe. Use when the user says "naya niche", "add niche", "client onboard", "new client", "niche add karo", or wants to set up a business with its auto-provisioned agents end-to-end.
---

# Niche + Client Onboarding (e2e API flow)

Sab calls admin auth ke saath. Base: `https://leadsgenai.in` (ya local `:8000`).

## Step 1 — Niche add karo (sirf agar builtin ~39 me nahi hai)

Pehle check: `GET /api/data/niches` — niche already hai (builtin ya custom)? Toh seedha Step 2. (39 builtin niches `app/niches.py` me; categories marketing/leadgen/both, har niche ka `lead_band` A/B/C jo voice-product band pricing decide karta hai.)

```
POST /api/data/niches   (admin)
{"name": "EV Charging Stations"}        # sirf name zaroori, baaki defaults
```

Optional fields: `key`, `target_type` (b2c|b2b|both, default b2c), `b2b_client`, `end_customer`, `avg_ticket_inr`, `pitch_hook`, `keywords`, `qualification_questions`, `pricing_inr`.

- **Pricing defaults** (pricing_inr na do toh): qualified_lead ₹300–1,500, appointment ₹800–2,500, monthly_starter ₹12,000. Niche ke ticket-size ke hisab se override karo (high-ticket: QL ₹800–6,000 tak jata hai).
- Custom niche **turant SAB jagah live**: flow (generic builder), KB auto-seed, agent provisioning resolve, web-call dropdown. Persistence: `data/custom_niches.json` (VPS-local, gitignored).
- **Verify**: `GET /api/data/niches?tier=C` me naya niche dikhe ([custom] tag, tier "C").
- **Builtin protected**: `DELETE /api/data/niches/{niche_key}` sirf custom pe chalta hai — builtin pe 403.

## Step 2 — Client create (auto 2 agents milte hain)

```
POST /api/platform/clients   (admin)
{
  "business_name": "Sharma EV Solutions",
  "contact_name": "Rahul Sharma",
  "contact_email": "rahul@sharmaev.in",
  "contact_phone": "+919876543210",
  "industry": "ev charging",
  "city": "Pune"
}
```

`industry` free text chalega — `resolve_niche_key` loose match karke NICHES key me map karta hai (fallback "general"). Explicit `niche` field bhi de sakte ho (industry pe priority leta hai).

System turant **2 agents auto-provision** karta hai (idempotent — dobara call pe duplicate nahi):
- **DATA agent** (`DA-xxx`, role="data") — business profile + niche facts KB me seed, namespace `client:<id>`
- **LEADS agent** (`LA-xxx`, role="leads") — end-customer calling, niche ke target_type ke hisab se

## Step 3 — Verify + web-call test

- `GET /api/platform/clients/{id}/agents` → dono agents (DA-xxx + LA-xxx) dikhne chahiye.
- Purana client bina agents ke? Backfill: `POST /api/platform/clients/{id}/provision-agents` (idempotent).
- **Web-call test**: browser me `/app/test-call` kholo → dropdown me niche select karo (custom wale [custom] tag ke saath dikhte hain) → call karke bot ka jawab check karo. Echo-reply aaye toh `leadgen-ops` skill ka quota triage dekho.

## Enterprise gate

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`).

**Change-risk tier:** API-only onboard (POST niche/client) = **Standard**. Niche pricing/`lead_band` define karna = **High-risk** — band A/B/C seedha voice-product band-pricing decide karta (`voice_packages.BANDS`), galat band = galat bill.

- **Idempotency/dedupe:** Step 1 se pehle `GET /api/data/niches` check (builtin ya custom already?) = duplicate niche se bacho. Client `POST /api/platform/clients` agent-provision **idempotent** (DA-xxx + LA-xxx dobara call pe duplicate nahi); purana client backfill `POST .../provision-agents` bhi idempotent. KB seed bhi namespace `client:<id>` pe re-seed-safe.
- **Safety:** custom niche persistence `data/custom_niches.json` (VPS-local, gitignored, bind-mount) — git me commit mat karo. Builtin niche protected (`DELETE` pe 403) — yeh guard todna mat. KB seed (deep_extract) heavy → off-loop / `asyncio.to_thread` + deadline (public path pe blocking ML = prod-down).
- **Compliance (fail-CLOSED):** niche ka `target_type` + qualification = outbound script feed karta — TRAI/DND/9am–7pm/AI-disclosure gate niche-level se bypass KABHI nahi. Client contact PII = DPDP (consent-ledger), scrape ToS-safe niches hi.
- **Observability:** naya niche `/api/data/niches?tier=C` me `[custom]` tag se dikhe; client agents `/api/platform/clients/{id}/agents` me; events `agent_events` table.
- **Rollback (NAMED):** galat niche → `DELETE /api/data/niches/{key}` (custom only). Galat client/agents → provision idempotent so re-run safe; data-repair = `data/custom_niches.json` edit + KB namespace purge.

**Evidence (done):** `GET /api/data/niches?tier=C` me niche `[custom]` + `GET /api/platform/clients/{id}/agents` me DA-xxx+LA-xxx dono + `/app/test-call` pe niche-grounded reply (echo nahi) + `.venv\Scripts\python.exe scripts\prod_check.py` green. Pricing/band touch hua to `pytest tests\test_billing_truth_2026.py -q` bhi.
