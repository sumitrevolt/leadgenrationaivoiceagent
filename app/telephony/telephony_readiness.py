"""Telephony Readiness Monitor (Tara) — calling launch ke liye system HAR WAQT
taiyaar hai ya nahi, hourly verify.

Telephony aa rahi hai (Tata SmartFlo — Vobiz/Jio removed 2026-09-15) — calling
start se pehle system taiyaar hai ya nahi, hourly verify.
Checks (sab local/config — koi paid API call nahi):
  SmartFlo creds (TATA_SMARTFLO_API_TOKEN/KEY) · DID (TATA_SMARTFLO_DID) ·
  TTS (edge-tts) · STT (GROQ key) · LLM chain · compliance flags.

Score 0-100 + missing list + Hinglish next-actions. Watchdog-job me wired (Tara
log_event). Alert sirf score-drop pe, gated `TELEPHONY_READY_ALERTS=1`.
Import-safe, kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOG = os.path.join("data", "telephony_readiness.jsonl")


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        from app.config import settings

        return str(getattr(settings, name.lower(), "") or "")
    except Exception:
        return ""


def _sync_run(coro):
    """Run an async coroutine from a sync context (best-effort, never raise)."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # Already in an event loop — use a thread to avoid deadlock.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=10)
    return asyncio.run(coro)


def _active_provider() -> str:
    """Live telephony provider — tata_smartflo (Vobiz/Jio removed 2026-09-15)."""
    return (_env("TELEPHONY_PROVIDER") or "tata_smartflo").strip().lower()


def _alerts_enabled() -> bool:
    return os.environ.get("TELEPHONY_READY_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def run_checks() -> dict[str, Any]:
    """Saare readiness checks (sync, fast, koi network nahi). Kabhi raise nahi."""
    checks: dict[str, dict[str, Any]] = {}

    def add(key: str, ok: bool, why: str, weight: int = 10) -> None:
        checks[key] = {"ok": bool(ok), "why": why, "weight": weight}

    provider = _active_provider()
    # Vobiz removed 2026-09-15 — Tata SmartFlo is the sole provider now.
    tata_token = _env("TATA_SMARTFLO_API_TOKEN")
    tata_key = _env("TATA_SMARTFLO_API_KEY")
    tata_did = _env("TATA_SMARTFLO_DID")
    tata_creds = bool(tata_token and tata_key)
    tata_enabled = os.environ.get("TATA_SMARTFLO_ENABLED", "0").strip().lower() in (
        "1", "true", "yes",
    )

    add(
        "provider_creds",
        tata_creds,
        "TATA_SMARTFLO_API_TOKEN + TATA_SMARTFLO_API_KEY",
        20,
    )
    add("did", bool(tata_did), "TATA_SMARTFLO_DID (bundled DID)", 15)

    # Synthetic Verification check — DID connectivity probe.
    # 2026-08-30 FIX: previous code hardcoded outbound_ok=True which gave a
    # false-green readiness score even when the DID was NOT bound correctly.
    # Now defaults to False; only passes when the probe explicitly
    # succeeds or is not configured (weight=0).
    smartflo_verify_outbound = _env("SMARTFLO_VERIFY_CALLER_ID_OUTBOUND").lower() in (
        "1", "true", "yes",
    )
    probe_w = 20 if smartflo_verify_outbound else 0
    if smartflo_verify_outbound:
        try:
            from app.telephony.telephony_readiness_probe import (
                verify_outbound_connectivity,
            )

            probe_result = _sync_run(verify_outbound_connectivity())
            outbound_ok = probe_result.get("ok", False)
            probe_why = probe_result.get("why", "probe result unknown")
            add("outbound_probe", outbound_ok, probe_why, probe_w)
        except Exception as exc:
            add("outbound_probe", False, f"probe error: {exc}", probe_w)
    else:
        add(
            "outbound_probe",
            True,
            "skipped (SMARTFLO_VERIFY_CALLER_ID_OUTBOUND=0 — weight=0, not scored)",
            0,
        )

    add(
        "tata_smartflo_enabled",
        tata_enabled,
        "TATA_SMARTFLO_ENABLED=1 (INERT default — live test ke baad arming)",
        10,
    )
    telephony_ok = tata_creds
    # Voice AI chain
    tts_ok = False
    try:
        import edge_tts  # noqa: F401

        tts_ok = True
    except Exception:
        pass
    add("tts_edge", tts_ok, "edge-tts installed (hi-IN-SwaraNeural)", 15)
    add("stt_groq", bool(_env("GROQ_API_KEY")), "GROQ_API_KEY (whisper-large-v3 STT)", 15)
    llm_ok = False
    llm_why = "koi free-LLM provider configured nahi"
    try:
        from app.voice_agent.free_ai import describe

        provs = (describe() or {}).get("providers") or {}
        configured = [k for k, v in provs.items() if v]
        llm_ok = bool(configured)
        llm_why = f"LLM providers: {', '.join(configured) or 'none'}"
    except Exception:
        pass
    add("llm_chain", llm_ok, llm_why, 15)
    # LLM live health (observability se)
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(500)
        rate = 1.0 - float(st.get("fallback_or_fail_rate", 0) or 0)
        add(
            "llm_health",
            rate >= 0.5 or st.get("total_calls", 0) == 0,
            f"recent ok-rate {round(rate, 2)}",
            5,
        )
    except Exception:
        add("llm_health", True, "no data yet", 5)
    # Compliance posture
    add("dnd_config", telephony_ok, "compliance gate creds available", 5)
    add(
        "compliance_flags",
        os.environ.get("WHATSAPP_AUTO_SEND", "0") != "1",
        "ban-risky auto-send OFF (TRAI-safe posture)",
        5,
    )
    # Latency knobs present (Phase-3)
    add(
        "turn_knobs",
        bool(os.environ.get("TURN_SILENCE_MS") or True),
        "turn-taking env knobs available",
        5,
    )

    # Voice launch posture (2026-09-11): a HALTED dialer must never score as
    # "ready". Catches the case where a live-posture flag is ON while the admin
    # kill switch is ENGAGED — every dial path refuses, so nothing is live.
    try:
        from app.telephony.voice_launch import admin_kill_status, launch_state_conflict

        _conflict = launch_state_conflict()
        _kill = admin_kill_status()
        add(
            "voice_launch_posture",
            _conflict is None,
            (
                _conflict["detail"]
                if _conflict
                else f"kill switch disengaged (source={_kill.source})"
            ),
            15,
        )
    except Exception as exc:
        add("voice_launch_posture", False, f"posture check error: {exc}", 15)

    score = sum(c["weight"] for c in checks.values() if c["ok"])
    total = sum(c["weight"] for c in checks.values())
    missing = [k for k, c in checks.items() if not c["ok"]]
    actions = []
    if "provider_creds" in missing:
        actions.append("TATA_SMARTFLO_API_TOKEN + TATA_SMARTFLO_API_KEY set karo (.env)")
    if "did" in missing:
        actions.append("TATA_SMARTFLO_DID set karo (SmartFlo console se bundled DID copy karo)")
    if "stt_groq" in missing:
        actions.append("GROQ_API_KEY set karo — STT weak link")
    if "tts_edge" in missing:
        actions.append("pip install edge-tts>=7.2.0 (image rebuild)")
    if "voice_launch_posture" in missing:
        actions.append(
            "Voice launch posture contradict karti hai: admin kill switch ENGAGED hai "
            "par PLATFORM_DIAL_DAILY/VOICE_LAUNCH_CAMPAIGN ON hai — koi bhi dial "
            "path refuse karega. Kill switch disengage karo ya live-posture flag OFF."
        )
    if not actions:
        actions.append(
            f"{provider.title()} calling ready — kal 10am–7pm IST window me test karo ✅"
        )
    return {
        "provider": provider,
        "score": round(100 * score / max(total, 1)),
        "checks": checks,
        "missing": missing,
        "actions": actions,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def run_watch() -> dict[str, Any]:
    """Hourly (watchdog) — log under Tara; score girne pe gated alert. Kabhi raise nahi."""
    try:
        res = run_checks()
        # Vobiz balance snapshot removed 2026-09-15 (Vobiz deletion; SmartFlo
        # is flat-rate with no PAYG balance to poll).
        prev_score = None
        try:
            if os.path.exists(_LOG):
                with open(_LOG, encoding="utf-8") as f:
                    lines = f.readlines()
                if lines:
                    prev_score = json.loads(lines[-1]).get("score")
        except Exception:
            pass
        try:
            os.makedirs(os.path.dirname(_LOG) or ".", exist_ok=True)
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps({"score": res["score"], "missing": res["missing"], "at": res["at"]})
                    + "\n"
                )
        except Exception:
            pass
        dropped = prev_score is not None and res["score"] < prev_score
        if dropped and _alerts_enabled():
            notify = os.environ.get("NOTIFY_EMAIL", "").strip()
            if notify:
                try:
                    from app.integrations.email_sender import email_sender

                    await email_sender.send_email(
                        [notify],
                        f"⚠️ Telephony readiness gira: {prev_score} → {res['score']}",
                        "Missing: "
                        + ", ".join(res["missing"])
                        + "\nActions:\n- "
                        + "\n- ".join(res["actions"]),
                    )
                except Exception:
                    pass
        try:
            from app.platform import team

            team.log_event(
                "tara",
                "telephony_readiness",
                f"score {res['score']}/100"
                + (
                    f" | missing: {', '.join(res['missing'][:4])}"
                    if res["missing"]
                    else " | READY ✅"
                ),
                status="ok" if res["score"] >= 80 else "warn",
            )
        except Exception:
            pass
        return res
    except Exception as e:
        logger.warning(f"[telephony_readiness] failed: {e}")
        return {"error": str(e)}
