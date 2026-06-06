# Project Memory — leadgenrationaivoiceagent

## User Preferences (IMPORTANT)
- **Language: ALWAYS reply in Hinglish (Hindi + English mix, Roman script).** User ne explicitly bola hai — har jawab Hinglish me hi dena hai.
- Concise aur direct rakho. Zyada formatting / verbosity nahi.

## Project Context
- "LeadGen AI Voice Agent" — FastAPI based B2B lead-gen + AI voice agent platform.
- Stack: Lead scrapers (Google Maps, IndiaMart, JustDial, LinkedIn), AI voice agent (free STT Vosk/Whisper, free TTS EdgeTTS, Gemini/Vertex LLM), telephony Twilio + Exotel.
- 20 niches configured (solar, real estate, dental, HVAC, interior, study abroad, etc.).
- Integrations: WhatsApp, HubSpot, Google Sheets, Email.
- `.env` me Twilio/Exotel keys abhi placeholder hain — live calling configured nahi.

## User's Goal / Business Model
- Chhoti companies ko AI voice agent bechna (takibot-style) — agent unke potential customers ko call karke unke business ke hisab se leads laaye.
- User "free calls" chahta hai. Reality: AI brain ~free ho sakta hai, lekin telephony (PSTN) per-minute paid hai.
- Recommended pitch: client ko "per qualified lead" charge karo (₹200–500/lead), "free calls" mat bolo.

## Key Facts Established
- Dograh (open-source, self-hosted Vapi/Retell alternative, BYOK) platform layer free karta hai, lekin telephony nahi.
- Telephony (real phone ring) ka cost ~₹0.50–0.80/min India me — yeh research chal raha hai ki koi free solution hai kya.
