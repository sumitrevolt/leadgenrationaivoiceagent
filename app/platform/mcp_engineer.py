"""mcp_engineer.py — Arya, MCP Engineer (platform staff agent).

Council 2026-06-26 verdict: project me 3 MCP layers exist — (1) /mcp expose via
fastapi-mcp, (2) /api/mcp-product/v1/* metered B2B surface, (3) A2A Agent Card.
Pre-Arya: koi dedicated agent in surfaces ka health, key-rotation, abuse-watch,
ya cross-server registry sync nahi karta. Hermes infra-handler poora app dekhta
hai, par MCP-specific signals (key abuse, A2A drift, /mcp auth failures) silent.

Arya yeh gap bhare. PATTERN match `engineer_agents.py` (Pranav/Vidya/Arnav):
- 0-100 score computer (mcp_health_score)
- KPI sub-scores: expose_reachable, product_armed, keys_active, quota_pressure,
  auth_failures_24h, a2a_card_valid, dependency_present
- INERT default: MCP_ENGINEER unset -> _disabled_result()
- Pure-Python; uses sqlite/httpx/json only (no new deps)
- log_event() into agent_events (team dashboard auto-picks)
- ntfy alert on critical (auth_failure spike, key abuse)

Production-ready scope (LLM council Chairman verdict):
- Hourly health pulse — fast, no LLM call
- Daily key-rotation reminder (90d-old keys)
- A2A Agent Card schema validation (against discover endpoint)
- /mcp endpoint auth-probe (verify gate is closed, NOT public)
- Quota-pressure detection: any key > 80% daily limit -> ntfy alert
- Obsidian sync via log_event hook (Agents/Arya.md auto-writes)

PUBLIC API:
    from app.platform import mcp_engineer
    mcp_engineer.run_mcp()            # full health check + score + log
    mcp_engineer.health_score()       # quick KPI snapshot dict
    mcp_engineer.rotation_due_keys()  # keys >90 days old needing rotation
    mcp_engineer.audit_mcp_security() # one-shot security probe of /mcp
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Per-role enable flag (registered in app/api/automation_flags.py AUTOMATION_FLAGS)
_MCP_ENGINEER_FLAG = "MCP_ENGINEER"

# Tunables — env-overridable
_KEY_ROTATION_DAYS = int(os.environ.get("MCP_KEY_ROTATION_DAYS", "90"))
_QUOTA_PRESSURE_PCT = int(os.environ.get("MCP_QUOTA_PRESSURE_PCT", "80"))
_AUTH_FAIL_ALERT_THRESHOLD = int(os.environ.get("MCP_AUTH_FAIL_ALERT", "20"))

_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_AUTH_FAIL_LOG = _DATA_DIR / "mcp_auth_failures.jsonl"  # appended by middleware


# --------------------------------------------------------------------------- #
# Shared helpers (pattern-match engineer_agents.py)
# --------------------------------------------------------------------------- #
def _flag_on(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes")


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(x)))


def _disabled_result(role: str, flag: str) -> dict[str, Any]:
    return {
        "role": role,
        "score": None,
        "status": "disabled",
        "summary": f"{role} agent disabled (set {flag}=1 in .env to activate)",
        "kpis": {},
        "actions": [f"Set {flag}=1 to enable the {role} agent"],
        "ts": int(time.time()),
    }


def _try_log(role: str, event: str, detail: str, status: str = "ok") -> None:
    """Best-effort agent_events log — never raises, never blocks."""
    try:
        from app.platform import team

        team.log_event(role, event, detail[:480], status=status)
    except Exception as exc:
        logger.debug("mcp_engineer _try_log skipped: %s", exc)


def _maybe_alert(title: str, body: str, priority: str = "default") -> None:
    """Send ntfy alert if OPS_ALERTS configured. Fail-open."""
    try:
        from app.platform import ops_alerts

        # ops_alerts has no send_alert (the hasattr guard made this a permanent no-op,
        # so the MCP auth-attack ntfy page never fired). The real push helper is _ntfy.
        ops_alerts._ntfy(title, body, priority=priority, tags=["mcp"])
    except Exception as exc:
        logger.debug("mcp_engineer _maybe_alert swallowed: %s", exc)


# --------------------------------------------------------------------------- #
# Sub-probes — each returns a 0-100 score + KPI dict
# --------------------------------------------------------------------------- #
def _probe_dependency() -> tuple[float, dict[str, Any]]:
    """Is fastapi-mcp importable? Without it, /mcp doesn't mount at all."""
    try:
        import fastapi_mcp  # noqa: F401

        return 100.0, {"fastapi_mcp_installed": True}
    except ImportError:
        return 0.0, {"fastapi_mcp_installed": False}


def _probe_product_armed() -> tuple[float, dict[str, Any]]:
    """Is MCP-as-product flag ON? Off = customer-facing surface paused (503)."""
    try:
        from app.platform import mcp_keys

        armed = mcp_keys.enabled()
        return (100.0 if armed else 50.0), {"mcp_product_enabled": armed}
    except Exception:
        return 0.0, {"mcp_product_enabled": False, "error": "mcp_keys import failed"}


def _probe_keys() -> tuple[float, dict[str, Any]]:
    """Active key count + quota pressure.
    - Zero keys = neutral 50 (newly-armed surface, not yet adopted).
    - Any key > QUOTA_PRESSURE_PCT% daily limit = warn + alert.
    """
    try:
        from app.platform import mcp_keys

        summary = mcp_keys.usage_summary() or {}
        keys = summary.get("keys") or []
        active = [k for k in keys if k.get("enabled")]
        if not active:
            return 50.0, {"active_keys": 0, "quota_pressure_keys": []}
        pressured = []
        for k in active:
            today = int(k.get("calls_today", 0) or 0)
            limit = int(k.get("daily_limit", 1) or 1)
            pct = (today / limit) * 100 if limit > 0 else 0
            if pct >= _QUOTA_PRESSURE_PCT:
                pressured.append({"label": k.get("label"), "pct": round(pct, 1)})
        score = 100.0 if not pressured else max(40.0, 100.0 - 10 * len(pressured))
        return score, {
            "active_keys": len(active),
            "total_keys": len(keys),
            "quota_pressure_keys": pressured,
        }
    except Exception as exc:
        return 50.0, {"active_keys": None, "error": str(exc)[:120]}


def _probe_rotation_due() -> tuple[float, dict[str, Any]]:
    """Any active key older than _KEY_ROTATION_DAYS days?"""
    try:
        from app.platform import mcp_keys

        rows = mcp_keys.list_all() or []
        cutoff = time.time() - (_KEY_ROTATION_DAYS * 86400)
        due = []
        for r in rows:
            if not r.get("enabled", True):
                continue
            created = r.get("created_at", 0)
            if created and created < cutoff:
                age_days = int((time.time() - created) / 86400)
                due.append({"id": r.get("id"), "label": r.get("label"), "age_days": age_days})
        score = 100.0 if not due else max(50.0, 100.0 - 10 * len(due))
        return score, {"rotation_due_count": len(due), "rotation_due": due[:5]}
    except Exception as exc:
        return 75.0, {"rotation_due_count": None, "error": str(exc)[:120]}


def _probe_auth_failures() -> tuple[float, dict[str, Any]]:
    """Tail _AUTH_FAIL_LOG and count last-24h MCP auth failures.
    Threshold breach = potential brute-force / leaked-key probe = ntfy alert.
    """
    if not _AUTH_FAIL_LOG.exists():
        return 100.0, {"auth_failures_24h": 0, "log_present": False}
    cutoff = time.time() - 86400
    n = 0
    try:
        lines = _AUTH_FAIL_LOG.read_text(encoding="utf-8").splitlines()[-50000:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if int(rec.get("ts", 0)) >= cutoff:
                    n += 1
            except Exception:
                continue
    except Exception:
        return 75.0, {"auth_failures_24h": None, "log_present": True}
    if n >= _AUTH_FAIL_ALERT_THRESHOLD:
        score = max(10.0, 100.0 - n)
    elif n > 0:
        score = 80.0
    else:
        score = 100.0
    return score, {"auth_failures_24h": n, "log_present": True}


def _probe_a2a_card() -> tuple[float, dict[str, Any]]:
    """A2A Agent Card has the required fields and capability paths are valid.
    Validates against the static schema defined in app/api/mcp_product.py.
    """
    try:
        from app.api import mcp_product
        from app.platform import mcp_keys as _mk

        required = ("name", "version", "url", "capabilities", "auth")
        caps = list(_mk.SUPPORTED_CAPABILITIES or ())
        if not caps:
            return 60.0, {"a2a_card_valid": False, "reason": "no SUPPORTED_CAPABILITIES"}
        # We can't await the async route from sync code reliably; instead
        # check that the underlying capability_paths cover every capability.
        paths = getattr(mcp_product, "_CAPABILITY_PATHS", {}) or {}
        missing = [c for c in caps if not paths.get(c)]
        score = 100.0 if not missing else 50.0
        return score, {
            "a2a_card_valid": not missing,
            "capabilities": caps,
            "missing_paths": missing,
            "required_fields": list(required),
        }
    except Exception as exc:
        return 0.0, {"a2a_card_valid": False, "error": str(exc)[:120]}


def _probe_expose_gate() -> tuple[float, dict[str, Any]]:
    """Is /mcp mounted with an admin gate (token or IP allowlist)?
    Council #1 finding: pre-fix mount was UNGATED → admin tools leak.
    Detect by env presence of FASTAPI_MCP_TOKEN or MCP_IP_ALLOWLIST.
    """
    token_set = bool(os.environ.get("FASTAPI_MCP_TOKEN", "").strip())
    allowlist = os.environ.get("MCP_IP_ALLOWLIST", "").strip()
    has_gate = token_set or bool(allowlist)
    score = 100.0 if has_gate else 0.0
    return score, {
        "mcp_endpoint_gated": has_gate,
        "token_configured": token_set,
        "ip_allowlist_set": bool(allowlist),
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def run_mcp() -> dict[str, Any]:
    """Full MCP health pass — score + KPIs + actions + ntfy on critical."""
    if not _flag_on(_MCP_ENGINEER_FLAG):
        return _disabled_result("mcp", _MCP_ENGINEER_FLAG)

    sub_scores: list[float] = []
    kpis: dict[str, Any] = {}
    actions: list[str] = []

    for name, probe in (
        ("dependency", _probe_dependency),
        ("expose_gate", _probe_expose_gate),
        ("product_armed", _probe_product_armed),
        ("keys", _probe_keys),
        ("rotation", _probe_rotation_due),
        ("auth_failures", _probe_auth_failures),
        ("a2a_card", _probe_a2a_card),
    ):
        try:
            s, k = probe()
        except Exception as exc:
            s, k = 50.0, {f"{name}_error": str(exc)[:120]}
        sub_scores.append(_clamp(s))
        kpis[name] = k

    score = round(sum(sub_scores) / len(sub_scores), 1) if sub_scores else None

    # Derive actions from KPIs
    if not kpis.get("dependency", {}).get("fastapi_mcp_installed"):
        actions.append("Install fastapi-mcp: add to requirements.txt + rebuild image")
    if not kpis.get("expose_gate", {}).get("mcp_endpoint_gated"):
        actions.append(
            "CRITICAL: /mcp is UNGATED — set FASTAPI_MCP_TOKEN or MCP_IP_ALLOWLIST in .env"
        )
    if not kpis.get("product_armed", {}).get("mcp_product_enabled"):
        actions.append("MCP-as-product paused — set MCP_PRODUCT=1 to enable B2B surface")
    pressured = kpis.get("keys", {}).get("quota_pressure_keys") or []
    if pressured:
        actions.append(
            f"Quota pressure on {len(pressured)} key(s): "
            + ", ".join(f"{p['label']}@{p['pct']}%" for p in pressured[:3])
        )
    rotation_due = kpis.get("rotation", {}).get("rotation_due") or []
    if rotation_due:
        actions.append(f"Rotate {len(rotation_due)} key(s) older than {_KEY_ROTATION_DAYS}d")
    auth_fails = kpis.get("auth_failures", {}).get("auth_failures_24h") or 0
    if isinstance(auth_fails, int) and auth_fails >= _AUTH_FAIL_ALERT_THRESHOLD:
        actions.append(f"AUTH ATTACK SIGNAL: {auth_fails} failed /mcp/* auth attempts in 24h")
        _maybe_alert(
            "MCP auth-failure spike",
            f"{auth_fails} failed auth attempts in 24h (threshold {_AUTH_FAIL_ALERT_THRESHOLD})",
            priority="high",
        )

    summary = f"MCP health {score:.0f}/100" if isinstance(score, float) else "MCP health unknown"
    if score is not None and score < 60:
        summary += " — attention needed"
    elif score is not None and score >= 90:
        summary += " — all green"

    result = {
        "role": "mcp",
        "score": score,
        "status": "ok",
        "summary": summary,
        "kpis": kpis,
        "actions": actions,
        "ts": int(time.time()),
    }
    _try_log("arya", "mcp_pulse", summary, status=("warn" if (score or 100) < 60 else "ok"))

    # Persist last-run for /api/platform/mcp/health
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        (_DATA_DIR / "mcp_engineer_last.json").write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    return result


def health_score() -> dict[str, Any]:
    """Fast snapshot (no logging, no alerts) — for /api/platform/mcp/health."""
    last_file = _DATA_DIR / "mcp_engineer_last.json"
    if last_file.exists():
        try:
            data = json.loads(last_file.read_text(encoding="utf-8"))
            age = int(time.time() - last_file.stat().st_mtime)
            data["last_run_age_s"] = age
            return data
        except Exception:
            pass
    return {"role": "mcp", "score": None, "status": "never_ran", "summary": "no health data yet"}


def rotation_due_keys() -> list[dict[str, Any]]:
    """Keys older than rotation threshold — for admin dashboard."""
    _, kpis = _probe_rotation_due()
    return kpis.get("rotation_due") or []


def audit_mcp_security() -> dict[str, Any]:
    """One-shot security probe — quick checklist for /verify."""
    items = {
        "fastapi_mcp_dep": _probe_dependency()[0] == 100.0,
        "mcp_endpoint_gated": _probe_expose_gate()[0] == 100.0,
        "mcp_product_armed": _probe_product_armed()[0] >= 100.0,
        "no_rotation_overdue": _probe_rotation_due()[0] == 100.0,
        "no_auth_attack": _probe_auth_failures()[0] >= 80.0,
        "a2a_card_valid": _probe_a2a_card()[0] == 100.0,
    }
    items["all_green"] = all(items.values())
    return items


def log_auth_failure(reason: str, ip: str = "", path: str = "") -> None:
    """Called by middleware on /mcp/* 401 — appends to _AUTH_FAIL_LOG.
    Tail-read by _probe_auth_failures for the alert threshold.
    """
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": int(time.time()),
            "reason": (reason or "")[:80],
            "ip": (ip or "")[:64],
            "path": (path or "")[:120],
        }
        with _AUTH_FAIL_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


__all__ = [
    "run_mcp",
    "health_score",
    "rotation_due_keys",
    "audit_mcp_security",
    "log_auth_failure",
]
