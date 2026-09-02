"""Setup & Readiness audit — the stack's "automated setup" status in one place.

This session added a big automation suite, but everything is opt-in and there was no way
to SEE what's actually live. This auto-scans the whole stack:
  - feature flags (on/off),
  - optional dependencies (installed?),
  - keys/config (set? — presence only, never prints the value),
  - pending user-actions,
and produces a readiness report. Read-only + never-crash. Used by
`scripts/setup_status.py` (CLI) and can back an admin endpoint / dashboard.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

# env flag -> (what it enables, default-on?)
FLAGS: dict[str, tuple[str, bool]] = {
    "TEAM_AUTOMATION": ("Scheduler + AI staff (dailies/growth)", True),
    "AUTO_EMAIL_OUTREACH": ("Auto cold-email outreach (Rohan 10:30)", False),
    "REPLY_AGENT": ("AI reply triage (inbox replies)", False),
    "OPS_WATCHDOG": ("Ops monitoring + email alerts", False),
    "AUTO_ONBOARD": ("Auto client onboarding (website->KB)", False),
    "USE_STRUCTURED_CONTENT": ("Reliable typed marketing content (Instructor)", False),
    "USE_AGENTIC_RAG": ("Corrective CRAG retrieval", False),
    "USE_LIGHTRAG": ("Knowledge-graph RAG (LightRAG)", False),
    "USE_SILERO_VAD": ("Better voice VAD (Silero)", False),
    "USE_SMART_TURN": ("Semantic turn-taking (Smart Turn v3)", False),
    "USE_LANGGRAPH_SUPERVISOR": ("Multi-agent supervisor", False),
    "OUTREACH_VERIFY_MX": ("Email MX verify before send", True),
    "OUTREACH_SELECT_SKIP_MX": ("Defer MX to send-batch (TimeLimitExceeded fix)", True),
}

# import name -> feature it powers
DEPS: dict[str, str] = {
    "instructor": "typed LLM JSON",
    "advertools": "SEO/SEM + ads",
    "trafilatura": "web text extract",
    "markitdown": "any-file -> markdown",
    "lightrag": "knowledge-graph RAG",
    "langgraph_supervisor": "multi-agent supervisor",
    "langchain_openai": "LLM gateway",
    "email_validator": "email verify (MX)",
    "phonenumbers": "phone validate",
    "crawl4ai": "deep web crawl (heavy)",
    "silero_vad": "voice VAD",
    "faster_whisper": "STT",
    "edge_tts": "TTS",
    "qdrant_client": "vector RAG",
    "fastembed": "embeddings",
}

# env/settings key -> purpose (presence only)
KEYS: dict[str, str] = {
    "CEREBRAS_API_KEY": "LLM brain (free)",
    "GROQ_API_KEY": "STT hearing (free) — voice samajhne ke liye",
    "GOOGLE_MAPS_API_KEY": "prospecting (real phones)",
    "SMTP_PASSWORD": "email send + reply IMAP",
    "NOTIFY_EMAIL": "ops alerts + inquiry alerts",
    "UPI_VPA": "payment modal",
    "VOBIZ_AUTH_ID": "telephony (voice calls)",
    "HOSTINGER_API_TOKEN": "DNS API",
}

# pending user-actions (external — Claude can't do)
USER_ACTIONS = [
    "GROQ_API_KEY (console.groq.com, free) — STT hearing fix",
    "Udyam (MSME, free) cert -> DLT re-apply (cold-calling legal)",
    "Vobiz recharge + DID -> VOBIZ_CALLER_ID (voice calls)",
    "Dedicated cold-email domain + warmup (deliverability; primary mat jalao)",
]


def _flag(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v == "":
        return default
    return v in {"1", "true", "yes", "on"}


def _has_dep(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _has_key(name: str) -> bool:
    v = os.getenv(name, "")
    if not v:
        try:
            from app.config import settings

            v = getattr(settings, name.lower(), "") or ""
        except Exception:
            v = ""
    return bool(str(v).strip())


def pending_actions() -> list[str]:
    """Only the user-actions that are ACTUALLY still pending (key-based, dynamic)."""
    out: list[str] = []
    if not _has_key("GROQ_API_KEY"):
        out.append("GROQ_API_KEY (console.groq.com, free) — STT hearing fix")
    dlt_ok = os.getenv("DLT_APPROVED", "").strip().lower() in ("1", "true", "yes")
    if not dlt_ok:
        out.append("Udyam (MSME, free) cert -> DLT re-apply (cold-calling legal)")
    if not _has_key("VOBIZ_CALLER_ID"):
        out.append("Vobiz recharge + DID -> VOBIZ_CALLER_ID (voice cold-calls)")
    if not _has_key("UPI_VPA"):
        out.append("UPI_VPA (apna UPI ID) — payment modal")
    out.append("Dedicated cold-email domain + warmup (deliverability)")
    return out


def audit() -> dict[str, Any]:
    flags = {
        k: {"on": _flag(k, dflt), "desc": desc, "default_on": dflt}
        for k, (desc, dflt) in FLAGS.items()
    }
    deps = {k: {"installed": _has_dep(k), "feature": v} for k, v in DEPS.items()}
    keys = {k: {"set": _has_key(k), "purpose": v} for k, v in KEYS.items()}
    flags_on = sum(1 for f in flags.values() if f["on"])
    deps_in = sum(1 for d in deps.values() if d["installed"])
    keys_set = sum(1 for k in keys.values() if k["set"])
    return {
        "flags": flags,
        "deps": deps,
        "keys": keys,
        "user_actions": pending_actions(),
        "summary": {
            "flags_on": f"{flags_on}/{len(flags)}",
            "deps_installed": f"{deps_in}/{len(deps)}",
            "keys_set": f"{keys_set}/{len(keys)}",
        },
    }


def format_report(a: dict | None = None) -> str:
    a = a or audit()
    L = ["=== LeadGen AI — Setup & Readiness ===", ""]
    s = a["summary"]
    L.append(f"Flags ON: {s['flags_on']} | Deps: {s['deps_installed']} | Keys: {s['keys_set']}")
    L.append("")
    L.append("-- FEATURE FLAGS --")
    for k, v in a["flags"].items():
        mark = "ON " if v["on"] else "off"
        dft = " (default-on)" if v["default_on"] else ""
        L.append(f"  [{mark}] {k}{dft} — {v['desc']}")
    L.append("")
    L.append("-- OPTIONAL DEPS --")
    for k, v in a["deps"].items():
        L.append(f"  [{'OK ' if v['installed'] else 'no '}] {k} — {v['feature']}")
    L.append("")
    L.append("-- KEYS / CONFIG (presence only) --")
    for k, v in a["keys"].items():
        L.append(f"  [{'SET' if v['set'] else '---'}] {k} — {v['purpose']}")
    L.append("")
    L.append("-- PENDING USER ACTIONS (external) --")
    for x in a["user_actions"]:
        L.append(f"  - {x}")
    return "\n".join(L)


__all__ = ["audit", "format_report", "FLAGS", "DEPS", "KEYS", "USER_ACTIONS"]
