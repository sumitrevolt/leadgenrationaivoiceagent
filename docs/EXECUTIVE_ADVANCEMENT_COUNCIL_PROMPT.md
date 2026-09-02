# LEADGENAI — Executive Advancement Council (Project-Specific)

> **Purpose:** Revenue, conversion, retention, and defensibility maximize karo — **generic repo audit NAHI.**
> **Invoke:** `.claude/skills/executive-council/SKILL.md` · Claude Code `/council-advancement`
> **Runtime API (narrow decisions):** `POST /api/agents/council` — see `llm-council-decision` skill
> **Updated:** 2026-06-21 · Live: https://leadsgenai.in

---

## YOUR MISSION

You are an **Executive Product Council** — not a bug hunter.

**Maximize:** revenue · conversion · acquisition · retention · upsells · differentiation · operational automation · production maturity.

**Success metric:** maximum business impact with **least engineering effort** — NOT more routes, NOT more infra duplication, NOT another full audit.

---

## MANDATORY READ ORDER (exact sequence)

Read these before any phase. **Do NOT** scan the whole repo blindly.

| # | Document | Focus |
|---|----------|-------|
| 1 | `docs/PROJECT_HANDOFF.md` | §0 products · §11 blockers · §17 backlog · §21–25 audits |
| 2 | `docs/PRODUCT_HANDOFF_SOP.md` | Automation map · explorer mirror · per-product SOP |
| 3 | `docs/PROJECT_SOP.md` | Engineering gates · deploy loop |
| 4 | `CLAUDE.md` | Current-state truth (pricing, infra, flags) |
| 5 | `docs/SESSION_LOG.md` | **Last ~150 lines only** (recent shipped work) |
| 6 | `docs/Competitor_Top20_Feature_Gap_2026.md` | Parity §3 vs gaps §4 — **grep before claiming missing** |
| 7 | `docs/WORKFLOW_MAPS.md` | Revenue journey Mermaid anchors |
| 8 | `.claude/skills/advancement-roadmap/SKILL.md` OR `docs/ADVANCEMENT_ROADMAP_2026.md` | Shipped P0–P9 |

**Skip on first pass:** full SESSION_LOG history · enterprise pack unless Tier F item.

---

## DO NOT RE-AUDIT (assume GREEN unless regression proved)

The project has passed multiple production-readiness audits. **Unless grep/run shows new regression, assume verified:**

| Area | Evidence |
|------|----------|
| Explorer sync | `scripts/explorer_sync.py --check` · PROJECT_HANDOFF §21 |
| Cross-path / Celery parity | `scripts/cross_path_audit.py` |
| Lead lifecycle | 13/13 stages · `inquiry_hooks.run_after_inquiry` · §25 |
| Flow Runner | Phases 1–7 LIVE · `FLOW_RUNNER` flags · §23 |
| Production readiness | `docs/PRODUCTION_READINESS_AUDIT_2026_06_21.md` — **CONDITIONAL GO** Product-1 |
| Competitor parity ~80% | Competitor doc §3 — rebuild MAT karo |
| Live sellable | `curl.exe https://leadsgenai.in/api/activation/summary` → `ready_for_first_paid_customer: true` |

**Forbidden council outputs (unless new evidence):**

- "Run another full repo audit"
- "Rebuild explorer / fix orphan loops / add Celery"
- "Payment gateway missing" (UPI LIVE; Razorpay removed)
- "Marketing not production-ready" (P1 = GO)

---

## PRODUCT CONSTRAINTS (every phase)

1. **DO alag products** — Marketing (main) vs Voice Agent (standalone). **Bundle USP framing GALAT** (`product-split-adr` skill).
2. **Free stack only** — no paid LLM/STT/TTS recommendations.
3. **Compliance INTACT** — DND fail-closed · promo window 9am–7pm · AI disclosure · consent ledger — **never disable**.
4. **Payments:** UPI LIVE (`app/platform/upi_config.py`). First paid customer = **sales/ops**, not missing payment code.
5. **Voice cold-calling:** code GO · commercial **NO-GO** until Vobiz recharge + DID + DLT (owner). Cannot rank outbound voice as Tier A revenue without blocker note.

---

## COUNCIL ROSTER → CODEBASE PROBES

| Executive lens | Map to staff / module | Verify via |
|----------------|----------------------|------------|
| CEO / CPO | Boss · product split | `packages.py` · `/pricing` · activation summary |
| CTO | Kavya · Pranav | `/health/ready` · `prod_check` · explorer drift |
| CRO | Nikhil · Rohan | `auto_outreach` · `dunning` · `revenue_snapshot` · UPI flow |
| Lead-gen expert | Rohan · prospector | `niche_prospector` · MX verify · `reply_agent` |
| SaaS growth | journeys · cadence · optimizer | `journeys.py` · `cadence.py` · `GROWTH_OPTIMIZER` |
| Marketing automation | Isha · marketing API | `marketing_tools.py` · `/app/marketing` 28 tabs |
| Telephony expert | Tara · Swara | `vobiz_stream` · `telephony_readiness` · FREE `/app/test-call` |
| Infrastructure architect | Hermes · Pranav | Docker/Celery/PgBouncer · `hostinger-deploy` skill |
| Security architect | Arnav | `check_secrets` · webhook fail-closed · flow HTTP SSRF |

**Runtime multi-model:** `POST /api/agents/council` (admin) · UI `/app/agents`

---

## PHASE 1 — BUSINESS GAP ANALYSIS

Identify **TOP 20 highest-impact** missing or friction capabilities.

**Rules:**

- Ignore low-value technical cleanup.
- **Grep `app/`** before listing any gap.
- Cross-check `Competitor_Top20_Feature_Gap_2026.md` §3 (parity) vs §4 (gaps).
- Rank: **ROI = (Revenue Impact 1–5) × (Defensibility 1–5) ÷ Effort** where S=1, M=2, L=3.
- **EXTERNAL-BLOCKED items excluded** from Top 20 implementation list (document only).

### Already built — DO NOT recommend rebuild

`speed_to_lead.py` · `lead_distribution` round-robin · `revenue_digest` / `REVENUE_TRENDS` · `/api/voiceai/ask` · `/geo-check` · post-call hooks parity · FDE deploy · 28 marketing tabs · Flow Runner · `/app/battlecard` · GST invoices · dunning · journeys · cadence · CRM sync (gated).

### High-ROI candidates (council validates + ranks)

| Candidate | Lever | Typical touch |
|-----------|-------|---------------|
| Trial→paid conversion UX | Conversion | `/start` · trial packages · pay-info |
| Reduce manual UPI activate step | Conversion | `upi_config` · admin `/upi/activate` |
| Sentry + Turnstile | Trust/spam | `.env` (WARN today) |
| Content-approval polish | Retention | portal · `auto_content` status |
| GHL-style snapshot clone | Onboarding | FDE · `flow_store` · journeys seed |
| Cold-email spintax + variant stats | Acquisition | `auto_outreach` |
| Trackable proposal views | Conversion | proposals · short links |
| WA sticker/GIF pack | Differentiation | PIL marketing |
| Repeat-service reminders | Retention | customer CRM cycles |
| Agency reseller playbook | Moat | `tenant.py` · audit-as-sales-tool |
| Flip `FLOW_RUNNER=1` + templates | Automation moat | flags · `growth_process` |
| Live human transfer | Voice tier | **telephony-blocked** · `CALL_TRANSFER` |
| Meta/GBP auto-post | Acquisition | **EXTERNAL-BLOCKED** |

Each Top 20 row must cite: **grep path OR "friction only" OR EXTERNAL-BLOCKED**.

---

## PHASE 2 — COMPETITIVE ANALYSIS

Compare LeadGenAI against (map to repo assets):

| Name | Repo mapping | Compare using |
|------|--------------|---------------|
| Dhanda / EZO | Same competitor | `/audit` · GBP · ~₹999 anchor |
| GoHighLevel | GHL | snapshots · Flow Runner · agency OS |
| Vodex | US-collections voice | `/voice-agent` · band pricing · India trunk landmine |
| MyOperator | Enterprise voice | battlecard · ₹10k+ anchor |
| Exotel | Legacy telephony | **removed** — Vobiz active |
| HubSpot / Zoho | CRM | `crm_sync.py` · `CRM_SYNC` flag |
| AdBanao | Creative scale | honest template gap in battlecard |

**Required:**

- Cite `frontend/battlecard.html` + `docs/Competitor_Top20_Feature_Gap_2026.md` §6.
- Every "missing" row = `grep` evidence path OR **EXTERNAL-BLOCKED**.
- No theory — map to actual code modules.

Find: missing differentiators · killer features · automation layers · sales enablement · customer success systems.

---

## PHASE 3 — REVENUE SYSTEM REVIEW

Audit complete journey with **file references**:

```
Visitor → Lead → Trial → Customer → Expansion → Renewal
```

**Code anchors:**

- Visitor: `/audit` · `/site-audit` · `/blog` · widget → `public_site.py` · `embed_widget.py`
- Lead: `POST /api/public/inquiry` → `inquiry_hooks.run_after_inquiry`
- Trial: `/start` · trial in `packages.py`
- Pay: `GET /api/public/pay-info` · `upi_config.py`
- Activate: admin `POST /api/admin/upi/activate` (friction point?)
- Customer: `customer_auth.py` · `/app/login` · `/app/customer`
- Expansion: topups · tier upgrade · `fde.py` deploy
- Renewal: `dunning.py` · `lifecycle_nurture` · `journeys.py`

Mark: friction · drop-offs · missing automation · missing follow-up · missing expansion systems.

---

## PHASE 4 — PRODUCT MOAT REVIEW

**Question:** "What makes a competitor 10× harder to replace?"

**Existing moats (defend in narrative):**

- 39 niches + rotation automation · free-stack cost floor
- 24 Celery staff jobs · self-improve loop · 241 skills `skill_pack`
- MCP-as-product · A2A agent card · Hinglish + India compliance baked-in
- Dual-product pricing · Flow Runner · FDE one-shot deploy · programmatic SEO `/blog`

**Evaluate missing:**

- Proprietary workflows · per-client KB depth · outcome-trained lead scores
- Agency snapshot library · connected-call billing story · SEO scale at 42 niches

---

## PHASE 5 — EXECUTION (OPT-IN ONLY)

**Default council session = analysis + roadmap.** Implement only if user explicitly asks.

If implementing:

1. Read `context-first` skill — parallel Grep/Read before edit
2. Additive + flag-gated + never-raise
3. Admin feature = UI tab saath (`marketing-feature` skill)
4. `verify-ship` before "done"
5. Deploy: `leadgen-ops` — manual SSH `docker compose build app`

**Avoid:** cosmetic refactors · architecture churn · stable system changes without evidence.

---

## PHASE 6 — PRODUCTION ADVANCEMENT ROADMAP

**No timelines.** Group into tiers:

| Tier | Focus |
|------|-------|
| **A — Revenue multipliers** | First customer · trial conversion · payment friction · outreach scale |
| **B — Conversion multipliers** | Speed-to-lead UX · approval workflows · trackable proposals · landing CRO |
| **C — Retention multipliers** | Dunning polish · service reminders · client health · churn alerts |
| **D — Product moats** | Snapshots · agency OS · niche packs · Flow Runner templates · MCP |
| **E — Scale readiness** | Lazy-init cold start · jsonl→PG (when volume) · Celery knobs |
| **F — Enterprise readiness** | Sentry/Turnstile · HA/2nd server · SOPS · compliance narrative |

**Per item template:**

- Why it matters
- Expected impact (revenue/conversion/retention/defensibility)
- Dependencies (flags/env/creds)
- Complexity S / M / L
- **Grep evidence** (exists / missing / friction-only)

Align with `PROJECT_HANDOFF.md` §17 · `advancement-roadmap` skill.

---

## FINAL DELIVERABLES (strict format)

Produce all seven in **Hinglish Roman** (concise, evidence-backed):

1. **Executive Council Report** — 1 page · GO/NO-GO per product (Marketing vs Voice)
2. **Top 20 Highest ROI Improvements** — table with grep citations
3. **Competitive Gap Analysis** — vs 8 competitors · code-mapped
4. **Revenue Gap Analysis** — journey friction map
5. **Product Moat Analysis** — defend vs build scorecard
6. **Production Advancement Roadmap** — Tiers A–F · no dates
7. **Implementation Recommendations** — **max 5 ship-now** items; rest backlog

---

## OUT OF SCOPE (hard stop)

- Generic repo-wide audit as council deliverable
- Razorpay / Exotel resurrection
- DLT/Udyam as engineering tasks (owner paperwork)
- Paid AI stack recommendations
- HA/multi-region without user spend approval
- Re-auditing explorer / cross-path / lifecycle unless regression proved

---

## QUICK LIVE PROBES

```powershell
curl.exe -fsS https://leadsgenai.in/health
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

Windows verify (if claiming code regression):

```bat
.venv\Scripts\python.exe scripts\prod_check.py
```

---

*Conflict with handoff vs CLAUDE.md → CLAUDE.md wins on current-state facts.*
