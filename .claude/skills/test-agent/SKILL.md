---
name: test-agent
description: Test the AI voice agent before going live — run the persona eval suite, have a text/web conversation, or check guardrails (PII redaction, prompt-injection block). Use when the user says "test the agent", "is the bot working", "run evals", "check the voice agent", or "try the bot".
---

# Test the Voice Agent

The agent (live brain `app/voice_agent/telecaller_brain.py`; full orchestrator + eval harness `natural_dialog.py`) listens, understands, gives grounded answers, books appointments, detects voicemail, and is guarded against PII leaks + prompt injection. It talks naturally in Hinglish on the FREE `free_ai.py` chain (Mistral primary → Groq → Cerebras → … → Gemini — no paid key needed); if the whole chain is down it degrades to rule-based fallbacks.

## Options

1. Eval suite (7 personas: interested, busy-rude, confused, price-objector, voicemail, not-interested, Hindi-switcher):
   ```bash
   python -m app.voice_agent.eval_suite
   ```
   Expect pass_rate near 100%.

2. Quick text conversation:
   ```python
   import asyncio
   from app.voice_agent.natural_dialog import NaturalDialogManager
   async def go():
       m = NaturalDialogManager(niche="solar_commercial", client_name="SunPower", client_service="commercial solar")
       s = m.new_conversation()
       print(await m.opening_line(s))
       for u in ["kitna kharcha?", "interested hoon demo dikhao"]:
           print("AGENT:", (await m.respond(u, s)).text)
   asyncio.run(go())
   ```

3. Browser web-call (no telephony cost): start server (`uvicorn app.main:app --port 8000`) then open `/app/test-call`. Mic allow karo — server Groq whisper-large-v3 STT chalega (phone-parity).

4. Voice change ke baad: `python scripts/agent_tester.py` (scorecard: double/empty/repeat/long/slow). Quality already free chain pe (Gemini key ki zaroorat nahi). Best Hindi voice (optional): SARVAM_API_KEY + STT_PROVIDER=sarvam.
