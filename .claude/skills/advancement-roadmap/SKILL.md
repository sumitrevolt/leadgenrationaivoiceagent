---
name: advancement-roadmap
description: LeadGen AI ko competitor-grade/advanced banane ka prioritized roadmap — 2026 web research + repo gap truth. Use when user bole "advanced bano", "aur kya chahiye", "competitor se aage", "next feature", "deep research", ya product moat/planning.
---

# Advancement Roadmap (2026 truth — rebuild mat karo)

## Pehle verify karo (80% already built)

Competitor doc `docs/Competitor_Top20_Feature_Gap_2026.md` me P0 list hai — **grep pehle**. Ye PEHLE se live/code-complete hain (rebuild = FAIL):
- brand_frames + daily feed · business card `/b/{slug}/card` · magic_resize · review_to_post
- speed_to_lead + lead_distribution round-robin · content_approval · FDE snapshots
- geo_visibility + grid rank (growth_tools + `/api/localseo/*`)
- call_insights + `/api/voiceai/ask` · NL `/api/ai/command` (ab `call_insights` action bhi)

**Moat intact:** koi competitor ₹1,199–6,999 me marketing + leadgen + voice teeno nahi deta (DO products — bundle USP mat likho).

## 2026 market direction (web research)

1. **Agentic execution** — draft nahi, *karna* (Vendasta MARiO, OmniLocal, Birdeye BirdAI). Humare 14 AI staff + Celery durable = on-trend; demo/UI me agents visible karo.
2. **Speed-to-lead <2 min** (Privyr/Podium) — metric built (`speed_to_lead.py`); gap = landing badge + auto-engage unified pipeline marketing copy.
3. **Post-call webhook discipline** — `callId` idempotency, 200+async worker, `call.transcript` + `call.report.ready` dual events (AgentCall/CallSphere pattern). Hum: metering+qualify wired (`post_call_hooks.py`); next = structured `call.report.ready` customer webhook after qualify.
4. **Local-first / MCP** — hum `/mcp` + customer webhooks + A2A card already; sell as "apna data, apna VPS".
5. **GEO / AI-search visibility** — lead magnet #3 (`geo_visibility.py`); gap = **public page** `/geo-check` (audit/site-audit pattern), abhi sirf growth_tools admin.

## Priority backlog (wireable, free-stack)

| P | Item | Why | Touch |
|---|------|-----|-------|
| P0 | Human call transfer + context whisper | Voice tier killer; Exotel gone → Vobiz connect-leg | `call_transfer.py`, gated `CALL_TRANSFER` |
| P0 | Public `/geo-check` lead magnet | OmniLocal/Birdeye GEO trend; API ready | `frontend/website/`, `main.py` route |
| P0 | `call.report.ready` webhook after qualify | 2026 voice SaaS standard | `post_call_hooks.py`, `customer_webhooks.py` |
| P1 | Post-call analytics DB table (not just jsonl) | Dashboard p95 <60s insights | new migration + worker job |
| P1 | Proposal view-tracking pixel | Privyr pattern | `proposal_tracking.py` extend |
| P1 | Connected-call billing copy on `/pricing` | Vodex framing | `pricing.html` only |
| P2 | Video clips repurposing | ffmpeg heavy | Celery `heavy` queue, opt-in |
| EXT | Meta auto-post, GBP API, DLT cold-call | user paperwork — token mat jalao |

## Cross-path discipline (har advancement pe)

1. `grep` touch-points → duplicate route check
2. Additive + never-raise + flag-gated
3. `scripts/cross_path_audit.py` + targeted test
4. `leadgen-ops` deploy loop

## Research sources

- In-repo: `Competitor_Top20_Feature_Gap_2026.md`, `ROADMAP_2026_Automation_Revenue_Hardening.md`, `AUTOMATION.md`
- Web: agentic local SMB (Vendasta/OmniLocal 2026), voice webhook idempotency (AgentCall, CallSphere, Sherlock)
