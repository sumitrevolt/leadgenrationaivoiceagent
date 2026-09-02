# Landing-Page Voice Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/app/test-call` a real landing-page onboarding path — a prospect talks to the AI in the browser and, in that same session, a free-trial account gets created (not just a WhatsApp text they have to go act on later).

**Architecture:** Reuse the LIVE close-signal plumbing in `TelecallerBrain` (deal write + WhatsApp handoff, commit 048f0b5) instead of building a new account-creation path. Add a small "did the close-signal actually fire this turn" flag the brain already has the state for; `web_call.py` reads it and — only when a new `WEBCALL_INLINE_SIGNUP` flag is on — pushes a `close_signal` WebSocket event to the browser; the browser shows an inline form that calls the EXISTING `/api/public/signup` endpoint (same one `/pricing` already uses, same Turnstile + anti-hijack + trial provisioning). Separately, personalize the WhatsApp handoff link so even without the inline overlay, `/pricing` can prefill from a phone-call closer.

**Tech Stack:** FastAPI (Python 3.12) backend, vanilla-JS server-rendered HTML frontend (no build step), pytest + pytest-asyncio for tests.

## Global Constraints

- No voice-spoken passwords — email/password stay typed form fields, never conversation state.
- No new account-creation code path — the browser must call the existing `POST /api/public/signup` (`app/api/public_site.py:504`); do not duplicate its validation/dedupe/trial-provisioning logic anywhere else.
- `WEBCALL_INLINE_SIGNUP` default **OFF** (`"0"`) — this is new, funnel-critical, user-facing behavior; it ships dark and gets enabled after manual verification, per this project's flag-gating convention.
- `/app/test-call`'s existing internal staff-tuning behavior must not regress — all changes are additive (new WS message type, new flag, reworded copy with identical meaning).
- Every new/changed Python function gets a pytest test in the same style as its neighbors (`tests/test_voice_close_signal.py` for `telecaller_brain.py` changes).
- Hinglish user-facing copy, matching the existing tone in `web_call.html`/`pricing.html`.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/voice_agent/telecaller_brain.py` | Add `close_signal_fired` per-turn flag; personalize the WhatsApp handoff link (both inside the already-live close-signal mechanism). |
| `tests/test_voice_close_signal.py` | New tests for both of the above (existing file, append). |
| `app/api/web_call.py` | New `WEBCALL_INLINE_SIGNUP` flag helper + `_close_signal_payload()` pure helper; wire it into the WS turn loop; update the module's WS-protocol docstring. |
| `tests/test_web_call_close_signal.py` | New file — unit tests for the two new `web_call.py` helpers. |
| `frontend/web_call.html` | Reword "TEST MODE" banner copy (4 spots); add inline trial-signup overlay (HTML+CSS+JS) triggered by the new `close_signal` WS message; include the existing Turnstile loader. |
| `frontend/pricing.html` | Read `?phone=&biz=` from the URL (personalized WhatsApp link lands here) and prefill the FREE-trial signup modal. |
| `frontend/website/index.html` | Promote the existing `/app/test-call` hero link from a ghost button to a primary CTA with onboarding-focused copy. |
| `scripts/webcall_close_signal_probe.py` | New — a small manual-verification script (mirrors existing `scripts/ws_test.py`) that drives a scripted conversation to the close-signal turns and prints the `close_signal` WS message. |

---

## Task 1: `close_signal_fired` per-turn flag on `TelecallerBrain`

**Files:**
- Modify: `app/voice_agent/telecaller_brain.py:617` (`__init__`), `:798-801` (`_on_close_signal`), `:1459-1466` (`reply`)
- Test: `tests/test_voice_close_signal.py`

**Interfaces:**
- Produces: `TelecallerBrain.close_signal_fired: bool` — instance attribute, `False` by default and after every `reply()` call unless that specific turn caused `_on_close_signal()` to perform its real side-effects (i.e. `caller_phone` was known). Task 3 (`web_call.py`) reads this via `getattr(tcbrain, "close_signal_fired", False)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_voice_close_signal.py`:

```python
def test_close_signal_fired_flag_set_when_phone_known():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")
    assert brain.close_signal_fired is False
    brain._on_close_signal()
    assert brain.close_signal_fired is True


def test_close_signal_fired_flag_stays_false_without_phone():
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert brain.caller_phone == ""
    brain._on_close_signal()
    assert brain.close_signal_fired is False


@pytest.mark.asyncio
async def test_close_signal_fired_resets_on_next_turn(monkeypatch):
    """close_signal_fired must reflect ONLY the just-completed reply() turn --
    web_call.py checks it once per turn to decide whether to emit a WS
    close_signal event; a stale True would re-fire the overlay forever."""
    monkeypatch.setenv("CLOSE_DETECT", "1")
    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.set_caller_phone("9876543210")

    await brain.reply([], "trial start karwa do")
    assert brain.close_signal_fired is True

    await brain.reply(
        [{"role": "assistant", "content": "Bilkul sir! ... WhatsApp number confirm kar dijiye."}],
        "mujhe thoda sochna hai",
    )
    assert brain.close_signal_fired is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_close_signal.py -k close_signal_fired -v`
Expected: FAIL — `AttributeError: 'TelecallerBrain' object has no attribute 'close_signal_fired'`

- [ ] **Step 3: Add the flag**

In `app/voice_agent/telecaller_brain.py`, change (around line 617):

```python
        self.caller_phone: str = ""
```

to:

```python
        self.caller_phone: str = ""
        # True only for the turn in which _on_close_signal() actually performed
        # its durable side-effects (deal write + WhatsApp) -- reset at the top of
        # every reply() call. web_call.py reads this once per turn to decide
        # whether to emit a close_signal WS event (inline trial-signup overlay).
        self.close_signal_fired: bool = False
```

In `_on_close_signal()`, change (around line 798-801):

```python
        """
        if not self.caller_phone:
            return
        try:
```

to:

```python
        """
        if not self.caller_phone:
            return
        self.close_signal_fired = True
        try:
```

In `reply()`, change (around line 1459-1466):

```python
    async def reply(self, history: list[dict[str, str]], user_text: str) -> str:
        """Returns stripped reply text, or "" on ANY failure (caller falls back).

        Pipeline: KB-grounding (niche + client facts) -> free_ai.chat (Cerebras ->
        Groq -> OpenRouter; PRIMARY — free, fast, quota-proof; instant no-op jab
        koi free key set na ho) -> Gemini-direct (multi-key rotation; fallback).
        Repeated-answer guard: bot pichhli line dohraye to ek nudged retry."""
        try:
```

to:

```python
    async def reply(self, history: list[dict[str, str]], user_text: str) -> str:
        """Returns stripped reply text, or "" on ANY failure (caller falls back).

        Pipeline: KB-grounding (niche + client facts) -> free_ai.chat (Cerebras ->
        Groq -> OpenRouter; PRIMARY — free, fast, quota-proof; instant no-op jab
        koi free key set na ho) -> Gemini-direct (multi-key rotation; fallback).
        Repeated-answer guard: bot pichhli line dohraye to ek nudged retry."""
        self.close_signal_fired = False
        try:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_close_signal.py -v`
Expected: PASS — all tests in the file green, including the 3 new ones and the pre-existing ones (`test_on_close_signal_writes_sales_pipeline_deal`, `test_web_call_learns_phone_from_post_close_reply`, etc.) unaffected.

- [ ] **Step 5: Commit**

```bash
git add app/voice_agent/telecaller_brain.py tests/test_voice_close_signal.py
git commit -m "feat(voice): add close_signal_fired per-turn flag to TelecallerBrain"
```

---

## Task 2: Personalize the WhatsApp handoff link

**Files:**
- Modify: `app/voice_agent/telecaller_brain.py:837-845` (`_send_close_whatsapp`)
- Test: `tests/test_voice_close_signal.py`

**Interfaces:**
- Consumes: `self.caller_phone` (digits-only, set via `set_caller_phone`), `self.client_name`, `self.niche` — all already `self.` attributes.
- Produces: no new symbols; `_send_close_whatsapp()`'s message body now contains `https://leadsgenai.in/start?phone=...&biz=...&niche=...` (biz omitted when blank, matching the existing `_on_close_signal` business_name-blank rule for `niche == "ai_marketing"`). Task 5 (`pricing.html`) reads these query params.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_voice_close_signal.py`:

```python
@pytest.mark.asyncio
async def test_send_close_whatsapp_personalizes_link_with_phone_and_niche(monkeypatch):
    from app.integrations import whatsapp as wa

    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("VOICE_CLOSE_WHATSAPP", "1")

    sent = {}

    class FakeSender:
        async def send_text_message(self, to_number, message):
            sent["message"] = message
            return {"ok": True}

    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: FakeSender())
    brain = TelecallerBrain(niche="salon", client_name="Glow Salon")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert "phone=9876543210" in sent["message"]
    assert "biz=Glow%20Salon" in sent["message"]
    assert "niche=salon" in sent["message"]


@pytest.mark.asyncio
async def test_send_close_whatsapp_omits_biz_for_ai_marketing_niche(monkeypatch):
    """ai_marketing persona pitches the platform itself -- client_name holds an
    internal placeholder ("Demo Co"), not the prospect's real business, so the
    personalized link must omit biz= (matches _on_close_signal's existing
    business_name-blank rule for this niche, telecaller_brain.py:807)."""
    from app.integrations import whatsapp as wa

    monkeypatch.setenv("WHATSAPP_AUTO_SEND", "1")
    monkeypatch.setenv("VOICE_CLOSE_WHATSAPP", "1")

    sent = {}

    class FakeSender:
        async def send_text_message(self, to_number, message):
            sent["message"] = message
            return {"ok": True}

    monkeypatch.setattr(wa, "get_whatsapp_sender", lambda: FakeSender())
    brain = TelecallerBrain(niche="ai_marketing", client_name="Demo Co")
    brain.set_caller_phone("9876543210")
    await brain._send_close_whatsapp()
    assert "biz=" not in sent["message"]
    assert "phone=9876543210" in sent["message"]
    assert "niche=ai_marketing" in sent["message"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_voice_close_signal.py -k personalizes_link -v`
Expected: FAIL — `assert "phone=9876543210" in sent["message"]` fails because the current message only contains the bare `https://leadsgenai.in/start` link.

- [ ] **Step 3: Personalize the link**

In `app/voice_agent/telecaller_brain.py`, change (around line 837-845):

```python
        try:
            from app.integrations.whatsapp import get_whatsapp_sender

            link = "https://leadsgenai.in/start"
            msg = (
                "Namaste! LeadGen AI se Swara 🙂 Aapne call pe interest dikhaya — "
                f"7-din FREE trial yahan shuru karein: {link}\n"
                "Koi sawaal ho to isi number pe reply kar dijiye."
            )
            sender = get_whatsapp_sender()
```

to:

```python
        try:
            from urllib.parse import quote

            from app.integrations.whatsapp import get_whatsapp_sender

            params = [f"phone={quote(self.caller_phone)}"]
            biz = self.client_name if self.niche != "ai_marketing" else ""
            if biz:
                params.append(f"biz={quote(biz)}")
            if self.niche:
                params.append(f"niche={quote(self.niche)}")
            link = "https://leadsgenai.in/start?" + "&".join(params)
            msg = (
                "Namaste! LeadGen AI se Swara 🙂 Aapne call pe interest dikhaya — "
                f"7-din FREE trial yahan shuru karein: {link}\n"
                "Koi sawaal ho to isi number pe reply kar dijiye."
            )
            sender = get_whatsapp_sender()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_voice_close_signal.py -v`
Expected: PASS — all tests green, including the pre-existing `test_send_close_whatsapp_sends_when_both_flags_enabled` (still asserts `"leadsgenai.in/start" in sent["message"]`, which remains true since the link now starts with that same base URL plus a query string).

- [ ] **Step 5: Commit**

```bash
git add app/voice_agent/telecaller_brain.py tests/test_voice_close_signal.py
git commit -m "feat(voice): personalize close-signal WhatsApp handoff link with phone/biz/niche"
```

---

## Task 3: `WEBCALL_INLINE_SIGNUP` flag + `close_signal` WS event in `web_call.py`

**Files:**
- Modify: `app/api/web_call.py:21-26` (docstring), `:370-376` (near `_web_call_edge_enabled`), `:1440-1452` (`_brain_turn`)
- Test: `tests/test_web_call_close_signal.py` (new file)

**Interfaces:**
- Consumes: `TelecallerBrain.close_signal_fired`, `.client_name`, `.niche`, `.caller_phone` (Task 1).
- Produces: `_webcall_inline_signup_enabled() -> bool` and `_close_signal_payload(tcbrain: Any) -> dict[str, Any] | None` in `app/api/web_call.py` — both plain functions, importable and unit-testable without a WebSocket. `_close_signal_payload` returns `None` when the flag is off or the turn didn't fire a close-signal; otherwise returns `{"type": "close_signal", "business_name": str, "niche": str, "phone": str}`. Task 4 (`web_call.html`) consumes this exact JSON shape over the WS.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_call_close_signal.py`:

```python
"""Landing-page voice onboarding -- close-signal -> in-page trial-signup
overlay. _close_signal_payload() decides whether to emit a WS close_signal
event so the browser can show the inline-signup overlay right in the call
session (instead of only via the WhatsApp handoff link). Flag-gated
WEBCALL_INLINE_SIGNUP, default OFF.
"""

from __future__ import annotations

from app.api.web_call import _close_signal_payload, _webcall_inline_signup_enabled


class _FakeBrain:
    def __init__(
        self,
        close_signal_fired=False,
        client_name="Demo Co",
        niche="ai_marketing",
        caller_phone="",
    ):
        self.close_signal_fired = close_signal_fired
        self.client_name = client_name
        self.niche = niche
        self.caller_phone = caller_phone


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("WEBCALL_INLINE_SIGNUP", raising=False)
    assert _webcall_inline_signup_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("WEBCALL_INLINE_SIGNUP", "1")
    assert _webcall_inline_signup_enabled() is True


def test_payload_none_when_flag_off(monkeypatch):
    monkeypatch.delenv("WEBCALL_INLINE_SIGNUP", raising=False)
    brain = _FakeBrain(close_signal_fired=True, caller_phone="9876543210")
    assert _close_signal_payload(brain) is None


def test_payload_none_when_not_fired(monkeypatch):
    monkeypatch.setenv("WEBCALL_INLINE_SIGNUP", "1")
    brain = _FakeBrain(close_signal_fired=False)
    assert _close_signal_payload(brain) is None


def test_payload_built_when_flag_on_and_fired(monkeypatch):
    monkeypatch.setenv("WEBCALL_INLINE_SIGNUP", "1")
    brain = _FakeBrain(
        close_signal_fired=True,
        client_name="Glow Salon",
        niche="salon",
        caller_phone="9876543210",
    )
    payload = _close_signal_payload(brain)
    assert payload == {
        "type": "close_signal",
        "business_name": "Glow Salon",
        "niche": "salon",
        "phone": "9876543210",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_web_call_close_signal.py -v`
Expected: FAIL — `ImportError: cannot import name '_close_signal_payload' from 'app.api.web_call'`

- [ ] **Step 3: Add the flag helper + payload builder**

In `app/api/web_call.py`, change (around line 370-376):

```python
def _web_call_edge_enabled() -> bool:
    """FREE EdgeTTS Swara voice on test-call — default ON; WEB_CALL_EDGE_TTS=0 se band."""
    import os

    v = os.environ.get("WEB_CALL_EDGE_TTS", "1").strip().lower()
    return v not in ("0", "false", "no", "off")
```

to:

```python
def _web_call_edge_enabled() -> bool:
    """FREE EdgeTTS Swara voice on test-call — default ON; WEB_CALL_EDGE_TTS=0 se band."""
    import os

    v = os.environ.get("WEB_CALL_EDGE_TTS", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _webcall_inline_signup_enabled() -> bool:
    """Browser-native trial-signup overlay on a voice close-signal (landing-page
    onboarding). Default OFF — new funnel-critical behavior, verify manually
    before enabling in prod. WEBCALL_INLINE_SIGNUP=1 to turn on."""
    import os

    v = os.environ.get("WEBCALL_INLINE_SIGNUP", "0").strip().lower()
    return v in ("1", "true", "yes")


def _close_signal_payload(tcbrain: Any) -> dict[str, Any] | None:
    """WS payload to tell the browser "show the inline trial-signup overlay
    now" -- only when the flag is on AND this exact reply() turn is the one
    that made _on_close_signal() fire for real (deal write + WhatsApp)."""
    if not _webcall_inline_signup_enabled():
        return None
    if not getattr(tcbrain, "close_signal_fired", False):
        return None
    return {
        "type": "close_signal",
        "business_name": getattr(tcbrain, "client_name", "") or "",
        "niche": getattr(tcbrain, "niche", "") or "",
        "phone": getattr(tcbrain, "caller_phone", "") or "",
    }
```

In the module docstring, change (around line 21-26):

```python
Server -> Client (JSON):
    {"type": "ready",  "test_mode": true, "pipeline": false, "providers": {...}}
    {"type": "bot",    "text": "...", "audio_b64": "<base64?>", "test_mode": true}
    {"type": "info",   "text": "..."}
    {"type": "error",  "text": "..."}
    {"type": "pong"}
```

to:

```python
Server -> Client (JSON):
    {"type": "ready",  "test_mode": true, "pipeline": false, "providers": {...}}
    {"type": "bot",    "text": "...", "audio_b64": "<base64?>", "test_mode": true}
    {"type": "info",   "text": "..."}
    {"type": "error",  "text": "..."}
    {"type": "close_signal", "business_name": "...", "niche": "...", "phone": "..."}
        # WEBCALL_INLINE_SIGNUP=1 only -- caller wants to proceed and a phone is
        # known; browser shows the inline trial-signup overlay (see
        # frontend/web_call.html).
    {"type": "pong"}
```

Wire it into `_brain_turn()` — change (around line 1440-1452):

```python
                    _turn_timing["llm_ms"] = int((time.monotonic() - _t_llm) * 1000)
                    if tc_reply:
                        _t_tts = time.monotonic()
                        await _send_tcbrain_sentence_chunks(
                            websocket,
                            sentences=_split_sentences(tc_reply),
                            user_text=user_text,
                            full_reply=tc_reply,
                            llm_stream=False,
                            timing=_turn_timing,
                        )
                        _turn_timing["tts_ms"] = int((time.monotonic() - _t_tts) * 1000)
                    return tc_reply
```

to:

```python
                    _turn_timing["llm_ms"] = int((time.monotonic() - _t_llm) * 1000)
                    if tc_reply:
                        _t_tts = time.monotonic()
                        await _send_tcbrain_sentence_chunks(
                            websocket,
                            sentences=_split_sentences(tc_reply),
                            user_text=user_text,
                            full_reply=tc_reply,
                            llm_stream=False,
                            timing=_turn_timing,
                        )
                        _turn_timing["tts_ms"] = int((time.monotonic() - _t_tts) * 1000)
                    signal_payload = _close_signal_payload(tcbrain)
                    if signal_payload:
                        try:
                            await websocket.send_json(signal_payload)
                        except Exception:
                            pass
                    return tc_reply
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_web_call_close_signal.py -v`
Expected: PASS — all 5 tests green.

- [ ] **Step 5: Commit**

```bash
git add app/api/web_call.py tests/test_web_call_close_signal.py
git commit -m "feat(web-call): flag-gated close_signal WS event for inline trial signup"
```

---

## Task 4: Inline trial-signup overlay in `frontend/web_call.html`

**Files:**
- Modify: `frontend/web_call.html` (banner copy at lines 242, 475-476, 577, 844-846; new overlay markup after line 251; new CSS before line 182; new JS before the "Boot" section at line 1092; new script include after line 1097)
- Create: `scripts/webcall_close_signal_probe.py` (manual verification aid)

**Interfaces:**
- Consumes: `close_signal` WS message `{"type": "close_signal", "business_name": str, "niche": str, "phone": str}` (Task 3). Calls existing `POST /api/public/signup` (`app/api/public_site.py:504`) with `{business_name, email, password, phone, plan: "trial", niche, _turnstile_token}` and reads `window.turnstileToken()` from the existing `/site/turnstile.js` loader (same helper `frontend/pricing.html` already uses). Stores the response's `access_token` under `localStorage["accessToken"]` — same key `pricing.html:361` already uses, so `/app/customer` picks it up identically.

- [ ] **Step 1: Reword the "TEST MODE" banner copy (4 spots, same meaning, less stigma)**

In `frontend/web_call.html`, change (line 242):

```html
    <div class="foot" id="foot"><b>TEST MODE</b> — koi real phone call / charge nahi. Browser me hi bot se baat ho rahi hai.</div>
```

to:

```html
    <div class="foot" id="foot"><b>🔒 Free &amp; safe</b> — koi charge nahi, koi real phone call nahi. Browser me hi AI se baat karke apna free trial shuru karein.</div>
```

Change (lines 475-476):

```javascript
        if(data.responder){
          foot.innerHTML = "<b>TEST MODE</b> · responder: " + data.responder +
            " — koi real phone call / charge nahi.";
        }
```

to:

```javascript
        if(data.responder){
          foot.innerHTML = "<b>🔒 Free &amp; safe</b> · " + data.responder +
            " se baat ho rahi hai — koi charge nahi.";
        }
```

Change (line 577):

```javascript
            foot.innerHTML = "<b>Audio blocked</b> — browser ne awaaz roki. Green Call button dubara dabao (ya ⌨️ se type karo). <b>TEST MODE</b>";
```

to:

```javascript
            foot.innerHTML = "<b>Audio blocked</b> — browser ne awaaz roki. Green Call button dubara dabao (ya ⌨️ se type karo). <b>🔒 Free &amp; safe</b>";
```

Change (lines 844-846):

```javascript
    foot.innerHTML = noSR
      ? "Is browser me voice support nahi — niche type karke baat karein. <b>TEST MODE</b>, no charge."
      : "Mic permission chahiye — ya niche type karke baat karein. <b>TEST MODE</b>, no charge.";
```

to:

```javascript
    foot.innerHTML = noSR
      ? "Is browser me voice support nahi — niche type karke baat karein. <b>🔒 Free</b>, no charge."
      : "Mic permission chahiye — ya niche type karke baat karein. <b>🔒 Free</b>, no charge.";
```

- [ ] **Step 2: Add the overlay CSS**

In `frontend/web_call.html`, change (line 181-182):

```css
  .hist-turn .ts{color:var(--muted);font-size:10px;margin-left:4px}
</style>
```

to:

```css
  .hist-turn .ts{color:var(--muted);font-size:10px;margin-left:4px}

  /* ---- Inline trial-signup overlay (voice close-signal) ---- */
  .signup-overlay{
    position:absolute;inset:0;z-index:50;background:rgba(30,27,46,.55);
    display:flex;align-items:center;justify-content:center;padding:18px;
  }
  .signup-overlay.hidden{display:none}
  .signup-card{
    background:var(--card);border-radius:16px;box-shadow:var(--shadow);
    padding:20px;width:100%;max-width:340px;max-height:88vh;overflow-y:auto;
  }
  .signup-title{font-size:17px;font-weight:800;color:var(--ink);margin-bottom:4px}
  .signup-sub{font-size:12.5px;color:var(--muted);margin-bottom:14px;line-height:1.4}
  .signup-card label{display:block;font-size:12px;font-weight:700;color:var(--ink);margin:10px 0 4px}
  .signup-card input{
    width:100%;border:1px solid var(--line);border-radius:9px;padding:9px 10px;
    font-size:13.5px;font-family:inherit;color:var(--ink);
  }
  .signup-card input:focus{outline:none;border-color:var(--brand-2);box-shadow:0 0 0 3px rgba(79,70,229,.12)}
  .signup-card input[readonly]{background:var(--bg);color:var(--muted)}
  .signup-err{font-size:12px;color:var(--err);margin-top:8px}
  .signup-err.hidden{display:none}
  .signup-card button{
    width:100%;border:none;border-radius:10px;padding:11px;font-size:14px;font-weight:800;
    cursor:pointer;margin-top:14px;font-family:inherit;
  }
  #signupSubmit{background:linear-gradient(135deg,var(--brand),var(--brand-2));color:#fff}
  #signupSubmit:disabled{opacity:.6;cursor:not-allowed}
  .signup-dismiss{background:transparent;color:var(--muted);margin-top:6px !important}
</style>
```

- [ ] **Step 3: Add the overlay HTML**

In `frontend/web_call.html`, change (lines 249-252):

```html
      <div id="historyList"><div class="hist-empty">Loading…</div></div>
    </div>
  </div>
</div>
```

to:

```html
      <div id="historyList"><div class="hist-empty">Loading…</div></div>
    </div>
  </div>

  <!-- Inline trial-signup overlay — shown on voice close-signal when
       WEBCALL_INLINE_SIGNUP=1 (see close_signal WS message handling below). -->
  <div class="signup-overlay hidden" id="signupOverlay">
    <div class="signup-card">
      <div class="signup-title">🎉 Trial shuru karein?</div>
      <div class="signup-sub">Call ki details bhar di hain — bas email aur password confirm karein, 7-din FREE trial turant shuru ho jayega.</div>
      <label for="suBiz">Business ka naam</label>
      <input id="suBiz" type="text" placeholder="e.g. Sharma Solar" />
      <label for="suPhone">Phone</label>
      <input id="suPhone" type="text" readonly />
      <label for="suEmail">Email</label>
      <input id="suEmail" type="email" placeholder="aap@business.com" />
      <label for="suPassword">Password</label>
      <input id="suPassword" type="password" placeholder="min 6 characters" />
      <div data-turnstile-host></div>
      <div class="signup-err hidden" id="signupErr"></div>
      <button id="signupSubmit">Free trial shuru karo</button>
      <button id="signupDismiss" class="signup-dismiss">Baad me karunga</button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Add the `close_signal` WS branch**

In `frontend/web_call.html`, change (lines 510-511):

```javascript
      } else if(data.type === "session_saved"){
        loadCallHistory();
```

to:

```javascript
      } else if(data.type === "session_saved"){
        loadCallHistory();

      } else if(data.type === "close_signal"){
        showSignupOverlay(data.business_name, data.niche, data.phone);
```

- [ ] **Step 5: Add the overlay JS (show/dismiss/submit)**

In `frontend/web_call.html`, change (lines 1091-1093):

```javascript
  // ---- Boot ------------------------------------------------------------
  loadCallHistory();
```

to:

```javascript
  // ---- Inline trial-signup overlay (voice close-signal, WEBCALL_INLINE_SIGNUP) ----
  var signupOverlay = document.getElementById("signupOverlay");
  var suBiz         = document.getElementById("suBiz");
  var suPhone       = document.getElementById("suPhone");
  var suEmail       = document.getElementById("suEmail");
  var suPassword    = document.getElementById("suPassword");
  var signupErr     = document.getElementById("signupErr");
  var signupSubmit  = document.getElementById("signupSubmit");
  var signupDismiss = document.getElementById("signupDismiss");

  function showSignupOverlay(businessName, niche, phone){
    if(!signupOverlay) return;
    suBiz.value = businessName || "";
    suPhone.value = phone || "";
    signupErr.classList.add("hidden");
    signupErr.textContent = "";
    signupOverlay.dataset.niche = niche || "general";
    signupOverlay.classList.remove("hidden");
  }
  if(signupDismiss){
    signupDismiss.onclick = function(){ signupOverlay.classList.add("hidden"); };
  }
  if(signupSubmit){
    signupSubmit.onclick = function(){
      var biz = (suBiz.value || "").trim();
      var email = (suEmail.value || "").trim();
      var password = suPassword.value || "";
      var phone = (suPhone.value || "").trim();
      if(biz.length < 2){
        signupErr.textContent = "Business ka naam likhein (kam se kam 2 characters).";
        signupErr.classList.remove("hidden");
        return;
      }
      if(email.indexOf("@") < 0){
        signupErr.textContent = "Sahi email daalein.";
        signupErr.classList.remove("hidden");
        return;
      }
      if(password.length < 6){
        signupErr.textContent = "Password kam se kam 6 characters ka ho.";
        signupErr.classList.remove("hidden");
        return;
      }
      signupErr.classList.add("hidden");
      signupSubmit.disabled = true;
      signupSubmit.textContent = "Shuru ho raha hai…";
      (window.turnstileToken ? window.turnstileToken() : Promise.resolve(""))
        .then(function(tok){
          return fetch("/api/public/signup", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
              business_name: biz,
              email: email,
              password: password,
              phone: phone,
              plan: "trial",
              niche: signupOverlay.dataset.niche || "general",
              _turnstile_token: tok
            })
          });
        })
        .then(function(r){ return r.json().then(function(d){ return {ok: r.ok, body: d}; }); })
        .then(function(res){
          if(!res.ok){
            signupErr.textContent = (res.body && res.body.detail) || "Signup fail hua, dobara try karein.";
            signupErr.classList.remove("hidden");
            signupSubmit.disabled = false;
            signupSubmit.textContent = "Free trial shuru karo";
            return;
          }
          try{
            if(res.body && res.body.access_token){
              localStorage.setItem("accessToken", res.body.access_token);
            }
          }catch(e){}
          signupOverlay.querySelector(".signup-card").innerHTML =
            '<div class="signup-title">✅ Trial shuru ho gaya!</div>' +
            '<div class="signup-sub">Aapka dashboard taiyaar hai.</div>' +
            '<button id="signupGoDash">Dashboard kholein</button>';
          var goBtn = document.getElementById("signupGoDash");
          if(goBtn){ goBtn.onclick = function(){ location.href = "/app/customer"; }; }
        })
        .catch(function(){
          signupErr.textContent = "Network error — dobara try karein.";
          signupErr.classList.remove("hidden");
          signupSubmit.disabled = false;
          signupSubmit.textContent = "Free trial shuru karo";
        });
    };
  }

  // ---- Boot ------------------------------------------------------------
  loadCallHistory();
```

- [ ] **Step 6: Load the existing Turnstile helper**

In `frontend/web_call.html`, change (lines 1097-1099):

```html
</script>
</body>
</html>
```

to:

```html
</script>
<script src="/site/turnstile.js" defer></script>
</body>
</html>
```

- [ ] **Step 7: Create the manual verification probe script**

Create `scripts/webcall_close_signal_probe.py`:

```python
"""Manual verification for the landing-page voice-onboarding close_signal WS
event (docs/superpowers/plans/2026-07-03-landing-page-voice-onboarding.md).

Drives a scripted web-call conversation through both close-signal turns and
prints every WS message so you can confirm a close_signal event arrives.
Run locally with WEBCALL_INLINE_SIGNUP=1 and CLOSE_DETECT=1 set on the
server process (see uvicorn env), server already running on :8000.

Usage: python scripts/webcall_close_signal_probe.py
"""

import asyncio
import json

import aiohttp


def _is_last_bot_chunk(msg: dict) -> bool:
    if msg.get("type") != "bot":
        return False
    chunk_total = msg.get("chunk_total")
    chunk_index = msg.get("chunk_index")
    if not chunk_total or chunk_index is None:
        return True
    return chunk_index >= chunk_total - 1


async def _drain_turn(ws, label: str, max_messages: int = 12) -> bool:
    """Read messages until the bot's final chunk for this turn, then peek for
    ONE more message with a short timeout (close_signal is sent AFTER the
    sentence chunks finish, so it arrives just after the last "bot" chunk --
    breaking immediately on the last chunk misses it). Returns True if a
    close_signal event was seen along the way."""
    saw_close_signal = False
    for _ in range(max_messages):
        msg = json.loads((await asyncio.wait_for(ws.receive(), 30)).data)
        mtype = msg.get("type")
        if mtype == "bot":
            print(f"{label}: bot", (msg.get("text") or "")[:100])
        elif mtype == "close_signal":
            print(f"{label}: CLOSE_SIGNAL", msg)
            saw_close_signal = True
        else:
            print(f"{label}: {mtype}")
        if _is_last_bot_chunk(msg):
            try:
                trailing = json.loads((await asyncio.wait_for(ws.receive(), 3)).data)
                print(f"{label}: trailing", trailing.get("type"))
                if trailing.get("type") == "close_signal":
                    saw_close_signal = True
            except asyncio.TimeoutError:
                pass
            break
    return saw_close_signal


async def probe() -> None:
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect("http://127.0.0.1:8000/api/web-call/ws", timeout=30) as ws:
            print("ready:", (await ws.receive()).data[:120])
            await ws.send_json({"type": "start", "niche": "ai_marketing", "flow": "qualify"})
            await _drain_turn(ws, "opener")

            await ws.send_json({"type": "user", "text": "trial start karwa do"})
            saw_1 = await _drain_turn(ws, "turn1")

            await ws.send_json({"type": "user", "text": "9876543210"})
            saw_2 = await _drain_turn(ws, "turn2")

            print("SAW close_signal:", saw_1 or saw_2)


if __name__ == "__main__":
    asyncio.run(probe())
```

- [ ] **Step 8: Manually verify in a real browser**

1. Set env vars for a local run: `WEBCALL_INLINE_SIGNUP=1`, `CLOSE_DETECT=1` (default on already), leave `VOICE_CLOSE_WHATSAPP`/`WHATSAPP_AUTO_SEND` unset (irrelevant to the overlay path — those only gate the WhatsApp send, not the WS event).
2. Start the local server (existing project run command) and open `http://localhost:8000/app/test-call`.
3. Tap ⌨️ (keyboard toggle) to use typed input instead of mic.
4. Type `trial start karwa do`, send. Bot should ask to confirm a WhatsApp number.
5. Type `9876543210`, send. The signup overlay should appear, prefilled with Phone `9876543210`.
6. Fill Business/Email/Password, submit. Expect either a success card ("✅ Trial shuru ho gaya!") or a clear inline error (e.g. Turnstile not configured locally is fine — `TURNSTILE_SECRET_KEY` unset makes the server-side check a no-op per `app/security/turnstile.py:124`).
7. Also run `python scripts/webcall_close_signal_probe.py` against the same running server and confirm `SAW close_signal: True` in the output.

- [ ] **Step 8.5: Two real bugs found during Step 8 live verification, fixed same-scope**

Live browser testing (not just the pytest suite) surfaced two pre-existing bugs outside this plan's original file list, both directly blocking the overlay's actual usability — fixed here rather than filed for later, since they'd otherwise make Task 4 look done while silently broken for any tester with Turnstile disabled (every local/dev environment) or any signup failure (every environment):

1. **`frontend/website/turnstile.js` — `turnstileToken()` hung 30s when Turnstile is disabled.** The shared `ready` flag flips true both when disabled (via `boot()`'s early-exit) and when an enabled widget merely *renders* (before it's solved) — `turnstileToken()`'s fast-path only checked `!ready`, so once `ready` was true, EVERY subsequent call (after boot()'s one-time flush) fell through to the 30s wait-for-widget branch, which never resolves when no widget was ever rendered. Fixed by adding a dedicated `disabled` flag, set permanently true only in the disabled/error paths of `boot()`, checked first in `turnstileToken()`. This is pre-existing code already used identically by `pricing.html` — the fix benefits both.
2. **`frontend/web_call.html` (and `frontend/pricing.html`, same pattern) — error responses always showed the generic fallback text, never the real reason.** `app/exceptions.py`'s global `http_exception_handler` wraps every `HTTPException` as `{"error": {"code", "message", "request_id"}}`, not FastAPI's default `{"detail": "..."}"`. Both files' signup-error handling read `.detail` (never present in this shape), so a live 409 "business already registered" always displayed "Signup fail hua, dobara try karein." Fixed both to read `(body.error && body.error.message) || body.detail || <fallback>`.

Verified live (see Step 8 transcript): overlay renders prefilled → Turnstile resolves instantly (no hang) → duplicate-business submit shows the real 409 message → fresh-data submit returns 200, `localStorage.accessToken` set (225-char JWT), success card renders.

- [ ] **Step 9: Commit**

```bash
git add frontend/web_call.html frontend/website/turnstile.js frontend/pricing.html scripts/webcall_close_signal_probe.py
git commit -m "feat(web-call): inline trial-signup overlay on voice close-signal

Also fixes two pre-existing bugs found during live verification: turnstile.js
token-resolution hang when Turnstile is disabled, and signup error messages
reading the wrong response-body field (both files)."
```

---

## Task 5: Prefill `/pricing` from the personalized WhatsApp handoff link

**Files:**
- Modify: `frontend/pricing.html:320` (after `closeModal()`)

**Interfaces:**
- Consumes: `?phone=&biz=` URL query params (Task 2's personalized WhatsApp link points here) and the existing `startTrial()` function (`pricing.html:312-319`) plus the existing `#f-biz`/`#f-phone` inputs (`pricing.html:182,184`).

- [ ] **Step 1: Add the prefill snippet**

In `frontend/pricing.html`, change (line 320):

```javascript
function closeModal(){ document.getElementById("ov").classList.remove("on"); }
```

to:

```javascript
function closeModal(){ document.getElementById("ov").classList.remove("on"); }

(function prefillFromVoiceHandoff(){
  try{
    var qs = new URLSearchParams(location.search);
    var phone = (qs.get("phone") || "").trim();
    var biz = (qs.get("biz") || "").trim();
    if(!phone && !biz) return;
    startTrial();
    if(biz) document.getElementById("f-biz").value = biz;
    if(phone) document.getElementById("f-phone").value = phone;
  }catch(e){}
})();
```

- [ ] **Step 2: Manually verify**

Open `http://localhost:8000/pricing?phone=9876543210&biz=Glow%20Salon` in a browser. Expect: the "Start FREE Trial" modal opens automatically, Business field pre-filled `Glow Salon`, Phone field pre-filled `9876543210`.

- [ ] **Step 3: Commit**

```bash
git add frontend/pricing.html
git commit -m "feat(pricing): prefill trial signup from voice close-signal handoff link"
```

---

## Task 6: Promote the `/app/test-call` hero CTA on the landing page

**Files:**
- Modify: `frontend/website/index.html:334`

**Interfaces:** None — pure copy/class change, no new symbols.

- [ ] **Step 1: Upgrade the CTA**

In `frontend/website/index.html`, change (line 334):

```html
        <a class="btn btn-ghost" href="/app/test-call">🎧 Live Demo suno (FREE)</a>
```

to:

```html
        <a class="btn btn-primary" href="/app/test-call">📞 AI se baat karo — free trial shuru karo</a>
```

- [ ] **Step 2: Manually verify**

Open `http://localhost:8000/` and confirm the hero CTA row shows the new button with primary (filled, brand-colored) styling matching the "10 FREE leads chahiye?" button, linking to `/app/test-call`.

- [ ] **Step 3: Commit**

```bash
git add frontend/website/index.html
git commit -m "feat(landing): promote voice-call CTA to primary hero button"
```

---

## Task 7: Full regression + flag documentation

**Files:** none new — verification only.

- [ ] **Step 1: Run the full touched-area test suite**

Run:
```
python -m pytest tests/test_voice_close_signal.py tests/test_web_call_close_signal.py tests/test_web_call_store.py tests/test_web_call_edge.py tests/test_voice_booking_wire.py -v
```
Expected: all PASS, zero regressions.

- [ ] **Step 2: Run the project's production-readiness check**

Run: `python scripts/prod_check.py`
Expected: green (import-safe, no route collisions — `/app/test-call` route unchanged, only its served file content changed).

- [ ] **Step 3: Confirm the new flag defaults OFF (no prod behavior change until explicitly enabled)**

Run:
```
python -c "import os; os.environ.pop('WEBCALL_INLINE_SIGNUP', None); from app.api.web_call import _webcall_inline_signup_enabled; assert _webcall_inline_signup_enabled() is False; print('OK: default OFF')"
```
Expected: `OK: default OFF`

- [ ] **Step 4: Final commit (if any working-tree changes remain)**

```bash
git status
```
Expected: clean (everything already committed per-task in Tasks 1-6). If not, commit remaining files with a summary message.

---

## Self-Review

**Spec coverage:**
- Spec §3 "Personalized handoff link" → Task 2. ✓
- Spec §4 "Same-session in-page signup" → Tasks 1, 3, 4. ✓
- Spec §1 "Landing-page CTA" → Task 6. ✓
- Spec §2 "Honest, trust-building copy" → Task 4 Step 1. ✓
- Spec's `/pricing` prefill (part of §3) → Task 5. ✓
- Spec "Explicitly OUT of scope" items (voice-spoken password, new OTP system, new URL alias, touching `/app/test-call` internal behavior) → none of the 7 tasks do any of these. ✓

**Placeholder scan:** No TBD/TODO; every step has complete, literal code (no "similar to Task N" references — Task 4 Step 5's JS and Task 2's Python are both written out in full even though the shape mirrors `pricing.html`'s existing pattern).

**Type/name consistency check:** `close_signal_fired` (Task 1) is read the same way in Task 3's `_close_signal_payload`. `_close_signal_payload`'s returned dict keys (`business_name`, `niche`, `phone`) match exactly what Task 4's `showSignupOverlay(data.business_name, data.niche, data.phone)` reads. `access_token` (server field, confirmed at `public_site.py:686`) matches what Task 4's JS reads (`res.body.access_token`) and the `localStorage` key `"accessToken"` matches the existing convention already used in `pricing.html:361` and 35+ other frontend files (verified via repo-wide grep before writing this plan) — a customer who signs up via the call and one who signs up via the form land in an identical logged-in state.
