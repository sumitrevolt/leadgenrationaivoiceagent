# Swara Voice Fix — recording + turn-taking (2026-08-24)

> Owner runbook. Two minimal, **idempotent** fixes for the live Vobiz call symptoms
> (admin sees recordings but owner hears nothing; Swara hiccups/confuses on the 2nd
> exchange). Both are production voice code (Swara) — owner-unfrozen this session
> ("sab karo"). No compliance gate touched (DND/TRAI/consent unchanged).

## Symptom → root

1. **Recording inaudible / missing Swara** → `vobiz_stream.py` call-recording
   **master clock** (`_rec_timeline_samples`) only advanced on **caller** frames, so
   during Swara's reply it froze; when the caller spoke again the *next* caller
   utterance was written at the stale position and **overwrote the bot's audio** →
   the mixed WAV was garbled / missing Swara's side. Fix advances the master clock
   on the bot too, so the caller writes at the true position (linear timeline).
2. **2nd-exchange confusion** → `_speaking` could get **stuck True** (documented in
   code; a play cancelled via `_stop_playback_only()` is not cleared by the canceller),
   so the customer's 2nd turn is treated as barge/superseded and skipped → Swara
   confuses/hiccups. Fix guarantees `_speaking`/`_disclosure_active` are cleared on
   play cancellation too (idempotent — no happy-path change).

## Commits (branch `fix/swara-recording-timeline`)
| Commit | Change |
|--------|--------|
| `ea3fd86a` | recording master-clock advances on bot audio (caller-overwrite fix) |
| `ca31020f` | `_speaking`/`_disclosure_active` cleared on play cancellation (stuck-speaking leak) |

Verification already done: **voice self-test SCORE=1.0 STATUS=OK** (personas 7/7, TTS OK,
STT OK), `py_compile` OK, and a standalone simulation proves the recording fix
(caller's 2nd utterance lands after the bot — no overwrite).

## Deploy (owner)
```
git push -u origin fix/swara-recording-timeline   # (after merge to main; repo is PR-only)
# VPS:
cd /opt/leadgen && git pull
setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &   # poll /tmp/dep.log + /health.version
```

## Verify (live call)
1. Place ONE outbound live call.
2. **Recording:** open the call recording — you should hear **both** the customer AND
   Swara. (It was blank/missing-Swara before.)
3. **Turn-taking:** have the customer reply twice — Swara should not hiccup/confuse on
   the 2nd exchange (if she still does, see the config step below).
4. `python -m app.voice_agent.self_test` → `SCORE=1.0 STATUS=OK`.

## If 2nd-exchange confusion STILL happens after the fix (config check)
These are config (`.env` on VPS), not the code:
```
docker exec leadgen_app printenv USE_SILERO_VAD VOBIZ_SILENCE_MS
# USE_SILERO_VAD should be 0  (documented landmine: =1 makes the turn gate misfire)
# VOBIZ_SILENCE_MS default is 500 (2026-08-23 owner latency change). If cutoffs
#   persist, bump it to 650 (turn_detector canonical is 700) and recreate app.
```

## Rollback
- `git revert ea3fd86a ca31020f` (both are isolated; no data migration, no compliance gate).
- Or `docker compose -f docker-compose.vps.yml up -d --no-deps app` after revert + deploy.
