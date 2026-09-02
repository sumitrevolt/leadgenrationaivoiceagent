"""
LLM injection / IFC guard — observe-only, flag-gated, import-safe.

Indirect Prompt Injection (IPI) detection for UNTRUSTED content the agent reads:
inbound email, scraped web, retrieved KB, tool output. It does NOT block — it
SCORES + flags so a human or deterministic gate can ratify before any side-effect
(Information Flow Control). The scan functions are PURE (always run); the WIRING
side-effects (log lines / draft tags) are gated by env `LLM_GUARD=1`.

Grounded in ai-engineering-from-scratch ph18/15-16 (IPI · IFC · red-team).
Skill: `.claude/skills/llm-security/SKILL.md`. Never raises (project rule).

IFC principle: content from an UNTRUSTED source must never drive control flow
(send / call / post / pay / tool-invoke) without trusted ratification. This module
gives you the label + the signal; the caller keeps the gate.
"""

from __future__ import annotations

import os
import re

# IFC trust labels
UNTRUSTED_SOURCES = {"inbox", "email", "web", "scrape", "rag", "kb", "tool", "third_party"}
TRUSTED_SOURCES = {"user", "customer", "operator", "admin", "system"}

# IPI signal patterns — imperative-to-agent instructions embedded in content.
# Conservative + observe-only, so benign false-positives are acceptable (we flag,
# never block). Each = (name, compiled regex).
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_prior",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all)\b"
            r".{0,24}\b(instruction|prompt|message|rule|context)",
            re.I,
        ),
    ),
    (
        "override_system",
        re.compile(
            r"\b(system prompt|developer message|your instructions?|you are now|new instructions?)\b",
            re.I,
        ),
    ),
    (
        "exfil_send",
        re.compile(
            r"\b(forward|send|email|sms|whatsapp|post|share|leak)\b.{0,40}"
            r"\b(all|every|contact|customer|password|api[ _]?key|secret|credential|token)\b",
            re.I,
        ),
    ),
    (
        "tool_invoke",
        re.compile(
            r"\b(call|invoke|execute|trigger|run)\b.{0,20}\b(the )?(tool|function|command|api|endpoint|webhook)\b",
            re.I,
        ),
    ),
    (
        "role_switch",
        re.compile(r"\b(act as|pretend to be|roleplay as|you must now|from now on you)\b", re.I),
    ),
    (
        "data_exfil",
        re.compile(
            r"\b(reveal|print|output|repeat|show|dump)\b.{0,30}"
            r"\b(system prompt|your prompt|your instructions?|api[ _]?key|secret|password)\b",
            re.I,
        ),
    ),
    ("encoded_blob", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")),  # long base64-ish payload
]


def label_source(source: str) -> str:
    """IFC trust label. Default = untrusted (fail-safe — unknown source is not trusted)."""
    s = (source or "").strip().lower()
    return "trusted" if s in TRUSTED_SOURCES else "untrusted"


def scan(text: str, source: str = "unknown") -> dict:
    """Scan content for IPI signals. PURE — never blocks, never raises.

    Returns: {risk:int, signals:[names], trust:label, source, suspicious:bool}
    """
    label = label_source(source)
    if not text:
        return {"risk": 0, "signals": [], "trust": label, "source": source, "suspicious": False}
    try:
        hits = [name for name, rx in _PATTERNS if rx.search(text)]
    except Exception:
        hits = []
    return {
        "risk": len(hits),
        "signals": hits,
        "trust": label,
        "source": source,
        "suspicious": bool(hits),
    }


def is_suspicious(text: str, source: str = "unknown") -> bool:
    """True if any IPI signal matched. Pure."""
    return scan(text, source)["risk"] > 0


def enabled() -> bool:
    """Wiring switch — observe-only side-effects (log lines / draft tags) only when
    LLM_GUARD=1. Scans run regardless; this just gates the noise so the feature is
    INERT by default (project ethos: gated, fail-open)."""
    return os.environ.get("LLM_GUARD", "").strip() == "1"
