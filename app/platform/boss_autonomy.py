"""Boss Autonomy service — canonical owner-free decision advancement.

Thin, flag-gated orchestration over "app.platform.boss_decision_governance"
(imported as "bdg"). This module is the ONLY runtime owner of the "Boss runs
without a human" decision loop; it uses public bdg API exclusively.

Hard rules (no monkey-patching, no private catalog access):
  * Canonical Boss identity is "manager" (workforce registry), never "hermes".
  * Advisory (Second Brain / LLM Council) is advisory-only; its absence NEVER
    defaults to execution — empty/low-confidence advice defers.
  * Unknown decision types fail closed (never default GREEN).
  * OWNER_ONLY (UPI/payment) + RED lanes are non-delegable (authority class C).
  * Every decision is hash-bound; every execution is single-use (bdg CAS).
  * Every transition is audited by bdg.

Flags (both must be ON for any governance write):
  BOSS_FULL_AUTONOMY=1        -> this service is active (default OFF / inert)
  BOSS_DECISION_GOVERNANCE=1  -> canonical governance ledger active (bdg)

Authority classes (owner-mandate):
  A — Boss autonomous (GREEN): advance to consume after advice + review.
  B — owner-armed channel (AMBER): Boss reviews, parks at needs_owner.
  C — non-delegable (OWNER_ONLY + RED + UNKNOWN): refuse / surface owner.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any

from app.platform import boss_decision_governance as bdg
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

FLAG = "BOSS_FULL_AUTONOMY"
AUTHORITY_KEY_ENV = "BOSS_GOV_AUTHORITY_KEY"
CONFIDENCE_ENV = "BOSS_AUTONOMY_CONFIDENCE"
DEFAULT_CONFIDENCE = 0.65
BOSS_ID = "manager"  # canonical Boss (workforce registry); never "hermes"
_MAX_STEPS = 20


def _flag_on(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return bool(v) and v not in ("0", "false", "no", "off")


def enabled() -> bool:
    """Boss autonomy flag. Default OFF / inert."""
    return _flag_on(FLAG)


def governance_enabled() -> bool:
    return bdg.enabled()


def ready() -> bool:
    """Both autonomy and governance flags must be ON for any write."""
    return enabled() and bdg.enabled()


def boss_id() -> str:
    """Canonical Boss identity from governance public routing surface."""
    try:
        b = bdg.routing_coverage().get("boss")
        if b:
            return str(b).strip().lower()
    except Exception as exc:  # noqa: BLE001 - surface function never raises
        logger.debug("[boss_autonomy] boss_id lookup failed: %s", type(exc).__name__)
    return BOSS_ID


def confidence_threshold() -> float:
    try:
        return max(0.0, min(1.0, float(os.getenv(CONFIDENCE_ENV, DEFAULT_CONFIDENCE))))
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE


def authority_class(decision_type: str) -> str | None:
    """A (auto) | B (owner-armed channel) | C (non-delegable) | None (unknown)."""
    dt = (decision_type or "").strip().lower()
    meta = bdg.DECISION_TYPE_REGISTRY.get(dt)
    if not meta:
        return None
    if meta.get("owner_only"):
        return "C"
    lane = str(meta.get("lane") or "")
    if lane == "RED":
        return "C"
    if lane == "AMBER":
        return "B"
    if lane == "GREEN":
        return "A"
    return None


def _hmac_evidence(decision_id: str, content_sha256: str) -> dict[str, Any]:
    """Mint Boss HMAC authority evidence (governance verifies its own key)."""
    secret = (os.getenv(AUTHORITY_KEY_ENV) or "").strip()
    if not secret:
        return {"ok": False, "error": "authority_key_unset", "fail_closed": True}
    msg = f"{decision_id}|{content_sha256}".encode()
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {"ok": True, "evidence": {"kind": "hmac", "sig": sig}}


def _assess_advice(advice: dict[str, Any] | None) -> tuple[float, str, str]:
    """Return (confidence, verdict, reason). Empty/absent advice never executes."""
    notes = list((advice or {}).get("notes") or [])
    if not notes:
        return 0.0, "defer", "no_second_brain_notes"
    scores: list[float] = []
    for n in notes:
        if not isinstance(n, dict):
            continue
        try:
            scores.append(float(n.get("score")))
        except (TypeError, ValueError):
            scores.append(0.0)
    if not scores:
        return 0.0, "defer", "no_scored_notes"
    confidence = min(1.0, max(0.0, sum(scores) / len(scores)))
    threshold = confidence_threshold()
    if confidence < threshold:
        return confidence, "defer", f"confidence {confidence:.2f} < {threshold:.2f}"
    return confidence, "proceed", f"confidence {confidence:.2f} >= {threshold:.2f}"


def _rollout_of(agent_id: str) -> str:
    for row in bdg.routing_coverage().get("agents") or []:
        if str(row.get("agent_id") or "") == str(agent_id or ""):
            return str(row.get("rollout") or "unknown")
    return "unknown"


def evaluate_decision(decision_id: str) -> dict[str, Any]:
    """Read-only normalized view of one decision (never mutates)."""
    did = (decision_id or "").strip()
    cur = bdg.get_decision(did)
    if not cur:
        return {"ok": False, "error": "not_found", "decision_id": did}
    dt = str(cur.get("decision_type") or "")
    return {
        "ok": True,
        "decision_id": did,
        "state": cur.get("state"),
        "lane": cur.get("lane"),
        "decision_type": dt,
        "authority_class": authority_class(dt),
        "tenant_id": cur.get("tenant_id"),
        "agent_id": cur.get("agent_id"),
        "rollout": cur.get("rollout"),
        "content_sha256": cur.get("content_sha256"),
        "consumed": bool(cur.get("consumed")),
        "advice_present": bool(cur.get("advice")),
        "updated_at": cur.get("updated_at"),
    }


def propose_and_decide(
    *,
    decision_type: str,
    title: str = "",
    payload: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    agent_id: str | None = None,
    proposed_by: str | None = None,
    advance: bool = True,
) -> dict[str, Any]:
    """Propose one governed decision and (optionally) advance it to terminal.

    Uses ONLY public bdg API. Never raises.
    """
    if not enabled():
        return {"ok": False, "error": "autonomy_off", "flag": FLAG, "outcome": "autonomy_off"}
    if not bdg.enabled():
        return {"ok": False, "error": "governance_off", "outcome": "governance_off"}

    dt = (decision_type or "").strip().lower()
    tenant = (tenant_id or os.getenv("DEFAULT_TENANT_ID", "platform")).strip()
    agent = (agent_id or boss_id()).strip().lower()
    proposer = (proposed_by or agent).strip().lower()

    if authority_class(dt) is None:
        return {
            "ok": False,
            "error": "unknown_decision_type",
            "decision_type": dt,
            "fail_closed": True,
            "outcome": "unknown_decision_type",
        }

    p = bdg.propose_decision(
        tenant_id=tenant,
        agent_id=agent,
        decision_type=dt,
        title=title or dt,
        payload=dict(payload or {}),
        proposed_by=proposer,
        kind="decision",
    )
    if p.get("inert"):
        return {"ok": False, "error": "governance_off", "inert": True, "outcome": "governance_off"}
    if not p.get("ok"):
        return {**p, "outcome": p.get("error") or "propose_failed"}

    did = str(p["decision"]["decision_id"])
    if not advance:
        return {"ok": True, "decision_id": did, "decision": p["decision"], "advanced": False}

    result = advance_decision(did, max_steps=_MAX_STEPS)
    result["proposed"] = True
    return result


_KNOWN_HARD_ERRORS = frozenset(
    {
        "agent_unarmed",
        "advice_unavailable",
        "advice_malformed",
        "advice_hash_mismatch",
        "advice_cross_tenant",
        "advice_stale",
        "advice_future_timestamp",
        "advice_must_be_advisory",
        "boss_cannot_self_approve",
        "upi_owner_only",
        "red_lane",
        "review_required",
        "approval_required_before_execute",
        "stale_hash",
        "replay_rejected",
        "owner_decision_id_required",
        "authority_key_unset",
        "boss_authority_required",
    }
)


def advance_decision(
    decision_id: str,
    *,
    max_steps: int = 1,
    expected_sha256: str = "",
) -> dict[str, Any]:
    """Advance an EXISTING decision id (never re-proposes) toward terminal state.

    Idempotent: repeats re-read the same decision and move it one bounded step.
    outcome: executed | consumed | refused | rejected | deferred | needs_owner |
    agent_unarmed | non_delegable | unknown_decision_type | advice_unavailable |
    stale_hash | bad_state | not_found | autonomy_off | governance_off |
    authority_key_unset.
    """
    if not enabled():
        return {
            "ok": False,
            "error": "autonomy_off",
            "outcome": "autonomy_off",
            "decision_id": decision_id,
        }
    if not bdg.enabled():
        return {
            "ok": False,
            "error": "governance_off",
            "outcome": "governance_off",
            "decision_id": decision_id,
        }

    did = (decision_id or "").strip()
    steps = 0
    result: dict[str, Any] = {"ok": False, "decision_id": did, "steps": 0}

    while steps < max(1, min(100, max_steps)):
        cur = bdg.get_decision(did)
        if not cur:
            return {**result, "error": "not_found", "outcome": "not_found", "steps": steps}

        sha = str(cur.get("content_sha256") or "")
        if expected_sha256 and expected_sha256 != sha:
            return {
                **result,
                "error": "stale_hash",
                "outcome": "stale_hash",
                "fail_closed": True,
                "steps": steps,
            }

        state = str(cur.get("state") or "")
        dt = str(cur.get("decision_type") or "")

        if cur.get("consumed") or state in ("executed", "consumed"):
            return {
                "ok": True,
                "decision_id": did,
                "state": state,
                "outcome": state,
                "steps": steps,
            }
        if state in ("refused", "boss_rejected"):
            return {
                "ok": True,
                "decision_id": did,
                "state": state,
                "outcome": "refused" if state == "refused" else "rejected",
                "refused": True,
                "steps": steps,
            }

        aclass = authority_class(dt)
        if aclass == "C":
            return {
                **result,
                "error": "non_delegable",
                "outcome": "non_delegable",
                "authority_class": "C",
                "state": state,
                "lane": cur.get("lane"),
                "fail_closed": True,
                "steps": steps,
            }
        if aclass is None:
            return {
                **result,
                "error": "unknown_decision_type",
                "outcome": "unknown_decision_type",
                "fail_closed": True,
                "steps": steps,
            }

        if state in ("proposed", "advice_requested"):
            r = bdg.record_second_brain_advice(did, use_council=True)
        elif state == "advice_recorded":
            advice = cur.get("advice") or {}
            confidence, verdict, reason = _assess_advice(advice)
            ev = _hmac_evidence(did, sha)
            if not ev.get("ok"):
                return {**ev, "outcome": "authority_key_unset", "decision_id": did, "steps": steps}
            if verdict == "defer":
                review = bdg.boss_review_decision(
                    did,
                    reviewer_id=boss_id(),
                    verdict="defer",
                    reason=reason,
                    authority_evidence=ev["evidence"],
                )
                if review.get("ok"):
                    return {
                        "ok": False,
                        "decision_id": did,
                        "state": "boss_reviewed",
                        "outcome": "deferred",
                        "confidence": round(confidence, 4),
                        "steps": steps + 1,
                    }
                return {
                    **review,
                    "outcome": review.get("error") or "review_failed",
                    "steps": steps + 1,
                }
            r = bdg.boss_review_decision(
                did,
                reviewer_id=boss_id(),
                verdict="proceed",
                reason=reason,
                authority_evidence=ev["evidence"],
            )
        elif state == "boss_reviewed":
            review = cur.get("boss_review") or {}
            if str(review.get("verdict") or "") == "defer":
                return {
                    "ok": False,
                    "decision_id": did,
                    "state": "boss_reviewed",
                    "outcome": "deferred",
                    "steps": steps,
                }
            ev = _hmac_evidence(did, sha)
            if not ev.get("ok"):
                return {**ev, "outcome": "authority_key_unset", "decision_id": did, "steps": steps}
            r = bdg.boss_approve(
                did,
                actor_id=boss_id(),
                expected_sha256=sha,
                authority_evidence=ev["evidence"],
            )
        elif state == "boss_approved":
            r = bdg.consume_or_execute(
                did, expected_sha256=sha, mode="execute", actor_id="boss_autonomy"
            )
        elif state == "needs_owner":
            return {
                "ok": False,
                "decision_id": did,
                "state": "needs_owner",
                "outcome": "needs_owner",
                "authority_class": aclass,
                "steps": steps,
                "note": "AMBER requires Owner OS decision id — Boss never self-approves these.",
            }
        else:
            return {
                **result,
                "error": "bad_state",
                "outcome": "bad_state",
                "state": state,
                "steps": steps,
            }

        steps += 1
        if r.get("inert"):
            return {
                **result,
                "error": "governance_off",
                "outcome": "governance_off",
                "inert": True,
                "steps": steps,
            }
        if not r.get("ok"):
            err = str(r.get("error") or "advance_failed")
            outcome = err if err in _KNOWN_HARD_ERRORS else "advance_failed"
            return {**result, **r, "outcome": outcome, "steps": steps}

    result["steps"] = steps
    cur = bdg.get_decision(did)
    result["state"] = str((cur or {}).get("state") or "?")
    result["outcome"] = "advanced"
    return result


def sweep_due(limit: int = 30, tenant_id: str | None = None) -> dict[str, Any]:
    """Advance every pending decision by one bounded step. No re-proposing."""
    if not enabled():
        return {"ok": False, "error": "autonomy_off", "outcome": "autonomy_off"}
    if not bdg.enabled():
        return {"ok": False, "error": "governance_off", "outcome": "governance_off"}

    pending = bdg.list_pending(tenant_id=tenant_id, limit=max(1, min(200, limit)))
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for row in pending:
        did = str(row.get("decision_id") or "")
        r = advance_decision(did, max_steps=1)
        out = str(r.get("outcome") or "?")
        counts[out] = counts.get(out, 0) + 1
        results.append(
            {
                "decision_id": did,
                "decision_type": row.get("decision_type"),
                "state": row.get("state"),
                "lane": row.get("lane"),
                "outcome": out,
                "ok": bool(r.get("ok")),
            }
        )
    return {
        "ok": True,
        "swept": len(results),
        "counts": counts,
        "results": results,
    }


def _state_path() -> Path:
    try:
        from app.platform import runtime_data

        runtime_data.store_dir("boss_autonomy")
        return runtime_data.store_path("boss_autonomy", "state.json")
    except Exception:  # noqa: BLE001
        return Path("data") / "boss_autonomy_state.json"


def _write_heartbeat(summary: dict[str, Any]) -> None:
    try:
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "heartbeat_at": time.time(),
            "enabled": enabled(),
            "governance_enabled": bdg.enabled(),
            "last_swept": summary.get("swept"),
            "last_counts": summary.get("counts"),
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, default=str), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:  # noqa: BLE001 - heartbeat is best-effort
        logger.debug("[boss_autonomy] heartbeat write failed: %s", type(exc).__name__)


def run_once(*, limit: int = 30, tenant_id: str | None = None) -> dict[str, Any]:
    """One bounded sweep + heartbeat. Never raises."""
    result = sweep_due(limit=limit, tenant_id=tenant_id)
    _write_heartbeat(result)
    return result


def _read_heartbeat() -> dict[str, Any]:
    try:
        path = _state_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def status() -> dict[str, Any]:
    snap = bdg.metrics_snapshot()
    hb = _read_heartbeat()
    return {
        "flag": FLAG,
        "enabled": enabled(),
        "governance_flag": "BOSS_DECISION_GOVERNANCE",
        "governance_enabled": bdg.enabled(),
        "ready": ready(),
        "boss_id": boss_id(),
        "boss_rollout": _rollout_of(boss_id()),
        "confidence_threshold": confidence_threshold(),
        "pending": snap.get("decisions", 0),
        "by_state": snap.get("by_state", {}),
        "heartbeat": hb,
    }


def metrics() -> dict[str, Any]:
    snap = bdg.metrics_snapshot()
    return {
        **snap,
        "autonomy_enabled": enabled(),
        "autonomy_flag": FLAG,
        "boss_id": boss_id(),
        "confidence_threshold": confidence_threshold(),
    }


__all__ = [
    "FLAG",
    "BOSS_ID",
    "enabled",
    "governance_enabled",
    "ready",
    "boss_id",
    "authority_class",
    "confidence_threshold",
    "evaluate_decision",
    "propose_and_decide",
    "advance_decision",
    "sweep_due",
    "run_once",
    "status",
    "metrics",
]
