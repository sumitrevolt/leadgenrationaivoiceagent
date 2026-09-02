"""
Advanced voice-agent self-test — drives the FREE web-call brain over scripted
conversations and returns a CI-gateable verdict.
================================================================================

Runs the SAME TelecallerBrain the phone agent uses, over the web-call WebSocket
(`/api/web-call/ws`) in text mode — FREE, no telephony, no paid STT/TTS/LLM key.

What it checks per scenario (catalogue in app/voice_agent/voice_selftest.py):
  MECHANICAL (gates the build, exit 1):
    NO_REPLY / DOUBLE_REPLY / EMPTY / BANNED-phrase / SERVER_CLOSED / CRASH
  SOFT mechanical (gates only with --strict):
    TOO_LONG (>35w) / SLOW (>9s) / REPEAT
  BEHAVIOURAL + GUARDRAIL + GOAL (advisory; --strict to gate):
    pushy-after-soft-no / talk-listen-ratio / missing-permission /
    missing-AI-disclosure (TRAI/DPDP) / literal-translation /
    prompt-injection-obeyed / PII-leak / per-scenario goal misses

Objective numbers in the scorecard:
  * latency P50/P95/P99 (distribution, not average)
  * quality_score = mean goal pass-rate (feeds eval_gate baseline when EVAL_GATE=1)
  * roundtrip-WER/CER per Swara line (opt-in --audio; FREE via Groq-whisper) —
    DIAGNOSTIC only, never gates (Devanagari↔roman folded via hinglish_normalize).

VOICE-ENGINE TESTER (2026-08-06): this script is ALSO the voice-engine tester —
every run can persist the driven test-call transcripts + audio into the SAME
stores the call-analysis pipeline reads (data/call_transcripts/YYYY-MM-DD.jsonl +
data/call_recordings/YYYY-MM-DD/webcall_test_*.mp3), so synthetic test data flows
into scripts/voice_call_analysis.py / live_eval / campaign_optimizer exactly like
real Vobiz calls — and --baseline diffing turns it into a before/after regression
harness for latency + quality.

Exit codes:
  0 = pass (or SKIP when no server is reachable — a local box with no app running
      is NOT a failure), 1 = a real run found a gating finding.

Run:
  local   : python scripts/agent_tester.py            # needs uvicorn on :8000
  VPS box : AGENT_TESTER_WS=ws://127.0.0.1:8080/api/web-call/ws python scripts/agent_tester.py
  live    : python scripts/agent_tester.py --url wss://leadsgenai.in/api/web-call/ws
  strict  : python scripts/agent_tester.py --strict   # behavioural/guardrail also gate
  audio   : python scripts/agent_tester.py --audio    # add roundtrip-WER (uses Groq quota)
  record  : python scripts/agent_tester.py --record   # persist transcripts+audio into analysis store
  baseline: python scripts/agent_tester.py --baseline report_before.json --json
                                                     # diff vs a saved prior run
  ci/json : python scripts/agent_tester.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

import aiohttp

# Windows cp1252 console can't encode emojis (❌/✅/⏱) used below — force UTF-8
# so the scorecard prints instead of crashing mid-print. No-op on Linux/Mac.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - older python
    pass

# In --json mode, ONLY the JSON object may reach stdout (CI runs json.loads on
# it) — but the app logger writes INFO to stdout the moment app.* is imported.
# Capture all import-time + runtime stdout into a buffer here (before importing
# app.*) and emit the JSON to the saved real stdout at the very end.
_JSON_MODE = "--json" in sys.argv
_REAL_STDOUT = sys.stdout
if _JSON_MODE:
    import io

    sys.stdout = io.StringIO()

# Make `app...` importable when run as a bare script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.voice_agent import voice_selftest as vs  # noqa: E402  (after sys.path tweak)

try:  # D-13 conversation QA judges (pushy/talk-ratio/permission/literal)
    from app.voice_agent import qa_checks as _qc
except Exception:  # pragma: no cover
    _qc = None

try:  # objective latency distribution (pure stdlib, import-safe)
    from app.voice_agent import voice_metrics as _vm
except Exception:  # pragma: no cover
    _vm = None

# Host/local default. IN-CONTAINER the app listens on :8080 (compose maps host
# 127.0.0.1:8000 -> container 8080) — set AGENT_TESTER_WS to ws://127.0.0.1:8080/...
DEFAULT_WS = os.environ.get("AGENT_TESTER_WS") or "ws://127.0.0.1:8000/api/web-call/ws"

BANNED = [
    "maine pehle",
    "pehle hi poocha",
    "unclear",
    "maaf kij",
    "[echo",
    "(no response)",
    "<think",  # chain-of-thought/reasoning leak — never speakable to a caller
    "thinking process",
]

_SCN_BY_NAME = {s.name: s for s in vs.SCENARIOS}


# --------------------------------------------------------------------------- #
# WS collection — one logical reply per bot turn (streaming chunks merged).
# --------------------------------------------------------------------------- #
async def _collect_replies(ws, first_timeout=12.0, settle=2.5):
    """Collect bot replies in a window. Returns (replies, ws_closed) where each
    reply is {"text", "audio_b64"}. Sentence-streamed replies (chunk_total>1)
    count as ONE reply (text from full_text); their audio is per-chunk/partial so
    we drop it for roundtrip (only clean single-message replies carry audio)."""
    replies: list[dict] = []
    while True:
        timeout = first_timeout if not replies else settle
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
        except asyncio.TimeoutError:
            break
        if msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
            return replies, True
        if msg.type != aiohttp.WSMsgType.TEXT:
            break
        try:
            d = json.loads(msg.data)
        except Exception:
            continue
        if d.get("type") != "bot":
            continue
        ct = d.get("chunk_total")
        if ct and ct > 1:
            if d.get("chunk_index", 0) == 0:
                replies.append(
                    {"text": (d.get("full_text") or d.get("text") or "").strip(), "audio_b64": None}
                )
            # later chunks of the same reply — skip
        else:
            replies.append({"text": (d.get("text") or "").strip(), "audio_b64": d.get("audio_b64")})
    return replies, False


async def run_scenario(session, scenario, ws_url, *, collect_audio=False, verbose=True) -> dict:
    """Drive one scenario over the WS. Returns a structured result:
    {name, kind, status: ran|skip, skip_reason, transcript, mechanical[str],
     latencies[ms], audio_pairs[(text, b64)]}."""
    res = {
        "name": scenario.name,
        "kind": scenario.kind,
        "niche": scenario.niche,
        "flow": scenario.flow,
        "status": "ran",
        "skip_reason": None,
        "transcript": [],
        "mechanical": [],
        "latencies": [],
        "audio_pairs": [],
        "turns_attempted": 0,
        "missed": 0,
    }
    transcript: list[dict] = res["transcript"]
    mech: list[str] = res["mechanical"]
    lat: list[float] = res["latencies"]

    connected = False
    try:
        async with session.ws_connect(ws_url, timeout=aiohttp.ClientWSTimeout(ws_close=60)) as ws:
            connected = True
            # drain {"type":"ready"} before sending anything
            try:
                ready = await asyncio.wait_for(ws.receive(), timeout=15.0)
                if ready.type != aiohttp.WSMsgType.TEXT:
                    mech.append(f"NO_READY: got type={ready.type}")
                    return res
            except asyncio.TimeoutError:
                mech.append("NO_READY: timeout waiting for ready")
                return res

            await ws.send_json({"type": "start", "niche": scenario.niche, "flow": scenario.flow})
            greeting, closed = await _collect_replies(ws, first_timeout=12.0, settle=3.0)
            if closed:
                mech.append("SERVER_CLOSED: closed after start (no greeting)")
                return res
            if greeting:
                g = (greeting[0]["text"] or "").strip()
                if g:
                    transcript.append({"role": "assistant", "content": g})
                if collect_audio and scenario.kind == "happy":
                    for r in greeting:
                        if r.get("audio_b64") and (r.get("text") or "").strip():
                            res["audio_pairs"].append((r["text"], r["audio_b64"]))
            else:
                mech.append("NO_GREETING: opener never sent")

            last_reply = ""
            for turn in scenario.turns:
                await ws.send_json({"type": "user", "text": turn, "niche": scenario.niche})
                transcript.append({"role": "user", "content": turn})
                res["turns_attempted"] += 1
                t0 = time.time()
                replies, closed = await _collect_replies(ws, first_timeout=12.0, settle=2.5)
                if closed:
                    mech.append(f"SERVER_CLOSED: closed mid-turn for {turn!r}")
                    res["missed"] += 1
                    break
                dt = time.time() - t0
                bots = [r["text"] for r in replies]
                n = len(bots)
                if n > 0:
                    lat.append(dt * 1000.0)
                else:
                    res["missed"] += 1
                reply = (bots[0] if bots else "").strip()
                if reply:
                    transcript.append({"role": "assistant", "content": reply})
                    if collect_audio and scenario.kind == "happy":
                        for r in replies:
                            if r.get("audio_b64") and (r.get("text") or "").strip():
                                res["audio_pairs"].append((r["text"], r["audio_b64"]))

                # MECHANICAL observations (kinds drive severity in voice_selftest)
                if n == 0:
                    mech.append(f"NO_REPLY for {turn!r}")
                if n > 1:
                    mech.append(f"DOUBLE_REPLY ({n}) for {turn!r}: {bots}")
                if n > 0 and not reply:
                    mech.append(f"EMPTY reply for {turn!r}")
                low = reply.lower()
                for b in BANNED:
                    if b in low:
                        mech.append(f"BANNED phrase '{b}' in: {reply!r}")
                if reply and reply == last_reply:
                    mech.append(f"REPEAT reply: {reply!r}")
                if len(reply.split()) > 35:
                    mech.append(f"TOO_LONG ({len(reply.split())}w): {reply!r}")
                if dt > 9:
                    mech.append(f"SLOW {dt:.1f}s for {turn!r}")
                last_reply = reply
                if verbose:
                    print(
                        f"  [{scenario.name}] U: {turn}\n           B({n}, {dt:.1f}s): {reply[:90]}"
                    )
    except Exception as e:
        conn_errs = (aiohttp.ClientConnectorError, OSError, asyncio.TimeoutError)
        if not connected and isinstance(e, aiohttp.WSServerHandshakeError):
            mech.append(f"PROTOCOL: WS handshake failed (status={getattr(e, 'status', '?')})")
        elif not connected and isinstance(e, conn_errs):
            res["status"] = "skip"
            res["skip_reason"] = type(e).__name__
        else:
            mech.append(f"CRASH: {type(e).__name__}: {str(e)[:120]}")
    return res


# --------------------------------------------------------------------------- #
# Roundtrip-WER (opt-in, diagnostic, FREE via Groq-whisper)
# --------------------------------------------------------------------------- #
async def roundtrip_block(audio_pairs, *, flag_cer=0.35) -> dict:
    """text -> (already-synthesised Swara mp3) -> Groq-whisper -> WER/CER vs text.
    Devanagari↔roman folded via hinglish_normalize so the score reflects Swara
    intelligibility, not script mismatch. DIAGNOSTIC only — never gates."""
    try:
        import base64

        from app.voice_agent import free_ai
        from app.voice_agent import voice_metrics as vm
    except Exception as e:  # pragma: no cover
        return {"available": False, "reason": f"import: {e}"}
    try:
        from app.voice_agent.hinglish_normalize import to_roman
    except Exception:  # pragma: no cover

        def to_roman(x):  # type: ignore[misc]
            return x

    rows = []
    for text, b64 in audio_pairs:
        try:
            audio = base64.b64decode(b64)
            recog, _src = await free_ai.transcribe_audio(
                audio, language="hi", filename="audio.mp3", mime="audio/mpeg"
            )
        except Exception as e:
            rows.append({"text": text, "wer": None, "cer": None, "error": str(e)[:100]})
            continue
        if not (recog or "").strip():
            rows.append({"text": text, "wer": None, "cer": None, "error": "empty transcription"})
            continue
        ref, hyp = to_roman(text), to_roman(recog)
        w, c = vm.wer(ref, hyp), vm.cer(ref, hyp)
        rows.append(
            {
                "text": text,
                "recog": recog,
                "wer": round(w, 3),
                "cer": round(c, 3),
                "flagged": c > flag_cer,
            }
        )
    scored = [r for r in rows if r.get("cer") is not None]
    return {
        "available": True,
        "n": len(scored),
        "mean_wer": round(sum(r["wer"] for r in scored) / len(scored), 3) if scored else None,
        "mean_cer": round(sum(r["cer"] for r in scored) / len(scored), 3) if scored else None,
        "flagged": [r["text"] for r in scored if r.get("flagged")],
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# Aggregate one full run into a report dict
# --------------------------------------------------------------------------- #
def build_report(results, *, strict=False) -> dict:
    findings: list[dict] = []
    scenario_scores: list[dict] = []
    latencies: list[float] = []
    turns_total = 0
    missed_total = 0
    ran = [r for r in results if r["status"] == "ran"]
    skipped = [r for r in results if r["status"] == "skip"]
    skipped_all = bool(results) and not ran

    for res in ran:
        for txt in res["mechanical"]:
            findings.append(vs.as_finding(txt, scenario=res["name"]))
        if _qc is not None:
            for txt in _qc.run_all(res["transcript"]):
                findings.append(vs.as_finding(txt, scenario=res["name"]))
        scn = _SCN_BY_NAME.get(res["name"])
        if scn is not None:
            sc = vs.score_scenario(scn, res["transcript"])
            scenario_scores.append(sc)
            findings.extend(sc["goal_findings"])
        latencies.extend(res["latencies"])
        turns_total += res.get("turns_attempted", 0)
        missed_total += res.get("missed", 0)

    agg = vs.aggregate(scenario_scores)
    gateinfo = vs.gate(findings, strict=strict, skipped=skipped_all)
    latency = _vm.latency_summary(latencies) if (_vm and latencies) else None
    # VAQI (Deepgram-style): Interruptions / Missed responses / Latency. Our
    # text-mode WS harness has no overlapping audio, so interruption legs stay
    # None here — only real telephony calls can populate those (see
    # observability.Tracer.record_interruption for the live-call counterpart).
    vaqi = (
        _vm.vaqi_summary(latencies_ms=latencies, turns_total=turns_total, missed_count=missed_total)
        if (_vm and turns_total)
        else None
    )
    return {
        "ran": [r["name"] for r in ran],
        "skipped": [{"name": r["name"], "reason": r["skip_reason"]} for r in skipped],
        "findings": findings,
        "scenario_scores": scenario_scores,
        "aggregate": agg,
        "latency": latency,
        "vaqi": vaqi,
        "gate": gateinfo,
    }


# --------------------------------------------------------------------------- #
# Voice-engine tester: persist test calls into the analysis store + before/after
# --------------------------------------------------------------------------- #
def persist_test_calls(results, *, verbose=True) -> dict:
    """Write driven test-call transcripts + audio into the SAME stores the
    call-analysis pipeline reads (call_transcripts_dir / call_recordings_dir).

    Transcripts: data/call_transcripts/YYYY-MM-DD.jsonl, vobiz_stream schema —
    so scripts/voice_call_analysis.py, live_eval and campaign_optimizer pick the
    synthetic calls up exactly like real Vobiz calls. Audio: decoded b64 mp3s
    into data/call_recordings/YYYY-MM-DD/webcall_test_{name}_{i}.mp3.
    Never raises — persistence is best-effort, does not gate.
    """
    import base64
    import uuid
    from datetime import datetime, timezone

    try:
        from app.platform.runtime_recording_paths import call_recordings_dir, call_transcripts_dir
    except Exception as e:  # pragma: no cover
        return {"written": 0, "error": f"import: {e}"}

    written = 0
    now = datetime.now(timezone.utc).replace(microsecond=0)
    day = now.strftime("%Y-%m-%d")
    try:
        transcripts_dir = call_transcripts_dir()
        recordings_dir = call_recordings_dir()
        transcripts_dir.mkdir(parents=True, exist_ok=True)
        recordings_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:  # pragma: no cover
        return {"written": 0, "error": f"mkdir: {e}"}

    for res in results:
        if res["status"] != "ran":
            continue
        transcript = res.get("transcript") or []
        if not transcript:
            continue
        sid = f"webcall_selftest_{res['name'].lower().replace(' ', '_')}_{now.strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
        # Only happy-path audio (the greeting + turn replies) carries b64
        pairs = [p for p in (res.get("audio_pairs") or []) if p and p[1]]
        user_turns = sum(1 for m in transcript if m.get("role") == "user")
        rec = {
            "ts": now.isoformat(),
            "started_at": now.isoformat(),
            "duration_s": 0,
            "stream_sid": sid,
            "session_id": sid,
            "niche": res.get("niche") or "general",
            "client_id": None,
            "client_name": "VoiceEngineTester",
            "voice": "hi-IN-SwaraNeural",
            "user_turns": user_turns,
            "stt_counts": {"selftest": user_turns},
            "messages": [{"role": m.get("role"), "content": m.get("content")} for m in transcript],
            "source": "voice_engine_test",
            "flow": res.get("flow") or "qualify",
            "lead_key": None,
        }
        try:
            with open(transcripts_dir / f"{day}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
        except Exception as e:  # pragma: no cover
            if verbose:
                print(f"  ⚠ transcript persist failed for {res['name']}: {e}")
            continue
        if pairs:
            day_dir = recordings_dir / day
            try:
                day_dir.mkdir(parents=True, exist_ok=True)
            except Exception:  # pragma: no cover
                day_dir = recordings_dir
            for i, (text, b64) in enumerate(pairs):
                try:
                    raw = base64.b64decode(b64)
                    out = day_dir / f"webcall_test_{res['name'].lower().replace(' ', '_')}_{i}.mp3"
                    out.write_bytes(raw)
                except Exception as e:  # pragma: no cover
                    if verbose:
                        print(f"  ⚠ audio persist failed ({res['name']}#{i}): {e}")
                    break
    if verbose and written:
        print(f"  💾 persisted {written} test-call transcripts to {transcripts_dir}/{day}.jsonl")
    return {"written": written, "day": day}


def diff_reports(before: dict, after: dict) -> dict:
    """Before/after regression diff for the voice-engine tester — latency
    percentiles, quality, and critical/warn finding counts. Missing keys on
    either side degrade to None (no fabricated zeros)."""

    def _lat(report):
        return (report or {}).get("latency") or {}

    def _agg(report):
        return (report or {}).get("aggregate") or {}

    b_l, a_l = _lat(before), _lat(after)
    b_a, a_a = _agg(before), _agg(after)

    def _d(metric, b, a):
        if b is None or a is None:
            return None
        return {"before": b, "after": a, "delta": round(float(a) - float(b), 3)}

    return {
        "latency": {
            k: _d(k, b_l.get(k), a_l.get(k))
            for k in ("p50", "p95", "p99", "max")
            if k in b_l or k in a_l
        },
        "quality": _d("quality_score", b_a.get("quality_score"), a_a.get("quality_score")),
        "goals": _d(
            "goals_passed",
            b_a.get("goals_passed"),
            a_a.get("goals_passed"),
        ),
        "findings": {
            "critical": _d(
                "count",
                len((before or {}).get("gate", {}).get("critical") or []),
                len((after or {}).get("gate", {}).get("critical") or []),
            ),
            "warn": _d(
                "count",
                len((before or {}).get("gate", {}).get("warn") or []),
                len((after or {}).get("gate", {}).get("warn") or []),
            ),
        },
    }


def print_diff(diff: dict) -> None:
    print("\n" + "-" * 60)
    print(" BEFORE vs AFTER (voice-engine regression diff)")
    print("-" * 60)
    n = 0
    for group in ("latency", "findings", "quality", "goals"):
        items = diff.get(group) or {}
        if not isinstance(items, dict):
            continue
        for label, v in items.items():
            if not isinstance(v, dict) or v.get("delta") is None:
                continue
            b, a, d = v["before"], v["after"], v["delta"]
            arrow = "▼" if d < 0 else ("▲" if d > 0 else "=")
            print(f"  {group}.{label:<12} {b} -> {a}  {arrow}{abs(d)}")
            n += 1
    if not n:
        print("  (no comparable metrics — baseline may be a skip/stale run)")
    print("-" * 60)


def _maybe_eval_gate(quality_score) -> dict | None:
    """Record quality into the rolling baseline + return the verdict when
    EVAL_GATE=1; INERT (None) otherwise."""
    if quality_score is None:
        return None
    try:
        from app.agents import eval_gate

        if not eval_gate.enabled():
            return None
        return eval_gate.score_and_gate(
            suite="voice_selftest", metric="quality", current_score=float(quality_score), agent="ci"
        )
    except Exception:  # pragma: no cover - best-effort
        return None


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def print_human(report, roundtrip, gate_verdict, strict):
    print("\n" + "=" * 60)
    print(" VOICE AGENT SELF-TEST")
    print("=" * 60)
    if report["skipped"]:
        for s in report["skipped"]:
            print(f"  ⏭  SKIP {s['name']} ({s['reason']})")
    agg = report["aggregate"]
    if agg["quality_score"] is not None:
        print(
            f"  ⭐ quality_score={agg['quality_score']}  "
            f"goals {agg['goals_passed']}/{agg['goals_total']}  "
            f"(scenarios scored: {agg['scenarios_scored']})"
        )
        for kind, b in (agg.get("by_kind") or {}).items():
            print(f"       - {kind:<12} goals {b['passed']}/{b['total']}")
    lat = report["latency"]
    if lat:
        print(
            f"  ⏱  latency ms  n={lat['n']}  p50={lat['p50']}  p95={lat['p95']}  "
            f"p99={lat['p99']}  max={lat['max']}"
        )
    vaqi = report.get("vaqi")
    if vaqi:
        mr = vaqi.get("missed_response_rate")
        print(
            f"  📶 VAQI  missed_response_rate={mr if mr is not None else 'n/a'} "
            f"({vaqi['missed_count']}/{vaqi['turns_total']} turns)  "
            f"interruption_rate={vaqi.get('interruption_rate') or 'n/a (text-mode, no audio)'}"
        )
    if roundtrip and roundtrip.get("available"):
        print(
            f"  🎙  roundtrip (DIAGNOSTIC, Swara intelligibility)  n={roundtrip['n']}  "
            f"mean_cer={roundtrip['mean_cer']}  mean_wer={roundtrip['mean_wer']}"
        )
        if roundtrip.get("flagged"):
            for t in roundtrip["flagged"][:5]:
                print(f"       ⚠ unclear line: {t[:70]!r}")
    if gate_verdict:
        print(
            f"  🚦 eval_gate: {gate_verdict.get('decision')} "
            f"(current={gate_verdict.get('current')} baseline={gate_verdict.get('baseline')})"
        )

    g = report["gate"]
    print("-" * 60)

    def _dump(label, items):
        if items:
            print(f"  {label} ({len(items)}):")
            for f in items:
                print(f"    - [{f['scenario']}] {f['text']}")

    _dump("❌ CRITICAL", g["critical"])
    _dump("⚠ WARN", g["warn"])
    _dump("· advisory", g["advisory"])
    print("-" * 60)
    if g["status"] == "skip":
        print("  ⏭  SKIPPED — no server reachable (exit 0, not a failure).")
    elif g["exit_code"] == 0:
        n_adv = len(g["advisory"]) + len(g["warn"])
        extra = f" ({n_adv} advisory/warn — informational)" if n_adv else ""
        print(f"  ✅ PASS{extra}")
    else:
        mode = "strict" if strict else "default"
        print(
            f"  ❌ FAIL ({mode} gate) — {len(g['critical'])} critical"
            + (f", +{len(g['warn']) + len(g['advisory'])} promoted" if strict else "")
        )
    print("=" * 60)


async def main() -> int:
    ap = argparse.ArgumentParser(description="Advanced voice-agent self-test (FREE).")
    ap.add_argument("--url", default=DEFAULT_WS, help="web-call WS URL")
    ap.add_argument("--strict", action="store_true", help="behavioural/guardrail/warn also gate")
    ap.add_argument("--audio", action="store_true", help="add roundtrip-WER (uses Groq STT quota)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    ap.add_argument("--only", default="", help="comma-separated scenario names to run")
    ap.add_argument(
        "--record",
        action="store_true",
        help="persist driven test-call transcripts+audio into the analysis store "
        "(data/call_transcripts + data/call_recordings) so voice_call_analysis "
        "picks them up like real calls",
    )
    ap.add_argument(
        "--baseline",
        default="",
        metavar="FILE",
        help="JSON report from a prior --json run; print a before/after latency+quality diff",
    )
    args = ap.parse_args()
    verbose = not args.json

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    scenarios = [s for s in vs.SCENARIOS if (not only or s.name in only)]

    results = []
    async with aiohttp.ClientSession() as session:
        for scn in scenarios:
            if verbose:
                print(f"\n=== {scn.kind.upper()}: {scn.name} ===")
            try:
                r = await run_scenario(
                    session, scn, args.url, collect_audio=args.audio, verbose=verbose
                )
            except Exception as e:  # never let one scenario abort the suite
                r = {
                    "name": scn.name,
                    "kind": scn.kind,
                    "status": "ran",
                    "skip_reason": None,
                    "transcript": [],
                    "mechanical": [f"CRASH: {type(e).__name__}: {str(e)[:120]}"],
                    "latencies": [],
                    "audio_pairs": [],
                }
            results.append(r)

    report = build_report(results, strict=args.strict)

    persisted = None
    if args.record:
        persisted = persist_test_calls(results, verbose=verbose)

    baseline = None
    if args.baseline:
        try:
            with open(args.baseline, encoding="utf-8") as f:
                baseline = json.load(f)
        except Exception as e:
            if verbose:
                print(f"  ⚠ could not load baseline {args.baseline!r}: {e}")

    roundtrip = None
    if args.audio:
        pairs = [p for r in results if r["status"] == "ran" for p in r["audio_pairs"]]
        if pairs:
            roundtrip = await roundtrip_block(pairs)

    gate_verdict = _maybe_eval_gate(report["aggregate"]["quality_score"])

    diff = diff_reports(baseline, report) if baseline else None

    if args.json:
        out = dict(report)
        out["roundtrip"] = roundtrip
        out["eval_gate"] = gate_verdict
        out["strict"] = args.strict
        out["persisted"] = persisted
        out["baseline_diff"] = diff
        # JSON ONLY -> the saved real stdout (import/runtime logging went to buffer)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str), file=_REAL_STDOUT)
    else:
        print_human(report, roundtrip, gate_verdict, args.strict)
        if diff:
            print_diff(diff)

    return int(report["gate"]["exit_code"])


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
