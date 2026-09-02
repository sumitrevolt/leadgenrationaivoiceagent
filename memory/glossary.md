# Glossary — domain terms, internal shorthand, entity names

Schema: `Term — definition (source-of-truth file if any)`. Dated only where the meaning changed over time.

## Products & pricing
- **Product 1 / "Marketing"** — AI Automated Marketing, MAIN product for Indian local businesses. Public plans: **Main** (`starter` key, ₹1,999/mo) + **Combo/Advanced** (`advanced`, ₹5,999/mo, includes 500 voice min). Truth: `app/marketing/packages.py`.
- **Product 2 / "Voice Agent"** — standalone AI telecaller, flat per **niche-band** A/B/C ₹4,999/9,999/19,999/mo, UNLIMITED calls. Truth: `voice_packages.py`; page `/voice-agent`.
- **Growth plan (₹2,999, key `growth`)** — LEGACY HIDDEN plan, `public:False`, backward-compat only. Public code paths must use `get_public_packages()`.
- **TOPUP_PACKS** — voice minute top-ups 100/250/500 min = ₹1,499/3,499/5,999.
- **lead_band** — niche → A/B/C pricing band mapping in `app/niches.py` (helpers `lead_band()`, `niches_for_product()`).
- **NICHES** — 39 builtin niche dict in `app/niches.py` (+ runtime custom merge); categories marketing/leadgen/both.
- **jiya makeover** — the ONLY real paying customer (as of 2026-07-05); first invoice `INV/2026-27/0001`.

## Voice / telephony
- **TelecallerBrain** — KB-grounded voice conversation brain (`telecaller_brain.py`), ACP pattern, ≤2 sentences/1 question.
- **free_ai chain** — multi-provider free LLM fallback chain (`app/voice_agent/free_ai.py` ~line 420) with escalating circuit-breaker.
- **vobiz_stream** — live WS voice session (`app/telephony/vobiz_stream.py`), L16/16k bidirectional; the "stream path" (vs `reply()` web path — guards must be mirrored in BOTH).
- **web-call** — FREE browser test call at `/app/test-call` (`app/api/web_call.py`) — voice tuning yahin hota hai, phone = final verify.
- **AMD** — answering machine detection (Twilio AnsweredBy → voicemail-drop/hangup).
- **platform_dial** — Swara's self-sale cold-call batch. HARD OFF since 2026-07-05 (user mandate).
- **DLT / 140-series / DND** — TRAI compliance stack for Indian outbound; DLT registration = user-side pending (Udyam re-apply); DND scrub fail-CLOSED.
- **Udyam** — free MSME registration (udyamregistration.gov.in) — the path to DLT re-apply as Proprietorship.

## Platform / ops
- **AI Staff Team** — 15+ named product-framed agents (`app/platform/team.py`): marketing = isha/dev/rohan/**neha**(pipeline_ops); voice = swara/tara/arjun/meera; platform = boss/kavya/nikhil/Hermes(infra)/Guru+Vikram(code_upgrader)/Pranav(SRE)/Vidya(FinOps)/Arnav(Security)/**Arya**(MCP)/Kabir+Aryan+Diya(gated OFF). Schedule truth: `team_scheduler.py` (24 jobs).
- **Mission Control** — `/app/automation` admin cockpit (28 tabs; Growth Lab = optimizer+experiments).
- **Office HQ** — `/app/office` virtual-office map; Simple cockpit default, 🎛️ toggle → Pro (Phaser map).
- **Control Center** — `/app/control-center` 4-level ops cockpit (Sigma graph).
- **Hot Queue** — mid-funnel worklist, default tab of `/app/inbox` (interested-but-unworked leads).
- **dead-man trio** — heartbeat (`data/job_heartbeats.json`) + revive-beat */20min + watchdog ensure_alive.
- **DLQ** — dead-letter queue, Redis `dlq:failed_tasks`; desk in Office HQ.
- **boot-grace** — heavy daily job whose window is active AT boot = skipped this boot (restart-storm guard).
- **godfile split** — 2026-06-20 refactor: 10 god-files → 22 modules; duplicate-route grep must cover ALL split routers.
- **first-route-wins** — FastAPI matches the first registered route; a duplicate silently shadows the later one.
- **fail-open / fail-closed** — billing meters + tenant middleware degrade PERMISSIVE; compliance (DND) + prod webhook signatures degrade BLOCKING.
- **skill_pack** — 250 runtime skills served to VPS agents (`platform/skill_pack.py`, KB "skills" namespace).
- **llm_council** — Karpathy 3-stage multi-agent decision engine (`POST /api/agents/council`, UI `/app/agents`).
- **eval_gate** — median-baseline regression signal wired into self_improve + DeepEval CI.
- **canary (🐦 pelican)** — model-emitted last line of every Claude reply; missing = context drift, start a new chat.
- **sandbox-stale** — Claude sandbox mount goes stale after file-tool edits → Windows file-tools = source of truth.
- **mini-site** — per-client public page `/b/{slug}` (booking + card + bio + widget.js embed).
- **consent ledger** — `consent_ledger.py`: opt-out → instant cross-channel suppression + 90-day recording retention.
- **Second Brain** — Obsidian markdown vault synced from `data/obsidian_staging/` via host cron (repo leadsgenai-brain).
