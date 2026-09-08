# Swara Call-Flow QA Checklist — 2026-09-08

**Owner symptom:** calls disconnect immediately as they connect/answer.
**Owner claim:** API key is configured, **DID number is not configured**.
**App:** https://leadsgenai.in · container `leadgen_app` · image `3939c2d4` · checkout `/opt/leadgen` @ `b1030d7e`

This doc defines, in **testable** terms, what "the end-to-end smart call flow works" means, and gives the evidence we currently have.

---

## 0. One-command verification

```bash
bash /opt/leadgen/scripts/verify_swara_callflow.sh          # 60m lookback, 8s min call
bash /opt/leadgen/scripts/verify_swara_callflow.sh 180      # 3h lookback
bash /opt/leadgen/scripts/verify_swara_callflow.sh 60 15    # require >=15s calls
```

Exit `0` = all PASS (or warnings only). Exit `1` = at least one FAIL. **Read-only** — it changes nothing.

Regression suite (hermetic, CI-safe):

```bash
cd /opt/leadgen && python -m pytest tests/test_swara_smartflo_callflow.py -q
```

---

## 1. Definition of "the smart flow works" (acceptance criteria)

A call **PASS**es only if **every** row below is true. `N` = 8 seconds default (`MIN_CALL_SEC`).

| # | Criterion | How we measure it | Source of truth |
|---|-----------|-------------------|-----------------|
| A1 | Call connects and stays up ≥ N seconds | artifact `ended_at - started_at` ≥ N | `call_transcripts/*.json` |
| A2 | Greeting actually plays | session `hist[0]` exists, contains AI-disclosure; ≥1 outbound `media` event sent | unit test + WS log |
| A3 | Caller audio is received | `media_frames > 0` **and** `caller_rms_max > 100` | artifact + unit test |
| A4 | STT produces text | a `user` turn appears in `messages` with non-empty text | artifact `messages` |
| A5 | LLM replies | an `assistant` turn follows the `user` turn | artifact `messages` |
| A6 | TTS audio is sent back | ≥1 outbound `media` event after the first user turn | WS send log |
| A7 | Barge-in works | caller speech during playback → outbound `clear` event, playback stops | unit test `test_barge_in_clears_playback` |
| A8 | No premature drop | WS stays open for the whole call; no `1005` / `WS error` | `docker logs leadgen_app` |
| A9 | Post-call artifact written, sane numbers | `duration ≥ N`, `media_frames > 0`, `caller_rms_max > 0`, `messages ≥ 2` | artifact |
| A10 | Compliance intact | AI-disclosure present; DND/TRAI-window/consent gates **not** bypassed | `app/telephony/compliance.py` |

> **A10 is non-negotiable.** No fix may weaken DND, the TRAI 09:00–21:00 window, consent, or the AI-disclosure. If a fix requires that, stop and escalate instead.

---

## 2. What we actually observed on prod (evidence, 2026-09-08)

### R1 — Stream is dropped during the handshake (~58 ms)

```
08:06:38.612  "WebSocket /api/telephony/smartflo/stream" [accepted]     <- 49.249.27.174
08:06:38.612  [smartflo-stream] WS open niche=general client=None (STT=True TTS=True audioop=True)
08:06:38.670  [smartflo-stream] WS error: (<CloseCode.NO_STATUS_RCVD: 1005>, '')
```

`1005 NO_STATUS_RCVD` = peer closed without a close frame. **No `connected` event and no `start` event was ever received** → the provider never completed the handshake. This is a *provider-side / config-side* teardown, not an exception in our code.

### R2 — DID / caller-ID env, as seen by the app container

| Key | Value | Verdict |
|-----|-------|---------|
| `TELEPHONY_PROVIDER` | `vobiz` | active provider |
| `VOBIZ_CALLER_ID` | `+911171366938` | set |
| `TATA_SMARTFLO_DID` | `918069879757` | set — **but see R3** |
| `TATA_SMARTFLO_ENABLED` | **unset** | ⇒ `tata_smartflo` trunk is excluded from `pick_trunk()` |
| `SIP_DID` | **EMPTY** | matches owner's "DID not configured" |
| `SIP_HOST` / `SIP_USERNAME` / `SIP_PROVIDER` | **EMPTY** | SIP handler `configured=False` |
| `JIO_SIP_DID` | unset | not in use |
| `SMARTFLO_WS_HOST` | `leadsgenai.in` | bare host — correct for `wss://{host}/...` |
| `SMARTFLO_VOICE_STREAM_ENABLED` | `1` | endpoint armed |

**Note the mismatch:** `VOBIZ_CALLER_ID=+911171366938` vs `TATA_SMARTFLO_DID=918069879757` — two different numbers. Whichever provider is active, the DID must be one *actually assigned to that account*.

### R3 — FreeSWITCH `vobiz` gateway is **NOREG**

```
$ docker exec leadgen-freeswitch fs_cli -x 'sofia status gateway'
external::vobiz   sip:leadgenfs@1a7ce9d9.sip.vobiz.ai   NOREG   3.73   0/0   0/0
```

Ping 3.73 ms but state `NOREG` → SIP REGISTER is not established. Any call routed over this trunk will fail on connect.

### R4 — No real call artifacts; only synthetic probes

```
smartflo_20260908_044643_probe-stream.json  media_frames=5   caller_rms_max=0   1 msg
smartflo_20260908_044415_probe-stream.json  media_frames=0   caller_rms_max=0   1 msg
```

`caller_rms_max = 0` ⇒ no audible caller audio ever reached the bot. **No real call has completed since the incident began.**

### R5 — Post-call metering is silently broken (code defect, not the outage cause)

`app/telephony/smartflo_stream.py::_cleanup()` calls:

```python
await meter_call_completion(client_id=..., call_duration_s=..., user_turns=..., metadata=...)
```

but the real signature is `meter_call_completion(call_id, *, client_id, duration_seconds, ...)`.
→ `TypeError`, swallowed by `except Exception: pass`. **Calls are never metered.**
Covered by `test_cleanup_meters_call_with_usable_duration` (marked `xfail`, will auto-flip when fixed).

### R6 — **P0: the checked-out source tree does not even parse (232 broken files)**

`/opt/leadgen` @ `b1030d7e` is **syntactically invalid in 232 of 1856 `.py` files**. It cannot be imported, tested, or deployed.

```
$ python3 /opt/leadgen/scripts/qa_scan_syntax.py /opt/leadgen app tests
scanned 1856 .py files under app, tests
BROKEN: 232
  app/utils/logger.py:122              unterminated string literal
  app/utils/jwt_versioning.py:185      unterminated string literal
  app/telephony/compliance.py:220      unterminated string literal
  app/telephony/trunks.py:86           unterminated string literal
  app/api/okf_admin.py:27              unterminated string literal
  ... (232 total)
```

Sample (`app/api/okf_admin.py`) — a long string was wrapped across a newline:

```python
        description="Ignored in prod paths - kept for explicitness
        flag must still be ON.",        # <-- SyntaxError
```

**Why prod still works:** the running container is image `3939c2d4`, built from an earlier commit. The same scan against the image is clean:

```
$ docker run ... ghcr.io/.../leadgenrationaivoiceagent:3939c2d4 python /scan.py /app app
scanned 944 .py files under app
BROKEN: 0
```

**Origin:** `app/utils/logger.py` compiles at `a1cff664^` and is broken at `a1cff664`
("fix(ci): fix W291, W292, W293, E701 whitespace issues") — an automated lint pass
split long string literals across lines. Working tree == HEAD blob (verified by
`git hash-object`), so this is committed, not a local edit.

**Impact:** **any `git pull` + rebuild on this box = instant crash.** Fix the tree
(or pin the deploy to the known-good commit) *before* rebuilding.

**Suggested fix shape** (per occurrence — close the string, then re-open with implicit concatenation):

```python
    + r')\s*[=:]\s*("[^"]{1,4096}"|\'[^\']{1,4096}\'|[^\s&,'
    + r'\)]\}"]{1,4096})',
```

**How to run the regression suite today** (the checkout cannot load `tests/conftest.py`):

```bash
docker run --rm -u 0:0 --network=none -w /app \
  -v /opt/leadgen/tests/test_swara_smartflo_callflow.py:/app/tests/test_swara_smartflo_callflow.py:ro \
  ghcr.io/sumitrevolt/leadgenrationaivoiceagent:3939c2d4 \
  /opt/venv/bin/python -m pytest tests/test_swara_smartflo_callflow.py -v --noconftest
# -> 10 passed, 1 xfailed
```

---

## 3. Manual QA runbook (do this after the fix lands)

1. `bash /opt/leadgen/scripts/verify_swara_callflow.sh` → expect **ALL PASS**.
2. Place one real test call (admin auth required — a bare `POST /api/telephony/smartflo/test-call` returns 401 without it).
3. While on the call, tick off A1–A10 by hand:
   - hear the greeting (AI-disclosure) — A2
   - speak; confirm the bot transcribes and answers — A3, A4, A5, A6
   - talk **over** the bot; confirm it stops — A7
   - stay on the call ≥ 15 s — A1, A8
4. Re-run the verifier: the newest artifact must show `media_frames > 0`, `caller_rms_max > 100`, `duration ≥ 15`, `messages ≥ 2` — A9.
5. Re-run the suite: `python -m pytest tests/test_swara_smartflo_callflow.py -q` → all green.

---

## 4. Triage order (highest-suspicion first)

0. **R6 — do not rebuild until the tree is fixed.** 232 unparseable files; a rebuild from `main` crashes on boot. Independent of the disconnect, but it will bite the moment the fix is deployed.
1. **R3 — gateway `NOREG`.** Most consistent with "connects then instantly drops". Fix registration (`sofia profile external restart reloadxml`, check `VOBIZ_SIP_USER` / `VOBIZ_SIP_PASS` / `VOBIZ_TRUNK_DOMAIN`).
2. **R2 — DID not owned by the active provider / `TATA_SMARTFLO_ENABLED` unset.** A caller-ID the provider does not recognise is rejected at setup → immediate teardown. Confirm which of `+911171366938` / `918069879757` belongs to the account actually carrying the call, and arm the matching trunk flag.
3. **R1 — SmartFlo Voice Bot channel not configured in the portal.** If the Voice-Bot wss endpoint is not attached to the DID, SmartFlo opens the socket and immediately closes it — exactly the 58 ms `1005` signature.
4. **R5 — metering bug.** Fix separately; it is a billing defect, not the outage.

---

## 5. Guardrails

- Never set `DND_FAIL_OPEN=1` in production (currently `DND_FAIL_OPEN=0` — correct, fail-closed).
- Never widen the TRAI promotional window past 09:00–21:00 IST.
- Never bypass consent / opt-out (`persist_opt_out`, DTMF `9`).
- Always keep the AI-disclosure in the opener (asserted by the regression test).
