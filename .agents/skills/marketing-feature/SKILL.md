---
name: marketing-feature
description: Add a new marketing feature to LeadGen AI the proven way — module + API + frontend tab + test + VPS smoke. Use when the user says "naya marketing feature", "add a poster/post/audit/review tool", "marketing me X add karo", "naya tab", or wants any new free-stack marketing capability. Captures the exact repeatable pattern so it is fast and token-cheap.
---

# Add a Marketing Feature (repeatable pattern)

Yeh wahi pattern hai jisse 19 marketing tabs bane. Har naya feature isi 5-step me, taaki re-derive na karna pade.

## Golden rules
- **Free-stack only** — koi paid API nahi. AI text chahiye to `app/voice_agent/free_ai.py` (Cerebras→Groq→…→Gemini chain).
- **LLM-first + never-empty template fallback** — har function LLM try kare, fail/empty pe deterministic template return kare. UI kabhi blank na ho.
- **Pure-sync + never-raise** jahan ho sake (poster/QR/SVG = pure logic, no API).
- **Reuse**: QR → `review_kit.py` ka stdlib encoder; poster SVG → `posters.py` (brand colors `brand_kit.py`); festivals → `festivals.py`.

## 5 steps
1. **Module**: `app/marketing/<feature>.py` — main function(s) return dict/SVG/text. LLM call `from app.voice_agent.free_ai import ...` (mock-able in tests). Template fallback hamesha.
2. **API**: `app/api/marketing.py` (ya wahi router file) me endpoint `POST/GET /api/marketing/<feature>` — admin auth, Isha event log (`log_event`). Public chahiye to `app/api/public_site.py` (rate-limit + honeypot pattern).
3. **Frontend tab**: `frontend/marketing.html` — naya tab button + panel. Niche dropdown dynamic `/api/data/niches` se. Poster/SVG inline + client-side canvas PNG download (existing tabs copy karo).
4. **Test**: `tests/` me `free_ai` mocked, function output assert (keys, char-limits, never-empty). `scripts\run_tests.bat` → `pytest_run.log` Read (~80+ green).
5. **Ship + smoke**: skill `leadgen-ops` loop (push → VPS pull+restart). Smoke ek `.py` file me likho (SSH inline quoting todta) → `python scripts/<smoke>.py` VPS pe → page 200 + function output verify.

## Gotchas
- SVG me user text **XML-escape** karo (`&`, `<`, `>`).
- Char-limits enforce karo jahan platform maange (RSA headline ≤30, desc ≤90, GBP desc ≤750).
- Naya file data likhe to `data/<dir>/` (gitignored, VPS-local) — phone/PII git me nahi.
- Done → `docs/SESSION_LOG.md` me append (tab count update), AGENTS.md `/app/marketing (N tabs)` 1-line.
