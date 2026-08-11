"""Boss + Second Brain governed decision approvals (ADR-adjacent, INERT default).

Extends Owner OS / approvals_bridge / runtime-data — NOT a second approval plane.

State machine (decision-bearing outputs ONLY — not heartbeats/logs/telemetry/drafts):
  proposed → advice_requested → advice_recorded → boss_reviewed
    → boss_approved | boss_rejected | needs_owner | refused
    → executed | consumed

Authority:
  GREEN  — Boss may approve after valid Second Brain advice + gates
  AMBER  — needs Owner OS decision id (human)
  RED    — refuse
  UPI / payment — always owner-only (human)
  Boss cannot self-approve a decision they proposed
  held/disabled agents stay unarmed (routing coverage ≠ live execute)

Second Brain = advisory only (obsidian_sync.recall + optional LLM Council).
Fail-closed if advice unavailable / stale / malformed / cross-tenant.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "BOSS_DECISION_GOVERNANCE"
_LEDGER_SEGMENTS = ("boss_decision_governance", "decisions.jsonl")
_AUDIT_SEGMENTS = ("boss_decision_governance", "audit.jsonl")

# Terminal + intermediate states
STATES = frozenset(
    {
        "proposed",
        "advice_requested",
        "advice_recorded",
        "boss_reviewed",
        "boss_approved",
        "boss_rejected",
        "needs_owner",
        "refused",
        "executed",
        "consumed",
    }
)

_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"advice_requested", "refused"}),
    "advice_requested": frozenset({"advice_recorded", "refused"}),
    "advice_recorded": frozenset({"boss_reviewed", "refused", "needs_owner"}),
    "boss_reviewed": frozenset({"boss_approved", "boss_rejected", "needs_owner", "refused"}),
    "boss_approved": frozenset({"executed", "consumed"}),
    "boss_rejected": frozenset({"consumed"}),
    "needs_owner": frozenset({"boss_approved", "boss_rejected", "refused", "consumed"}),
    "refused": frozenset({"consumed"}),
    "executed": frozenset({"consumed"}),
    "consumed": frozenset(),
}

# Decision types that are NEVER Boss-self-executable
_OWNER_ONLY_TYPES = frozenset(
    {
        "upi_payment",
        "payment_confirm",
        "manual_upi_credit",
        "billing_activate",
        "subscription_activate",
    }
)

_RED_TYPES = frozenset(
    {
        "cold_outbound_call",
        "compliance_override",
        "dnd_bypass",
        "voice_kill_disable",
        "secret_export",
        "cross_tenant_read",
    }
)

_AMBER_TYPES = frozenset(
    {
        "customer_content_publish",
        "whatsapp_send",
        "outbound_email_blast",
        "social_publish",
        "flag_flip_prod",
        "scheduler_arm",
    }
)

# Non-decision noise — refuse to govern as approval objects
_NON_DECISION_KINDS = frozenset(
    {
        "heartbeat",
        "telemetry",
        "log",
        "draft",
        "pulse",
        "roster",
        "handoff_summary",
        "aggregate_verdict",
    }
)

_ADVICE_MAX_AGE_S = 6 * 3600  # 6h — stale advice fail-closed
_BOSS_ID = "manager"


def enabled() -> bool:
    return (os.getenv(_FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _ledger_path():
    from app.platform import runtime_data

    runtime_data.store_dir(_LEDGER_SEGMENTS[0])
    return runtime_data.store_path(*_LEDGER_SEGMENTS)


def _audit_path():
    from app.platform import runtime_data

    runtime_data.store_dir(_AUDIT_SEGMENTS[0])
    return runtime_data.store_path(*_AUDIT_SEGMENTS)


def _append_jsonl(path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception as e:
        logger.debug("[boss_gov] read skip: %s", e)
    return out


def _audit(action: str, detail: dict[str, Any]) -> None:
    try:
        _append_jsonl(
            _audit_path(),
            {"at": _now_iso(), "action": action, **detail},
        )
    except Exception as e:
        logger.debug("[boss_gov] audit skip: %s", e)


def content_hash(
    *,
    tenant_id: str,
    agent_id: str,
    decision_type: str,
    payload: dict[str, Any],
) -> str:
    blob = json.dumps(
        {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "decision_type": decision_type,
            "payload": payload or {},
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def classify_lane_strict(decision_type: str) -> str:
    """RED refuse; UPI/payment + customer-touch AMBER (owner gate); else GREEN."""
    dt = (decision_type or "").strip().lower()
    if dt in _RED_TYPES:
        return "RED"
    if dt in _OWNER_ONLY_TYPES or dt in _AMBER_TYPES:
        return "AMBER"
    return "GREEN"


def _staff_ids() -> list[str]:
    from app.platform.team import STAFF

    return sorted(STAFF.keys())


def _agent_rollout(agent_id: str) -> str:
    """canary | held | disabled — mirrors runtime allowlists; never invents live fire."""
    aid = (agent_id or "").strip().lower()
    try:
        from app.platform.agent_runtime import PILOT_AGENTS
        from app.platform.agent_runtime_workforce import (
            AMBER_HOLD_AGENTS,
            FROZEN_VOICE_AGENTS,
            GREEN_MUTATE_HOLD,
            VOICE_HOLD_AGENTS,
        )

        if aid in FROZEN_VOICE_AGENTS:
            return "disabled"
        if aid in PILOT_AGENTS:
            return "canary"
        if aid in AMBER_HOLD_AGENTS or aid in VOICE_HOLD_AGENTS or aid in GREEN_MUTATE_HOLD:
            return "held"
        if aid in _staff_ids():
            return "held"
        return "disabled"
    except Exception:
        return "held"


def routing_coverage() -> dict[str, Any]:
    """Static 31/31 routing coverage for canonical STAFF + decision lanes.

    This is routing readiness — NOT proof that every live customer decision
    was Boss-approved after Second Brain advice.
    """
    staff = _staff_ids()
    rows = []
    for aid in staff:
        rows.append(
            {
                "agent_id": aid,
                "rollout": _agent_rollout(aid),
                "decision_authority": "boss_within_agent_contract",
                "governed": True,
                "armed": _agent_rollout(aid) == "canary",
            }
        )
    covered = {r["agent_id"] for r in rows if r["governed"]}
    return {
        "ok": len(staff) == 31 and covered == set(staff),
        "staff_count": len(staff),
        "covered_count": len(covered),
        "missing": sorted(set(staff) - covered),
        "boss": _BOSS_ID,
        "claim_note": (
            "31/31 = static routing coverage for canonical STAFF identities/"
            "decision types — not live customer decisions for held agents."
        ),
        "agents": rows,
        "decision_types_catalog": sorted(
            _OWNER_ONLY_TYPES | _AMBER_TYPES | _RED_TYPES | {"internal_plan", "ops_report"}
        ),
    }


def _latest_by_id() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _read_jsonl(_ledger_path()):
        did = str(row.get("decision_id") or "")
        if did:
            latest[did] = row
    return latest


def get_decision(decision_id: str) -> dict[str, Any] | None:
    return _latest_by_id().get((decision_id or "").strip())


def list_pending(*, tenant_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    open_states = {
        "proposed",
        "advice_requested",
        "advice_recorded",
        "boss_reviewed",
        "boss_approved",
        "needs_owner",
    }
    rows = []
    for d in _latest_by_id().values():
        if str(d.get("state") or "") not in open_states:
            continue
        if tenant_id and str(d.get("tenant_id") or "") != str(tenant_id):
            continue
        rows.append(d)
    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    return rows[: max(1, min(200, limit))]


def owner_os_visibility(*, limit: int = 40) -> dict[str, Any]:
    """Owner OS pending decisions surface (read model over same ledger)."""
    items = list_pending(limit=limit)
    return {
        "ok": True,
        "source": "boss_decision_governance",
        "flag": _FLAG,
        "enabled": enabled(),
        "pending": len(items),
        "items": [
            {
                "decision_id": r.get("decision_id"),
                "state": r.get("state"),
                "lane": r.get("lane"),
                "tenant_id": r.get("tenant_id"),
                "agent_id": r.get("agent_id"),
                "decision_type": r.get("decision_type"),
                "title": (r.get("title") or r.get("decision_type") or "")[:160],
                "content_sha256": r.get("content_sha256"),
                "updated_at": r.get("updated_at"),
                "decidable_here": r.get("state") == "needs_owner",
                "ui_state": "operational" if r.get("state") == "needs_owner" else "view_only",
            }
            for r in items
        ],
        "note": "Governed decisions share Owner OS visibility; no parallel approval SPA.",
    }


def buzz_ro_projection(*, limit: int = 20) -> dict[str, Any]:
    """Buzz #admin read-only mirror — never mutates, never includes secrets/payloads."""
    items = list_pending(limit=limit)
    return {
        "channel": "#admin",
        "mode": "read_only",
        "pending": len(items),
        "items": [
            {
                "decision_id": r.get("decision_id"),
                "state": r.get("state"),
                "lane": r.get("lane"),
                "agent_id": r.get("agent_id"),
                "decision_type": r.get("decision_type"),
                "tenant_present": bool(r.get("tenant_id")),
            }
            for r in items
        ],
        "mutation": False,
        "note": "Buzz visibility plane only — execute via Owner OS / runtime gates.",
    }


def propose_decision(
    *,
    tenant_id: str,
    agent_id: str,
    decision_type: str,
    title: str = "",
    payload: dict[str, Any] | None = None,
    kind: str = "decision",
    proposed_by: str | None = None,
) -> dict[str, Any]:
    """Create a governed decision object. Non-decision kinds are refused."""
    kind_l = (kind or "decision").strip().lower()
    if kind_l in _NON_DECISION_KINDS:
        return {
            "ok": False,
            "error": "not_a_decision_object",
            "kind": kind_l,
            "note": "Heartbeats/telemetry/drafts/aggregates are not approval objects.",
        }
    tenant_id = (tenant_id or "").strip()
    agent_id = (agent_id or "").strip().lower()
    decision_type = (decision_type or "").strip().lower()
    if not tenant_id or not agent_id or not decision_type:
        return {"ok": False, "error": "tenant_id, agent_id, decision_type required"}
    if agent_id not in set(_staff_ids()):
        return {"ok": False, "error": "unknown_agent", "agent_id": agent_id}
    if "/" in tenant_id or "\\" in tenant_id or ".." in tenant_id:
        return {"ok": False, "error": "unsafe_tenant_id"}

    payload = dict(payload or {})
    # Strip obvious secret-shaped keys from stored payload
    for k in list(payload.keys()):
        lk = str(k).lower()
        if any(s in lk for s in ("password", "secret", "api_key", "token", "private_key")):
            payload.pop(k, None)

    lane = classify_lane_strict(decision_type)
    sha = content_hash(
        tenant_id=tenant_id,
        agent_id=agent_id,
        decision_type=decision_type,
        payload=payload,
    )
    decision_id = "bdg_" + uuid.uuid4().hex[:16]
    proposer = (proposed_by or agent_id).strip().lower()
    row = {
        "decision_id": decision_id,
        "state": "proposed",
        "lane": lane,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "decision_type": decision_type,
        "title": (title or decision_type)[:160],
        "payload": payload,
        "content_sha256": sha,
        "proposed_by": proposer,
        "advice": None,
        "boss_review": None,
        "owner_decision_id": None,
        "consumed": False,
        "rollout": _agent_rollout(agent_id),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "schema": "boss_decision_governance.v1",
    }
    if lane == "RED":
        row["state"] = "refused"
        row["refuse_reason"] = "red_lane"
    # Mirror into approvals_bridge verification stream (same Owner OS ledger surface)
    try:
        from app.platform import approvals_bridge

        mirrored = approvals_bridge.create_verification_approval(
            title=f"[governed] {row['title']}",
            note=(
                f"lane={lane} agent={agent_id} type={decision_type} "
                f"sha={sha[:12]} decision_id={decision_id}"
            ),
            meta={
                "content_sha256": sha,
                "decision_type": decision_type,
                "lane": lane,
                "governance": "boss_decision_governance",
                "decision_id": decision_id,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
            },
        )
        if isinstance(mirrored, dict) and mirrored.get("id"):
            row["verification_item_id"] = mirrored["id"]
    except Exception as e:
        logger.debug("[boss_gov] approvals_bridge mirror skip: %s", e)
    _append_jsonl(_ledger_path(), row)
    _audit("propose", {"decision_id": decision_id, "state": row["state"], "lane": lane})
    return {"ok": True, "decision": row}


def _transition(
    decision_id: str, to_state: str, patch: dict[str, Any] | None = None
) -> dict[str, Any]:
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    from_state = str(cur.get("state") or "")
    if to_state not in STATES:
        return {"ok": False, "error": "bad_state"}
    allowed = _TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        return {
            "ok": False,
            "error": "illegal_transition",
            "from": from_state,
            "to": to_state,
        }
    if cur.get("consumed"):
        return {"ok": False, "error": "already_consumed"}
    row = dict(cur)
    row.update(patch or {})
    row["state"] = to_state
    row["updated_at"] = _now_iso()
    row["prev_state"] = from_state
    _append_jsonl(_ledger_path(), row)
    _audit("transition", {"decision_id": decision_id, "from": from_state, "to": to_state})
    return {"ok": True, "decision": row}


def request_advice(decision_id: str) -> dict[str, Any]:
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) == "refused":
        return {"ok": False, "error": "refused"}
    return _transition(decision_id, "advice_requested")


def record_second_brain_advice(
    decision_id: str,
    *,
    query: str | None = None,
    use_council: bool = False,
    injected_advice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record advisory Second Brain output. Never authoritative.

    Fail-closed when unavailable/stale/malformed/cross-tenant.
    ``injected_advice`` is for tests only (must include required fields).
    """
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) not in ("proposed", "advice_requested"):
        # allow propose→request then record; auto-request if still proposed
        if str(cur.get("state")) == "proposed":
            req = request_advice(decision_id)
            if not req.get("ok"):
                return req
            cur = req["decision"]
        else:
            return {"ok": False, "error": "bad_state", "state": cur.get("state")}

    tenant_id = str(cur.get("tenant_id") or "")
    sha = str(cur.get("content_sha256") or "")
    q = (query or f"{cur.get('decision_type')} {cur.get('title')} {tenant_id}").strip()

    advice: dict[str, Any]
    if injected_advice is not None:
        advice = dict(injected_advice)
    else:
        notes: list[dict[str, Any]] = []
        try:
            from app.platform import obsidian_sync

            notes = list(obsidian_sync.recall(q, k=3) or [])
        except Exception as e:
            logger.debug("[boss_gov] recall failed: %s", e)
            notes = []
        if not notes and not use_council:
            _transition(
                decision_id,
                "refused",
                {"refuse_reason": "advice_unavailable", "advice": None},
            )
            return {"ok": False, "error": "advice_unavailable", "fail_closed": True}
        council_blob = None
        if use_council:
            try:
                # Soft — council absence is OK if recall had notes; else fail-closed
                from app.agents import llm_council

                if hasattr(llm_council, "decide_sync"):
                    council_blob = {"status": "skipped_sync_unavailable"}
                else:
                    council_blob = {"status": "module_present", "authoritative": False}
            except Exception:
                council_blob = None
            if not notes and council_blob is None:
                _transition(
                    decision_id,
                    "refused",
                    {"refuse_reason": "advice_unavailable"},
                )
                return {"ok": False, "error": "advice_unavailable", "fail_closed": True}
        advice = {
            "source": "obsidian_sync.recall",
            "authoritative": False,
            "query": q[:200],
            "notes": [
                {
                    "folder": n.get("folder"),
                    "slug": n.get("slug"),
                    "score": n.get("score"),
                    "excerpt": (n.get("excerpt") or "")[:200],
                }
                for n in notes[:3]
            ],
            "council": council_blob,
            "bound_content_sha256": sha,
            "bound_tenant_id": tenant_id,
            "recorded_at": _now_iso(),
        }

    # Validate advice shape + bindings
    if not isinstance(advice, dict):
        _transition(decision_id, "refused", {"refuse_reason": "advice_malformed"})
        return {"ok": False, "error": "advice_malformed", "fail_closed": True}
    if advice.get("authoritative") is True:
        _transition(decision_id, "refused", {"refuse_reason": "advice_claimed_authority"})
        return {"ok": False, "error": "advice_must_be_advisory", "fail_closed": True}
    if str(advice.get("bound_content_sha256") or "") != sha:
        _transition(decision_id, "refused", {"refuse_reason": "advice_hash_mismatch"})
        return {"ok": False, "error": "advice_hash_mismatch", "fail_closed": True}
    if str(advice.get("bound_tenant_id") or "") != tenant_id:
        _transition(decision_id, "refused", {"refuse_reason": "advice_cross_tenant"})
        return {"ok": False, "error": "advice_cross_tenant", "fail_closed": True}
    try:
        recorded = datetime.fromisoformat(
            str(advice.get("recorded_at") or "").replace("Z", "+00:00")
        )
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        age = (_now() - recorded).total_seconds()
        if age > _ADVICE_MAX_AGE_S or age < -60:
            _transition(decision_id, "refused", {"refuse_reason": "advice_stale"})
            return {"ok": False, "error": "advice_stale", "fail_closed": True}
    except Exception:
        _transition(decision_id, "refused", {"refuse_reason": "advice_malformed_ts"})
        return {"ok": False, "error": "advice_malformed", "fail_closed": True}

    if str(cur.get("state")) == "proposed":
        request_advice(decision_id)
    return _transition(decision_id, "advice_recorded", {"advice": advice})


def boss_review_decision(
    decision_id: str,
    *,
    reviewer_id: str = _BOSS_ID,
    verdict: str = "proceed",
    reason: str = "",
) -> dict[str, Any]:
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) != "advice_recorded":
        return {"ok": False, "error": "advice_required_before_review", "state": cur.get("state")}
    reviewer_id = (reviewer_id or "").strip().lower()
    if reviewer_id != _BOSS_ID:
        return {"ok": False, "error": "only_boss_reviews", "reviewer_id": reviewer_id}
    review = {
        "by": reviewer_id,
        "verdict": (verdict or "proceed")[:40],
        "reason": (reason or "")[:200],
        "at": _now_iso(),
        "bound_content_sha256": cur.get("content_sha256"),
    }
    return _transition(decision_id, "boss_reviewed", {"boss_review": review})


def boss_approve(
    decision_id: str,
    *,
    actor_id: str = _BOSS_ID,
    expected_sha256: str = "",
    owner_decision_id: str | None = None,
) -> dict[str, Any]:
    """GREEN Boss approve after advice+review. AMBER needs owner_decision_id. RED refuse."""
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    actor_id = (actor_id or "").strip().lower()
    lane = str(cur.get("lane") or "")
    state = str(cur.get("state") or "")

    if expected_sha256 and expected_sha256 != cur.get("content_sha256"):
        return {"ok": False, "error": "stale_hash", "fail_closed": True}
    if cur.get("consumed"):
        return {"ok": False, "error": "replay_rejected", "fail_closed": True}

    # Boss cannot self-approve a decision they proposed
    if actor_id == str(cur.get("proposed_by") or "").lower() and actor_id == _BOSS_ID:
        return {"ok": False, "error": "boss_cannot_self_approve", "fail_closed": True}

    if str(cur.get("decision_type") or "") in _OWNER_ONLY_TYPES:
        return {
            "ok": False,
            "error": "upi_owner_only",
            "fail_closed": True,
            "note": "Manual UPI / payment confirmation is human-only.",
        }

    rollout = str(cur.get("rollout") or _agent_rollout(str(cur.get("agent_id") or "")))
    if rollout in ("held", "disabled"):
        return {
            "ok": False,
            "error": "agent_unarmed",
            "rollout": rollout,
            "fail_closed": True,
            "note": "held/disabled agents cannot execute even if routing-covered.",
        }

    if lane == "RED":
        return _transition(decision_id, "refused", {"refuse_reason": "red_lane"})

    if state not in ("boss_reviewed", "needs_owner"):
        return {"ok": False, "error": "review_required", "state": state}

    if lane == "AMBER":
        oid = (owner_decision_id or cur.get("owner_decision_id") or "").strip()
        if not oid:
            if state != "needs_owner":
                return _transition(
                    decision_id,
                    "needs_owner",
                    {"refuse_reason": None, "note": "AMBER requires Owner OS decision id"},
                )
            return {"ok": False, "error": "owner_decision_id_required", "lane": "AMBER"}
        return _transition(
            decision_id,
            "boss_approved",
            {
                "owner_decision_id": oid,
                "approved_by": actor_id,
                "approved_at": _now_iso(),
            },
        )

    # GREEN
    if actor_id != _BOSS_ID and state != "needs_owner":
        return {"ok": False, "error": "boss_or_owner_required"}
    if state == "needs_owner" and not (owner_decision_id or cur.get("owner_decision_id")):
        return {"ok": False, "error": "owner_decision_id_required"}

    return _transition(
        decision_id,
        "boss_approved",
        {
            "approved_by": actor_id,
            "approved_at": _now_iso(),
            "owner_decision_id": owner_decision_id or cur.get("owner_decision_id"),
        },
    )


def boss_reject(
    decision_id: str,
    *,
    actor_id: str = _BOSS_ID,
    reason: str = "",
) -> dict[str, Any]:
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) not in ("boss_reviewed", "needs_owner", "advice_recorded"):
        return {"ok": False, "error": "bad_state", "state": cur.get("state")}
    # from advice_recorded, must pass boss_reviewed first for reject? Allow reject from reviewed/needs_owner.
    if str(cur.get("state")) == "advice_recorded":
        br = boss_review_decision(
            decision_id, reviewer_id=actor_id, verdict="reject", reason=reason
        )
        if not br.get("ok"):
            return br
    return _transition(
        decision_id,
        "boss_rejected",
        {"rejected_by": actor_id, "reject_reason": (reason or "")[:200]},
    )


def mark_needs_owner(decision_id: str, *, owner_decision_id: str = "") -> dict[str, Any]:
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    patch = {}
    if owner_decision_id:
        patch["owner_decision_id"] = owner_decision_id.strip()
    if str(cur.get("state")) == "needs_owner":
        if patch:
            row = dict(cur)
            row.update(patch)
            row["updated_at"] = _now_iso()
            _append_jsonl(_ledger_path(), row)
            return {"ok": True, "decision": row}
        return {"ok": True, "decision": cur}
    if str(cur.get("state")) not in ("advice_recorded", "boss_reviewed"):
        return {"ok": False, "error": "bad_state", "state": cur.get("state")}
    return _transition(decision_id, "needs_owner", patch)


def consume_or_execute(
    decision_id: str,
    *,
    expected_sha256: str = "",
    mode: str = "execute",
    actor_id: str = "runtime",
) -> dict[str, Any]:
    """One-time consume. Requires boss_approved + hash match. Fail-closed otherwise."""
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if cur.get("consumed") or str(cur.get("state")) in ("consumed", "executed"):
        return {"ok": False, "error": "replay_rejected", "fail_closed": True}
    if str(cur.get("state")) != "boss_approved":
        return {
            "ok": False,
            "error": "approval_required_before_execute",
            "state": cur.get("state"),
            "fail_closed": True,
        }
    if not cur.get("advice"):
        return {"ok": False, "error": "advice_required_before_execute", "fail_closed": True}
    if expected_sha256 and expected_sha256 != cur.get("content_sha256"):
        return {"ok": False, "error": "stale_hash", "fail_closed": True}
    if str(cur.get("rollout") or "") in ("held", "disabled"):
        return {"ok": False, "error": "agent_unarmed", "fail_closed": True}
    if str(cur.get("decision_type") or "") in _OWNER_ONLY_TYPES:
        return {"ok": False, "error": "upi_owner_only", "fail_closed": True}
    if not enabled():
        return {
            "ok": False,
            "error": "flag_off",
            "flag": _FLAG,
            "fail_closed": True,
            "note": "Governance execute path INERT until BOSS_DECISION_GOVERNANCE=1",
        }

    to_state = "executed" if mode == "execute" else "consumed"
    out = _transition(
        decision_id,
        to_state,
        {
            "consumed": True,
            "consumed_by": actor_id,
            "consumed_at": _now_iso(),
        },
    )
    if out.get("ok"):
        try:
            from app.platform import approvals_bridge

            vid = str(cur.get("verification_item_id") or "").strip()
            if vid:
                approvals_bridge.decide(
                    "owner_os_verification",
                    vid,
                    "approve",
                    by=actor_id,
                    reason="governed_consume",
                )
        except Exception:
            pass
    return out


def assert_aggregate_is_not_approval(aggregate: dict[str, Any] | None) -> dict[str, Any]:
    """Falsify treating hierarchical aggregate Boss verdict as per-decision approval."""
    agg = aggregate or {}
    verdict = agg.get("verdict") if isinstance(agg.get("verdict"), dict) else {}
    return {
        "is_per_decision_approval": False,
        "aggregate_status": verdict.get("status") or agg.get("status"),
        "reason": (
            "coordinate_hierarchical / office_hq.boss_review emit aggregate or "
            "recommendation-only signals — not hash-bound per-decision approval."
        ),
        "required_for_execute": [
            "advice_recorded",
            "boss_reviewed",
            "boss_approved",
            "content_sha256_match",
            "tenant_match",
            "one_time_consume",
        ],
    }


def metrics_snapshot() -> dict[str, Any]:
    latest = _latest_by_id()
    by_state: dict[str, int] = {}
    for r in latest.values():
        st = str(r.get("state") or "?")
        by_state[st] = by_state.get(st, 0) + 1
    return {
        "flag": _FLAG,
        "enabled": enabled(),
        "decisions": len(latest),
        "by_state": by_state,
        "routing": {
            "staff_count": routing_coverage().get("staff_count"),
            "coverage_ok": routing_coverage().get("ok"),
        },
    }


__all__ = [
    "STATES",
    "enabled",
    "content_hash",
    "classify_lane_strict",
    "routing_coverage",
    "propose_decision",
    "request_advice",
    "record_second_brain_advice",
    "boss_review_decision",
    "boss_approve",
    "boss_reject",
    "mark_needs_owner",
    "consume_or_execute",
    "get_decision",
    "list_pending",
    "owner_os_visibility",
    "buzz_ro_projection",
    "assert_aggregate_is_not_approval",
    "metrics_snapshot",
]
