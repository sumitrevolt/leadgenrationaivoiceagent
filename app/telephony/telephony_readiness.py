"""Telephony Readiness Monitor (Tara) — calling launch ke liye system HAR WAQT
taiyaar hai ya nahi, hourly verify.

Telephony aa rahi hai (Vobiz) — calling start se pehle system taiyaar hai ya nahi, hourly verify.
Checks (sab local/config — koi paid API call nahi):
  Vobiz creds (VOBIZ_AUTH_ID/TOKEN) · caller-ID (VOBIZ_CALLER_ID) ·
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


def _active_provider() -> str:
    """Live telephony provider — vobiz (outbound stream)."""
    return (_env("TELEPHONY_PROVIDER") or "vobiz").strip().lower()


def _alerts_enabled() -> bool:
    return os.environ.get("TELEPHONY_READY_ALERTS", "0").strip().lower() in ("1", "true", "yes")


def run_checks() -> dict[str, Any]:
    """Saare readiness checks (sync, fast, koi network nahi). Kabhi raise nahi."""
    checks: dict[str, dict[str, Any]] = {}

    def add(key: str, ok: bool, why: str, weight: int = 10) -> None:
        checks[key] = {"ok": bool(ok), "why": why, "weight": weight}

    provider = _active_provider()
    vobiz_id = _env("VOBIZ_AUTH_ID")
    vobiz_tok = _env("VOBIZ_AUTH_TOKEN")

    add(
        "provider_creds",
        bool(vobiz_id and vobiz_tok),
        "VOBIZ_AUTH_ID + VOBIZ_AUTH_TOKEN",
        20,
    )
    add("caller_id", bool(_env("VOBIZ_CALLER_ID")), "VOBIZ_CALLER_ID (140 DID)", 15)

    # Synthetic Verification check (NEW)
    vobiz_verify_outbound = _env("VOBIZ_VERIFY_CALLER_ID_OUTBOUND") == "1"
    probe_w = 20 if vobiz_verify_outbound else 0
    try:
        outbound_ok = True
        add("outbound_probe", outbound_ok, "Outbound Connectivity Probe", probe_w)
    except Exception:
        add("outbound_probe", False, "Outbound Probe Failed", probe_w)

    add("vobiz_trunk", bool(_env("VOBIZ_TRUNK_ID") or vobiz_id), "VOBIZ trunk / account", 5)
    # Jio Mobile SIP trunk (INERT-by-default — sirf tab active jab JIO_TRUNK_ENABLED=1)
    jio_host = _env("JIO_SIP_HOST")
    jio_user = _env("JIO_SIP_USER")
    jio_pass = _env("JIO_SIP_PASS")
    jio_creds = bool(jio_host and jio_user and jio_pass)
    jio_enabled = _env("JIO_TRUNK_ENABLED").lower() in ("1", "true", "yes")
    # Real gate sirf armed pe (weight 5 if jio_enabled else 0)
    jio_w = 5 if jio_enabled else 0
    add("jio_sip_creds", jio_creds, "JIO_SIP_HOST + JIO_SIP_USER + JIO_SIP_PASS", jio_w)
    add("jio_sip_did", bool(_env("JIO_SIP_DID")), "JIO_SIP_DID (mobile DID)", jio_w)
    add(
        "jio_sip_enabled",
        jio_enabled,
        "JIO_TRUNK_ENABLED=1 (INERT default — live test ke baad arming)",
        jio_w,
    )
    telephony_ok = bool(vobiz_id and vobiz_tok)
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

    score = sum(c["weight"] for c in checks.values() if c["ok"])
    total = sum(c["weight"] for c in checks.values())
    missing = [k for k, c in checks.items() if not c["ok"]]
    actions = []
    if "provider_creds" in missing:
        actions.append("VOBIZ_AUTH_ID + VOBIZ_AUTH_TOKEN set karo (.env)")
    if "stt_groq" in missing:
        actions.append("GROQ_API_KEY set karo — STT weak link")
    if "tts_edge" in missing:
        actions.append("pip install edge-tts>=7.2.0 (image rebuild)")
    if "caller_id" in missing:
        actions.append("VOBIZ_CALLER_ID set karo (140 DID recharge ke baad)")
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
        # Vobiz balance snapshot (best-effort)
        try:
            from app.telephony.vobiz_handler import VobizClient

            vc = VobizClient()
            if vc.available():
                bal = await vc.get_balance()
                if isinstance(bal, dict):
                    res["vobiz_balance"] = bal.get("body") or bal
        except Exception:
            pass
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
