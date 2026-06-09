---
name: leadgen-start
description: Session bootstrap for LeadGen AI — token-efficient way to start ANY task on this project. Use at the start of a new chat, when the user says "shuru karo", "continue", "kaha the hum", "project pe kaam karo", or asks anything about the platform without specifying a file. Loads the lean working memory + token discipline so the session stays cheap.
---

# LeadGen AI — Session Start (token-efficient)

Iska maqsad: naya chat minimum token me oriented ho jaye. AGENTS.md (lean working memory) pehle se context me hai — use re-read mat karo.

## Token rules (FOLLOW — user weekly limit hit karta hai)
1. **Naya task = naya chat.** Memory `AGENTS.md` me persist hai, lambi conversation drag mat karo.
2. **Heavy sub-agents (Task/Agent) sirf jab zaroori** — wahi sabse zyada token jalate hain. Chhote lookups khud karo (Grep/Read targeted).
3. **AGENTS.md ko lean rakho.** Naya milestone → `docs/SESSION_LOG.md` me append karo (newest neeche), AGENTS.md me sirf 1-2 line status update.
4. Pura file mat padho jab tak zaroorat na ho — `Grep`/`Read offset+limit` se targeted lookup karo.
5. Verification VPS pe `.py` smoke se (chhota), web-call pe voice tuning (FREE). Phone-call sirf final (paisa).

## Project ek nazar me
- Product: **AI Automated Marketing** (core) + AI **voice agent** (helper). Live: https://leadsgenai.in (Hostinger VPS Mumbai, `/opt/leadgen`, systemd `leadgen`).
- Tiers: Starter ₹2,999 / Growth ₹5,999 / Advanced ₹11,999 (voice). Marketing tiers DLT-free → abhi launch ho sakta.
- 42 niches (`app/niches.py`). AI free stack: Cerebras LLM (working) + Groq STT (key missing) + EdgeTTS.
- 8 AI staff + scheduler (blog 06:30, content 07:00, digest 08:30, scrape 09:30, email 10:30, QA/trainer raat).

## Common task → kahan jao (re-derive mat karo)
- Deploy / test / push / "production error" → skill **`leadgen-ops`**; VPS-specific (SSL/Caddy/SSH/down) → **`hostinger-deploy`**.
- Naya marketing feature (poster/post/audit type) → skill **`marketing-feature`**.
- Naya niche ya client onboard → **`niche-onboarding`**.
- Voice agent edit/debug/tune → **`voice-agent-kb`** (internals) + **`test-agent`** (eval) + `scripts/agent_tester.py`.
- Lead-gen campaign chalao → **`run-campaign`**.

## Pehla step har task me
1. User ka exact ask samjho. Ambiguous ho to 1 chhota AskUserQuestion (token-cheap), warna seedha kaam.
2. Relevant skill upar se pick karo → uske steps follow karo.
3. Code change → `leadgen-ops` loop se ship + verify.
4. Done → `docs/SESSION_LOG.md` me 2-4 line milestone, AGENTS.md me 1-line status.

## Blockers (user-action, abhi pending)
GROQ_API_KEY (STT), Udyam→DLT re-apply (cold-calling), Vobiz recharge+DID (calls). External-blocked (build nahi kar sakte): missed-call callback, GBP/Meta auto-post. In par token mat jalao.
