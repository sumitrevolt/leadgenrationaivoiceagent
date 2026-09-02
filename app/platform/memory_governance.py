"""Memory governance — TWO redaction policies, do-not-remember, staleness/conflict.

Review P0/P1: the v2 hot-path fix replaced a strong redactor with a weaker regex
everywhere, which traded privacy for latency. That was wrong. The correct split
is by DESTINATION, not by speed:

  POLICY A — `scrub_secrets(text)`  (prompt-bound, microseconds)
      Destination: an AUTHORIZED, tenant-scoped agent prompt.
      Removes: secret-shaped tokens (API keys, JWTs, KEY/TOKEN/SECRET=... env
      lines). Keeps: the lead's phone/name/email — that IS the memory payload,
      and the prompt is already tenant-scoped and authorized.

  POLICY B — `mask_for_observability(text)`  (everything else)
      Destination: logs, exceptions, audit rows, admin API responses, UI
      diagnostics, metrics, error strings.
      Removes: secrets AND PII (phone, email, long digit runs), via the
      canonical `redact_packet_text` first (guardrails PII + secrets) and then
      an explicit phone/email mask so the result never depends on guardrails
      being importable. ~80ms — fine here, never on the assembly path.

  DO-NOT-REMEMBER
      Tenant-scoped suppression rules (`session`, `subject`, `pattern`).
      Suppressed content is never written to working/prospective memory;
      `forget()` also deletes what already matched. The audit row stores a
      HASH of the matched text, never the text.

  STALENESS / CONFLICT
      `resolve_conflicts()` — for `key: value` lines carrying an
      `(observed: <iso>)` marker, newest authoritative value wins deterministically
      and older contradicting values are dropped from the assembled context. The
      dropped pairs are returned so a caller can audit them.

Stores: `data/memory_suppression.jsonl` (rules) + `data/memory_governance_audit.jsonl`
(hashes only). Stdlib-only at import time; never raises.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_RULES_PATH_DEFAULT = os.path.join("data", "memory_suppression.jsonl")
_AUDIT_PATH_DEFAULT = os.path.join("data", "memory_governance_audit.jsonl")

RULE_SESSION = "session"
RULE_SUBJECT = "subject"
RULE_PATTERN = "pattern"
RULE_KINDS = frozenset({RULE_SESSION, RULE_SUBJECT, RULE_PATTERN})


def _rules_path() -> str:
    return (os.getenv("MEMORY_SUPPRESSION_PATH") or "").strip() or _RULES_PATH_DEFAULT


def _audit_path() -> str:
    return (os.getenv("MEMORY_GOVERNANCE_AUDIT_PATH") or "").strip() or _AUDIT_PATH_DEFAULT


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _h(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------- POLICY A: secrets only

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[REDACTED_KEY]", re.compile(r"\b(?:sk|pk|rk|gsk|xox[baprs])[-_][A-Za-z0-9\-_]{12,}\b")),
    ("[REDACTED_GOOGLE]", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("[REDACTED_AWS]", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "[REDACTED_JWT]",
        re.compile(r"\beyJ[A-Za-z0-9\-_]{8,}\.[A-Za-z0-9\-_]{8,}\.[A-Za-z0-9\-_]{8,}\b"),
    ),
    (
        "\\1=[REDACTED_ENV]",
        re.compile(r"(?im)\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|VPA))\s*=\s*\S+"),
    ),
)


def scrub_secrets(text: str) -> str:
    """POLICY A — prompt-bound. Secrets out, authorized lead data in. Never raises."""
    out = text or ""
    try:
        for repl, pat in SECRET_PATTERNS:
            out = pat.sub(repl, out)
    except Exception:
        return text or ""
    return out


# ------------------------------------------------ POLICY B: secrets + PII masks

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("[EMAIL]", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("[PHONE]", re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s\-]?)?\d{10}(?!\d)")),
    ("[NUM]", re.compile(r"(?<!\d)\d{11,19}(?!\d)")),  # long digit runs (acct/UPI ref)
)


def mask_for_observability(text: str) -> str:
    """POLICY B — logs/audit/admin/UI/metrics/errors. Secrets AND PII removed."""
    out = text or ""
    try:
        from app.dev_control.context_packets import redact_packet_text

        out = redact_packet_text(out)
    except Exception:
        pass  # guardrails unavailable -> the layers below still run
    # ALWAYS run our own secret set too: the canonical redactor does not cover
    # every shape (caught by test 2026-08-05 — a Google AIza key survived it).
    out = scrub_secrets(out)
    try:
        for repl, pat in _PII_PATTERNS:
            out = pat.sub(repl, out)
    except Exception:
        pass
    return out


def mask_row(
    row: dict[str, Any], *, fields: tuple[str, ...] = ("action", "note", "last_error")
) -> dict[str, Any]:
    """Mask the free-text fields of an admin/API row. Payload dict is dropped."""
    try:
        out = dict(row or {})
        for f in fields:
            if out.get(f):
                out[f] = mask_for_observability(str(out[f]))
        if "payload" in out:
            out["payload_keys"] = sorted((out.get("payload") or {}).keys())
            out.pop("payload", None)
        return out
    except Exception:
        return {"masked": True}


# ------------------------------------------------------- DO-NOT-REMEMBER rules


def _read_rules() -> list[dict[str, Any]]:
    path = _rules_path()
    rows: list[dict[str, Any]] = []
    try:
        if not os.path.exists(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return rows
    return [r for r in rows if not r.get("revoked")]


def _append(path: str, rec: dict[str, Any]) -> bool:
    """Append one JSONL row. Match keys only — never credentials.

    Callers must refuse secret-shaped values before building `rec`. This helper
    does NOT run secret scrubbers on the payload: those functions are modeled as
    secret-handling sinks and re-tainting the write trips CodeQL
    py/clear-text-storage-sensitive-data even after scrubbing.
    """
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception as e:
        logger.debug("[memory_governance] append failed: %s", e)
        return False


def audit(tenant_id: str, action: str, *, matched_text: str = "", meta: dict | None = None) -> None:
    """Audit WITHOUT the raw content — only a hash of what was suppressed."""
    _append(
        _audit_path(),
        {
            "at": _now(),
            "tenant_id": str(tenant_id or "")[:64],
            "action": str(action or "")[:64],
            "matched_hash": _h(matched_text) if matched_text else "",
            "meta": {k: str(v)[:120] for k, v in (meta or {}).items()},
        },
    )


def suppress(
    tenant_id: str,
    kind: str,
    value: str,
    *,
    reason: str = "",
    actor: str = "",
) -> dict[str, Any]:
    """Register a do-not-remember rule. Tenant-scoped; never raises."""
    tid = str(tenant_id or "").strip()[:64]
    k = str(kind or "").strip().lower()
    val = str(value or "").strip()[:200]
    if not tid:
        return {"ok": False, "error": "tenant_id required"}
    if k not in RULE_KINDS:
        return {"ok": False, "error": f"kind must be one of {sorted(RULE_KINDS)}"}
    if not val:
        return {"ok": False, "error": "value required"}
    # Never persist secret-shaped tokens as match keys (API keys / JWTs / env secrets).
    if scrub_secrets(val) != val:
        return {"ok": False, "error": "value looks like a secret — refuse to store cleartext"}
    reason_raw = str(reason or "")[:200]
    if scrub_secrets(reason_raw) != reason_raw:
        reason_raw = ""  # drop secret-shaped free text; do not store redactor output
    if k == RULE_PATTERN:
        try:
            re.compile(val)
        except Exception:
            return {"ok": False, "error": "invalid regex pattern"}
    rec = {
        "id": _h(f"{tid}|{k}|{val}")[:16],
        "tenant_id": tid,
        "kind": k,
        "match_key": val,
        "reason": reason_raw,
        "actor": str(actor or "")[:64],
        "at": _now(),
    }
    if not _append(_rules_path(), rec):
        return {"ok": False, "error": "write failed"}
    audit(tid, "suppress", meta={"kind": k, "rule_id": rec["id"]})
    return {"ok": True, "rule": rec}


def unsuppress(tenant_id: str, rule_id: str) -> dict[str, Any]:
    """Revoke a rule (append-only tombstone). Tenant-scoped."""
    tid = str(tenant_id or "").strip()[:64]
    if not tid or not rule_id:
        return {"ok": False, "error": "tenant_id and rule_id required"}
    hit = [r for r in _read_rules() if r.get("tenant_id") == tid and r.get("id") == rule_id]
    if not hit:
        return {"ok": False, "error": "not found for this tenant"}
    _append(_rules_path(), {"id": rule_id, "tenant_id": tid, "revoked": True, "at": _now()})
    audit(tid, "unsuppress", meta={"rule_id": rule_id})
    return {"ok": True, "rule_id": rule_id}


def list_rules(tenant_id: str) -> list[dict[str, Any]]:
    tid = str(tenant_id or "").strip()[:64]
    if not tid:
        return []
    revoked = {
        r.get("id") for r in _read_rules_raw() if r.get("revoked") and r.get("tenant_id") == tid
    }
    return [r for r in _read_rules() if r.get("tenant_id") == tid and r.get("id") not in revoked]


def _read_rules_raw() -> list[dict[str, Any]]:
    path = _rules_path()
    rows: list[dict[str, Any]] = []
    try:
        if not os.path.exists(path):
            return rows
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        pass
    return rows


DECISION_ALLOW = "allow"
DECISION_SUPPRESSED = "suppressed"
DECISION_DEFERRED = "deferred"
DEFER_CODE = "MEMORY_WRITE_DEFERRED_GOVERNANCE_UNAVAILABLE"


def governance_health() -> dict[str, Any]:
    """Is the do-not-remember authority TRUSTWORTHY right now?

    `ok=False` means we cannot prove a write is allowed — unreadable file,
    unparsable lines, or an unexpected error. Unknown is treated as unhealthy.
    """
    h = rules_health()
    if not h.get("readable", False):
        return {"ok": False, "reason": "dnr rules unreadable", **h}
    if int(h.get("unparsable") or 0) > 0:
        return {"ok": False, "reason": "dnr rules contain unparsable entries", **h}
    return {"ok": True, "reason": "", **h}


EVAL_MATCH = "match"
EVAL_NO_MATCH = "no_match"
EVAL_ERROR = "error"


def _evaluate_rules(
    tenant_id: str, *, session_id: str = "", subject_id: str = "", text: str = ""
) -> str:
    """Tri-state rule evaluation: match | no_match | error.

    An evaluation ERROR is deliberately NOT collapsed into "match": a governance
    outage is not a user suppression, and conflating them would fabricate
    suppression audits and could trigger deletions (review P0, 2026-08-05).
    """
    tid = str(tenant_id or "").strip()[:64]
    if not tid:
        return EVAL_NO_MATCH
    try:
        for r in list_rules(tid):
            kind = str(r.get("kind"))
            val = str(r.get("match_key") or r.get("value") or "")
            if kind == RULE_SESSION and session_id and val == str(session_id):
                return EVAL_MATCH
            if kind == RULE_SUBJECT and subject_id and val == str(subject_id):
                return EVAL_MATCH
            if kind == RULE_PATTERN and text and re.search(val, text, re.IGNORECASE):
                return EVAL_MATCH
    except Exception as e:
        logger.debug("[memory_governance] rule evaluation error: %s", e)
        return EVAL_ERROR
    return EVAL_NO_MATCH


def is_suppressed(
    tenant_id: str,
    *,
    session_id: str = "",
    subject_id: str = "",
    text: str = "",
) -> bool:
    """Convenience helper: True ONLY when a real rule matched.

    An evaluation error returns False here — it is NOT "not suppressed", it is
    "unknown", and callers that persist anything must use `check_write()` (which
    turns unknown into DEFERRED). This helper must never be used at a durable
    write, audit or deletion boundary.
    """
    return (
        _evaluate_rules(tenant_id, session_id=session_id, subject_id=subject_id, text=text)
        == EVAL_MATCH
    )


def check_write(
    tenant_id: str,
    *,
    session_id: str = "",
    subject_id: str = "",
    text: str = "",
    durable: bool = True,
) -> dict[str, Any]:
    """THE write gate. Fail-CLOSED for durable memory. Never echoes content.

    Returns {decision, code, reason} where decision is allow | suppressed |
    deferred. `deferred` means the DNR authority could not be trusted, so the
    caller must NOT persist — not in the record, not in retry state, not in
    `last_error`, not in an audit payload. The foreground agent may still answer;
    it just answers WITHOUT remembering.
    """
    tid = str(tenant_id or "").strip()[:64]
    if not tid:
        return {
            "decision": DECISION_DEFERRED,
            "code": "MEMORY_WRITE_REFUSED_NO_TENANT",
            "reason": "tenant_id required",
        }
    if durable:
        health = governance_health()
        if not health.get("ok"):
            # unknown/unavailable governance => refuse to persist raw content
            return {
                "decision": DECISION_DEFERRED,
                "code": DEFER_CODE,
                "reason": str(health.get("reason") or "governance unavailable"),
            }
    verdict = _evaluate_rules(tid, session_id=session_id, subject_id=subject_id, text=text)
    if verdict == EVAL_ERROR:
        # an outage is NOT a suppression: no rule-match audit, no matched_hash,
        # no deletion — only a deferral with a masked reason.
        return {
            "decision": DECISION_DEFERRED,
            "code": DEFER_CODE,
            "reason": "do-not-remember rule evaluation failed",
        }
    if verdict == EVAL_MATCH:
        return {
            "decision": DECISION_SUPPRESSED,
            "code": "MEMORY_WRITE_SUPPRESSED_BY_RULE",
            "reason": "matched a do-not-remember rule",
        }
    return {"decision": DECISION_ALLOW, "code": "", "reason": ""}


def remembering_allowed(tenant_id: str) -> bool:
    """False => callers should run in answer-without-remembering mode."""
    return check_write(tenant_id, durable=True)["decision"] != DECISION_DEFERRED


def durable_writes_allowed(*, only_when_stack_enabled: bool = True) -> dict[str, Any]:
    """Health-only gate for lanes that have no tenant handle (episodic/semantic).

    Those modules are keyed by lead/agent, not tenant, so per-tenant RULES cannot
    be evaluated there — but the HEALTH contract still applies: if the DNR
    authority is unreadable/unknown, a durable write must not happen.
    """
    if only_when_stack_enabled and (
        os.getenv("MEMORY_STACK_ENABLED") or ""
    ).strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"ok": True, "code": "", "reason": "memory stack off"}
    h = governance_health()
    if h.get("ok"):
        return {"ok": True, "code": "", "reason": ""}
    return {"ok": False, "code": DEFER_CODE, "reason": str(h.get("reason") or "unavailable")}


def guard_durable_write(
    tenant_id: str,
    *,
    session_id: str = "",
    subject_id: str = "",
    text: str = "",
    only_when_stack_enabled: bool = True,
) -> dict[str, Any]:
    """Guard for lanes OUTSIDE this package (episodic/semantic/shared).

    `only_when_stack_enabled` keeps existing lanes byte-identical while the
    memory-stack master flag is OFF — the fail-closed contract applies to the
    system being released, not retroactively to untouched code paths.
    """
    if only_when_stack_enabled and (
        os.getenv("MEMORY_STACK_ENABLED") or ""
    ).strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"decision": DECISION_ALLOW, "code": "", "reason": "memory stack off"}
    return check_write(
        tenant_id, session_id=session_id, subject_id=subject_id, text=text, durable=True
    )


def forget(
    tenant_id: str, *, session_id: str = "", subject_id: str = "", agent_id: str = ""
) -> dict[str, Any]:
    """Delete what already matched: prospective rows + this process's hot cache.

    REFUSED during a governance outage — a destructive deletion must never be
    driven by an authority we cannot read (review P0). Deletion resumes once the
    rules store is healthy again.
    """
    tid = str(tenant_id or "").strip()[:64]
    if not tid:
        return {"ok": False, "error": "tenant_id required"}
    health = governance_health()
    if not health.get("ok"):
        return {
            "ok": False,
            "deferred": True,
            "code": DEFER_CODE,
            "error": str(health.get("reason") or "governance unavailable"),
        }
    out: dict[str, Any] = {"ok": True, "prospective_purged": 0, "working_cleared": 0}
    try:
        from app.platform import prospective_store as ps

        res = ps.purge(tid, agent_id=agent_id)
        out["prospective_purged"] = int(res.get("purged") or 0)
    except Exception:
        out["prospective_error"] = "purge_failed"
    try:
        from app.platform import memory_stack as ms

        if session_id:
            out["working_cleared"] = 1 if ms.clear_working(tid, session_id) else 0
        else:
            out["working_cleared"] = ms.clear_tenant_working(tid)
    except Exception:
        out["working_error"] = "clear_failed"
    audit(tid, "forget", meta={"session": bool(session_id), "subject": bool(subject_id)})
    return out


def rules_health() -> dict[str, Any]:
    """Ops: is the rules file readable, how many rules, any parse damage."""
    path = _rules_path()
    total = bad = 0
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    total += 1
                    try:
                        json.loads(line)
                    except Exception:
                        bad += 1
    except Exception:
        return {"readable": False, "error": "rules_unreadable"}
    return {"readable": True, "lines": total, "unparsable": bad}


# ------------------------------------------------- STALENESS / CONFLICT (L3)

# "- key: value (observed: 2026-08-05T10:00:00Z)"  — provenance marker is optional
_FACT_RE = re.compile(
    r"^\s*[-•*]?\s*(?P<key>[A-Za-z][A-Za-z0-9 _/\-]{1,40})\s*:\s*(?P<val>.+?)\s*$"
)
_OBS_RE = re.compile(r"\(observed:\s*(?P<ts>[0-9T:\-\.\+Z ]{8,32})\)\s*$", re.IGNORECASE)


def _parse_obs(value: str) -> tuple[str, datetime | None]:
    m = _OBS_RE.search(value or "")
    if not m:
        return value, None
    ts = m.group("ts").strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        return value, None
    return _OBS_RE.sub("", value).strip(), dt.astimezone(timezone.utc)


REASON_STALE = "stale"
REASON_DUPLICATE = "duplicate"
REASON_CONFLICTED = "conflicted"

# Default source authority for equal-timestamp ties. Higher wins. Distilled
# semantic facts outrank a procedural lesson; a hot working transcript is not an
# authority about a customer fact at all.
_DEFAULT_AUTHORITY = {
    "semantic": 3,
    "episodic": 2,
    "shared": 1,
    "procedural": 0,
    "prospective": 0,
    "working": 0,
}


def lane_authority() -> dict[str, int]:
    """`MEMORY_STACK_LANE_AUTHORITY=semantic:3,episodic:2` overrides the defaults."""
    out = dict(_DEFAULT_AUTHORITY)
    raw = (os.getenv("MEMORY_STACK_LANE_AUTHORITY") or "").strip()
    if not raw:
        return out
    for part in raw.split(","):
        if ":" not in part:
            continue
        name, _, val = part.partition(":")
        try:
            out[name.strip().lower()] = int(val.strip())
        except Exception:
            continue
    return out


def resolve_facts(
    items: list[tuple[str, str]],
    *,
    authority: dict[str, int] | None = None,
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Cross-lane fact resolution. `items` = [(lane, text)] in injection order.

    Policy (deterministic, and NOT "whoever came first"):
      1. Newer valid `(observed: <iso>)` wins.
      2. At equal (or absent) time, higher configured SOURCE AUTHORITY wins.
      3. Equal time AND equal/undefined authority AND different values =>
         **CONFLICTED**: neither value is injected into the agent context; the
         pair is preserved (masked) for review.
      4. Identical values are deduplicated, never conflicted.
      5. A malformed timestamp is treated as absent — it can never outrank a
         valid one.
    Returns (items_out, report[]). Report values are masked for observability.
    """
    rank = authority or lane_authority()
    # key -> list of candidates
    cand: dict[str, list[dict[str, Any]]] = {}
    parsed: list[list[Any]] = []  # per item: list of (line, key|None, cand_ref)

    for idx, (lane, text) in enumerate(items):
        rows: list[Any] = []
        for line in (text or "").split("\n"):
            m = _FACT_RE.match(line)
            if not m:
                rows.append((line, None, None))
                continue
            key = m.group("key").strip().lower()
            val, obs = _parse_obs(m.group("val").strip())
            entry = {
                "item": idx,
                "lane": lane,
                "key": key,
                "value": val,
                "obs": obs,
                "auth": int(rank.get(str(lane).lower(), 0)),
                "line": line,
                "keep": False,
            }
            cand.setdefault(key, []).append(entry)
            rows.append((line, key, entry))
        parsed.append(rows)

    report: list[dict[str, Any]] = []

    for key, entries in cand.items():
        # collapse identical values first (dedupe, not conflict)
        by_value: dict[str, list[dict[str, Any]]] = {}
        for e in entries:
            by_value.setdefault(e["value"].strip().lower(), []).append(e)
        for _v, group in by_value.items():
            for extra in group[1:]:
                report.append(
                    {
                        "key": key,
                        "reason": REASON_DUPLICATE,
                        "lane": extra["lane"],
                        "value": mask_for_observability(extra["value"]),
                    }
                )
        distinct = [g[0] for g in by_value.values()]
        if len(distinct) == 1:
            distinct[0]["keep"] = True
            continue

        # 1) newest valid timestamp
        with_obs = [e for e in distinct if e["obs"] is not None]
        if with_obs:
            newest = max(e["obs"] for e in with_obs)
            top = [e for e in with_obs if e["obs"] == newest]
        else:
            top = list(distinct)

        # 2) source authority at equal time
        if len(top) > 1:
            best_auth = max(e["auth"] for e in top)
            top = [e for e in top if e["auth"] == best_auth]

        if len(top) == 1:
            winner = top[0]
            winner["keep"] = True
            for e in distinct:
                if e is winner:
                    continue
                report.append(
                    {
                        "key": key,
                        "reason": REASON_STALE,
                        "lane": e["lane"],
                        "value": mask_for_observability(e["value"]),
                        "superseded_by_lane": winner["lane"],
                    }
                )
        else:
            # 3) unresolved: inject NEITHER value
            for e in distinct:
                report.append(
                    {
                        "key": key,
                        "reason": REASON_CONFLICTED,
                        "lane": e["lane"],
                        "value": mask_for_observability(e["value"]),
                    }
                )

    out: list[tuple[str, str]] = []
    for idx, (lane, _text) in enumerate(items):
        kept_lines = [
            line for line, key, entry in parsed[idx] if key is None or (entry and entry["keep"])
        ]
        out.append((lane, "\n".join(kept_lines)))
    return out, report


def resolve_conflicts(
    text: str, *, lane: str = "", authority: dict[str, int] | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Single-block wrapper around `resolve_facts` (same policy)."""
    items, report = resolve_facts([(lane or "unknown", text)], authority=authority)
    return items[0][1], report


__all__ = [
    "SECRET_PATTERNS",
    "scrub_secrets",
    "mask_for_observability",
    "mask_row",
    "suppress",
    "unsuppress",
    "list_rules",
    "is_suppressed",
    "check_write",
    "guard_durable_write",
    "governance_health",
    "remembering_allowed",
    "forget",
    "rules_health",
    "audit",
    "resolve_facts",
    "resolve_conflicts",
    "lane_authority",
    "DECISION_ALLOW",
    "DECISION_SUPPRESSED",
    "DECISION_DEFERRED",
    "DEFER_CODE",
    "REASON_STALE",
    "REASON_DUPLICATE",
    "REASON_CONFLICTED",
    "RULE_SESSION",
    "RULE_SUBJECT",
    "RULE_PATTERN",
]
