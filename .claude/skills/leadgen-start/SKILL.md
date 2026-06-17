---
name: leadgen-start
description: Session bootstrap for LeadGen AI — token-efficient way to start ANY task on this project. Use at the start of a new chat, when the user says "shuru karo", "continue", "kaha the hum", "project pe kaam karo", or asks anything about the platform without specifying a file. Loads the lean working memory pointer + token discipline so the session stays cheap.
---

# LeadGen AI — Session Start (token-efficient)

Iska maqsad: naya chat minimum token me oriented ho jaye. `CLAUDE.md` (lean working memory) pehle se context me hai — use re-read mat karo. Deep history `docs/SESSION_LOG.md` me (auto-load NAHI hota).

## Token rules (FOLLOW — user weekly limit hit karta hai)
1. **Naya task = naya chat.** Memory `CLAUDE.md` me persist hai, lambi conversation drag mat karo.
2. **Heavy sub-agents (Task/Agent) sirf jab zaroori** — wahi sabse zyada token jalate hain. Chhote lookups khud karo (Grep/Read targeted).
3. **CLAUDE.md ko lean rakho.** Naya milestone → `docs/SESSION_LOG.md` me append karo (newest neeche), CLAUDE.md me sirf 1-2 line status update.
4. Pura file mat padho jab tak zaroorat na ho — `Grep`/`Read offset+limit` se targeted lookup karo.
5. **Windows = source of truth** (sandbox mount file-edits ke baad STALE). Verify Windows pe (Read/Edit/`.venv` python). CLAUDE.md/SESSION_LOG sandbox-bash se KABHI mat chhuo.
6. Verification VPS pe `.py` smoke se (chhota), web-call pe voice tuning (FREE). Phone-call sirf final (paisa).

## Project ek nazar me
- **DO ALAG products** (bundle/"dono ek saath" framing GALAT): (1) **AI Automated Marketing** = MAIN product (Dhanda-style, local SMBs); voice agent iske Advanced tier me sirf EK feature. (2) **AI Voice Calling Agent** = ALAG standalone telecaller (DLT-gated).
- Live: **https://leadsgenai.in** (Hostinger VPS Mumbai 72.61.245.204, `/opt/leadgen`, **Docker** `leadgen_app`; systemd `leadgen` DISABLED = rollback only). Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
- **Pricing (truth = source files, CLAUDE.md drift kar sakti):** Marketing `packages.py` Starter ₹1,199 / Growth ₹2,999 / Advanced ₹6,999 (Advanced me voice 500 min). Voice `voice_packages.py` FLAT/band: A ₹4,999 / B ₹9,999 / C ₹19,999 (unlimited calls/niche, free pilot 7d/50 calls). Marketing tiers DLT-free → abhi launch ho sakta; cold-calling DLT pe atki.
- 39 builtin niches (`app/niches.py`; custom niches merge on top = 40+). AI free stack: **LLM** = free multi-provider chain (Mistral primary → Groq → Cerebras → … → Gemini, circuit-breaker + fallback) + **Groq whisper STT** (key SET) + **EdgeTTS** hi-IN-SwaraNeural.
- 14 AI staff (`app/platform/team.py`, product-split) + **Celery durable scheduler** (worker+beat containers; in-process APScheduler = rollback). Auto-jobs IST: blog 06:30, content 07:00, digest 08:30, scrape/prospect 09:30, email 10:30, QA/trainer raat.

## Common task → kahan jao (re-derive mat karo)
- Deploy / test / push / "production error" → skill **`leadgen-ops`**; VPS-specific (SSL/Caddy/SSH/down) → **`hostinger-deploy`**.
- Non-trivial change/debug/audit ka discipline → **`fable-operating-manual`**.
- Naya marketing feature (poster/post/audit type) → skill **`marketing-feature`** (route shadowing dekho).
- Naya niche ya client onboard → **`niche-onboarding`**.
- Voice agent edit/debug/tune → **`voice-agent-kb`** (internals) + **`test-agent`** (eval) + `scripts/agent_tester.py`.
- Lead-gen campaign chalao → **`run-campaign`**. Pipeline safai → **`pipeline-hygiene`**.

## Pehla step har task me
1. User ka exact ask samjho. Ambiguous ho to 1 chhota AskUserQuestion (token-cheap), warna seedha kaam.
2. Relevant skill upar se pick karo → uske steps follow karo.
3. Code change → `leadgen-ops` loop se ship + verify (`docker compose build app` + `up -d --no-deps app` → `/health`=production).
4. Done → `docs/SESSION_LOG.md` me 2-4 line milestone, CLAUDE.md me 1-line status.

## Blockers (user-action, abhi pending)
🚨 **Razorpay** `.env` me placeholder keys (real `rzp_live_` set nahi) — checkout/topup/dunning dead jab tak fix na ho (pehle paid customer se pehle MUST). Udyam→DLT re-apply (cold-calling). Exotel KYC + recharge. External-blocked (build nahi kar sakte): missed-call callback, GBP/Meta auto-post. In par token mat jalao.
