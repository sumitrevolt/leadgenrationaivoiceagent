# Voice Hot Path Protection

The phone-call loop must never block or die because of an optional subsystem.

- Optional deps (observability, tracing) import behind try/except with a **no-op fallback** — hot path unchanged if module absent:

```python
try:
    from app.observability_llm import llm_span as _llm_span
except Exception:
    @contextmanager
    def _llm_span(*_a, **_k):
        yield _NoopSpan()
```

- ML/KB work on a public endpoint: `asyncio.to_thread` + hard deadline + disable-switch (3 prod-downs came from skipping this).
- **Pinned truths:** `USE_SILERO_VAD=0` (=1 made every call deaf), `edge-tts >= 7.2.0` (else 403). Don't "upgrade" these without a phone-call test.
- Audio stream = L16/16k over WS `/api/telephony/vobiz/stream/{token}`.
- Vobiz = India telephony; Twilio = international-only (foreign trunk domestic = ILLEGAL).
