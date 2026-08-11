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
import hmac
import importlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "BOSS_DECISION_GOVERNANCE"
_LEDGER_SEGMENTS = ("boss_decision_governance", "decisions.jsonl")
_AUDIT_SEGMENTS = ("boss_decision_governance", "audit.jsonl")
_CLAIM_SEGMENTS = ("boss_decision_governance", "claims")
_ADVICE_FUTURE_SKEW_S = 60  # reject recorded_at more than 60s in the future

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

# Explicit GREEN catalog — unknown types NEVER default to GREEN
_GREEN_TYPES = frozenset(
    {
        "internal_plan",
        "ops_report",
        "staff_task_complete",
        "hierarchical_member_output",
    }
)

# Typed decision registry (lane + owner-only). Unknown = absent = fail-closed.
DECISION_TYPE_REGISTRY: dict[str, dict[str, Any]] = {
    **{t: {"lane": "GREEN", "owner_only": False} for t in _GREEN_TYPES},
    **{t: {"lane": "AMBER", "owner_only": False} for t in _AMBER_TYPES},
    **{t: {"lane": "AMBER", "owner_only": True} for t in _OWNER_ONLY_TYPES},
    **{t: {"lane": "RED", "owner_only": False} for t in _RED_TYPES},
}

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
_PRODUCER_PATH = "app.platform.boss_decision_governance.adapter_propose_for_agent"
_CONSUMER_PATH = "app.platform.boss_decision_governance.consume_or_execute"


@dataclass(frozen=True)
class DecisionAdapter:
    """Explicit typed adapter — roster presence alone is NOT governance coverage."""

    agent_id: str
    producer: str
    consumer: str
    default_decision_type: str
    role: str = "staff"


def _redis_client():
    """Only when REDIS_URL is explicitly set — never silently share localhost state."""
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        import redis as _redis

        return _redis.from_url(url, decode_responses=True, socket_connect_timeout=1.5)
    except Exception:
        return None


def _atomic_claim(claim_key: str, *, ttl_s: int = 86400) -> bool:
    """Cross-process one-time claim. Redis SET NX when REDIS_URL set; else O_EXCL file."""
    key = (claim_key or "").strip()
    if not key or "/" in key or "\\" in key or ".." in key:
        return False
    r = _redis_client()
    if r is not None:
        try:
            return bool(r.set(f"bdg:claim:{key}", "1", nx=True, ex=max(60, int(ttl_s))))
        except Exception as e:
            logger.warning(
                "[boss_gov] redis claim failed key=%s err=%s", key[:48], type(e).__name__
            )
            # Explicit REDIS_URL + failure = fail closed (no silent dual-consume).
            return False
    try:
        from app.platform import runtime_data

        runtime_data.store_dir(_CLAIM_SEGMENTS[0], _CLAIM_SEGMENTS[1])
        path = runtime_data.store_path(*_CLAIM_SEGMENTS, f"{key}.claimed")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, b"1")
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception as e:
        logger.error("[boss_gov] claim primitive failed key=%s err=%s", key[:48], type(e).__name__)
        return False


def _resolve_callable(dotted: str) -> Callable[..., Any] | None:
    mod_name, _, attr = (dotted or "").rpartition(".")
    if not mod_name or not attr:
        return None
    try:
        mod = importlib.import_module(mod_name)
        fn = getattr(mod, attr, None)
        return fn if callable(fn) else None
    except Exception as e:
        logger.warning("[boss_gov] adapter resolve failed %s: %s", dotted, type(e).__name__)
        return None


def build_adapter_registry(
    *,
    staff_ids: list[str] | None = None,
    include_agents: list[str] | None = None,
) -> dict[str, DecisionAdapter]:
    """Build explicit per-STAFF adapters. ``include_agents`` limits for tests."""
    ids = list(staff_ids if staff_ids is not None else _staff_ids())
    if include_agents is not None:
        allow = {a.strip().lower() for a in include_agents}
        ids = [a for a in ids if a in allow]
    out: dict[str, DecisionAdapter] = {}
    for aid in ids:
        dtype = "ops_report" if aid == _BOSS_ID else "hierarchical_member_output"
        out[aid] = DecisionAdapter(
            agent_id=aid,
            producer=_PRODUCER_PATH,
            consumer=_CONSUMER_PATH,
            default_decision_type=dtype,
            role="boss" if aid == _BOSS_ID else "staff",
        )
    return out


def adapter_registry() -> dict[str, DecisionAdapter]:
    return build_adapter_registry()


def adapter_propose_for_agent(
    *,
    agent_id: str,
    tenant_id: str,
    decision_type: str | None = None,
    title: str = "",
    payload: dict[str, Any] | None = None,
    proposed_by: str | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Canonical producer adapter used by coordinator / STAFF paths."""
    reg = adapter_registry()
    aid = (agent_id or "").strip().lower()
    if aid not in reg:
        return {"ok": False, "error": "no_adapter", "agent_id": aid, "fail_closed": True}
    ad = reg[aid]
    return propose_decision(
        tenant_id=tenant_id,
        agent_id=aid,
        decision_type=(decision_type or ad.default_decision_type),
        title=title or f"{aid} decision",
        payload={**(payload or {}), **({"run_id": run_id} if run_id else {})},
        proposed_by=proposed_by or aid,
        kind="decision",
    )


def propose_from_hierarchical_run(run: dict[str, Any] | None) -> dict[str, Any]:
    """Wire hierarchical coordinator outputs into governed propose (flag-gated)."""
    if not enabled():
        return {"ok": True, "inert": True, "written": 0, "flag": _FLAG}
    run = run or {}
    run_id = str(run.get("run_id") or "")
    tenant_id = str(run.get("tenant_id") or os.getenv("DEFAULT_TENANT_ID") or "platform").strip()
    written: list[str] = []
    errors: list[dict[str, Any]] = []
    for team in run.get("teams") or []:
        for result in team.get("results") or []:
            if not isinstance(result, dict):
                continue
            if result.get("error") or result.get("mode") == "skipped":
                continue
            agent = str(result.get("agent") or "").strip().lower()
            if not agent:
                continue
            out = adapter_propose_for_agent(
                agent_id=agent,
                tenant_id=tenant_id,
                decision_type="hierarchical_member_output",
                title=f"hier:{run_id}:{agent}",
                payload={
                    "mode": result.get("mode"),
                    "output_excerpt": str(result.get("output") or "")[:400],
                },
                proposed_by=agent,
                run_id=run_id,
            )
            if out.get("ok") and out.get("decision"):
                written.append(str(out["decision"].get("decision_id")))
            elif out.get("inert"):
                continue
            else:
                errors.append({"agent": agent, "error": out.get("error")})
    return {
        "ok": not errors,
        "written": len(written),
        "decision_ids": written,
        "errors": errors,
        "run_id": run_id,
    }


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
        # Critical audit path must be observable — never silent success.
        logger.error("[boss_gov] AUDIT_WRITE_FAILED action=%s err=%s", action, type(e).__name__)
        raise


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
    """Typed registry only. Unknown types are UNKNOWN (fail-closed — never GREEN)."""
    dt = (decision_type or "").strip().lower()
    meta = DECISION_TYPE_REGISTRY.get(dt)
    if not meta:
        return "UNKNOWN"
    return str(meta.get("lane") or "UNKNOWN")


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


def routing_coverage(
    *,
    registry: dict[str, DecisionAdapter] | None = None,
) -> dict[str, Any]:
    """Coverage from explicit typed adapter registry — not hardcoded governed=True.

    Roster enumeration alone is NOT governance coverage (task-observer #30).
    """
    staff = _staff_ids()
    reg = registry if registry is not None else adapter_registry()
    rows = []
    for aid in staff:
        ad = reg.get(aid)
        producer_ok = bool(ad and _resolve_callable(ad.producer))
        consumer_ok = bool(ad and _resolve_callable(ad.consumer))
        governed = bool(ad and producer_ok and consumer_ok)
        rows.append(
            {
                "agent_id": aid,
                "rollout": _agent_rollout(aid),
                "decision_authority": "boss_within_agent_contract",
                "governed": governed,
                "armed": _agent_rollout(aid) == "canary" and governed,
                "adapter": (
                    None
                    if not ad
                    else {
                        "producer": ad.producer,
                        "consumer": ad.consumer,
                        "default_decision_type": ad.default_decision_type,
                        "producer_resolves": producer_ok,
                        "consumer_resolves": consumer_ok,
                    }
                ),
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
            "31/31 requires explicit typed adapters with resolvable producer+consumer "
            "for every STAFF id — not live customer decisions for held agents, and "
            "not roster enumeration alone."
        ),
        "agents": rows,
        "decision_types_catalog": sorted(DECISION_TYPE_REGISTRY.keys()),
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
    """Create a governed decision object. Non-decision kinds are refused.

    Flag OFF = fully inert (no ledger / approval / audit writes).
    """
    if not enabled():
        return {
            "ok": True,
            "inert": True,
            "flag": _FLAG,
            "note": "BOSS_DECISION_GOVERNANCE OFF — legacy path unchanged; zero governance writes.",
        }
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
    if agent_id not in adapter_registry():
        return {"ok": False, "error": "no_adapter", "agent_id": agent_id, "fail_closed": True}
    if "/" in tenant_id or "\\" in tenant_id or ".." in tenant_id:
        return {"ok": False, "error": "unsafe_tenant_id"}
    if decision_type not in DECISION_TYPE_REGISTRY:
        return {
            "ok": False,
            "error": "unknown_decision_type",
            "decision_type": decision_type,
            "fail_closed": True,
            "note": "Unknown types refuse until registered (never default GREEN).",
        }

    payload = dict(payload or {})
    # Strip obvious secret-shaped keys from stored payload
    for k in list(payload.keys()):
        lk = str(k).lower()
        if any(s in lk for s in ("password", "secret", "api_key", "token", "private_key")):
            payload.pop(k, None)

    lane = classify_lane_strict(decision_type)
    if lane == "UNKNOWN":
        return {"ok": False, "error": "unknown_decision_type", "fail_closed": True}
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
                "risk": lane,
                "mission_id": decision_id,
                "action": decision_type,
                "governance": "boss_decision_governance",
                "decision_id": decision_id,
                "tenant_id": tenant_id,
                "agent_id": agent_id,
            },
        )
        if not isinstance(mirrored, dict) or not mirrored.get("ok") or not mirrored.get("id"):
            logger.error(
                "[boss_gov] approval_mirror_failed decision_id=%s",
                decision_id,
            )
            return {
                "ok": False,
                "error": "approval_mirror_failed",
                "fail_closed": True,
            }
        row["verification_item_id"] = mirrored["id"]
    except Exception as e:
        logger.error("[boss_gov] approvals_bridge mirror exception: %s", type(e).__name__)
        return {"ok": False, "error": "approval_mirror_failed", "fail_closed": True}
    try:
        _append_jsonl(_ledger_path(), row)
        _audit("propose", {"decision_id": decision_id, "state": row["state"], "lane": lane})
    except Exception as e:
        logger.error("[boss_gov] ledger/audit write failed: %s", type(e).__name__)
        return {"ok": False, "error": "ledger_write_failed", "fail_closed": True}
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
    if not enabled():
        return {"ok": True, "inert": True, "flag": _FLAG}
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) == "refused":
        return {"ok": False, "error": "refused"}
    return _transition(decision_id, "advice_requested")


def _fetch_second_brain_advice(
    *,
    query: str,
    tenant_id: str,
    content_sha256: str,
    use_council: bool = False,
) -> dict[str, Any]:
    """Advisory provider — tests monkeypatch this; no production inject hook."""
    notes: list[dict[str, Any]] = []
    try:
        from app.platform import obsidian_sync

        notes = list(obsidian_sync.recall(query, k=3) or [])
    except Exception as e:
        logger.debug("[boss_gov] recall failed: %s", e)
        notes = []
    if not notes and not use_council:
        return {"ok": False, "error": "advice_unavailable"}
    council_blob = None
    if use_council:
        try:
            from app.agents import llm_council

            if hasattr(llm_council, "decide_sync"):
                council_blob = {"status": "skipped_sync_unavailable"}
            else:
                council_blob = {"status": "module_present", "authoritative": False}
        except Exception:
            council_blob = None
        if not notes and council_blob is None:
            return {"ok": False, "error": "advice_unavailable"}
    return {
        "ok": True,
        "advice": {
            "source": "obsidian_sync.recall",
            "authoritative": False,
            "query": query[:200],
            "notes": [
                {
                    "folder": n.get("folder"),
                    "slug": n.get("slug"),
                    "score": n.get("score"),
                    "excerpt": (n.get("excerpt") or "")[:200],
                    "tenant_id": n.get("tenant_id") or n.get("client_id"),
                    "namespace": n.get("namespace") or n.get("folder"),
                }
                for n in notes[:3]
            ],
            "council": council_blob,
            "bound_content_sha256": content_sha256,
            "bound_tenant_id": tenant_id,
            "recorded_at": _now_iso(),
        },
    }


def _validate_note_tenant_provenance(notes: list[Any], tenant_id: str) -> str | None:
    """Refuse notes that declare a different tenant/namespace. Returns error code or None."""
    want = (tenant_id or "").strip()
    for n in notes or []:
        if not isinstance(n, dict):
            continue
        declared = str(n.get("tenant_id") or n.get("client_id") or "").strip()
        if declared and declared != want:
            return "advice_cross_tenant_note"
        ns = str(n.get("namespace") or n.get("folder") or "").strip().lower()
        if ns.startswith("client:") and want and not ns.startswith(f"client:{want.lower()}"):
            return "advice_cross_tenant_note"
        if ns.startswith("tenant:") and want and ns != f"tenant:{want.lower()}":
            return "advice_cross_tenant_note"
    return None


def verify_boss_authority(
    *,
    decision_id: str,
    content_sha256: str,
    evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    """Authenticate Boss. Request ``actor_id`` alone NEVER establishes authority."""
    ev = dict(evidence or {})
    kind = str(ev.get("kind") or "").strip().lower()
    if not kind:
        return {"ok": False, "error": "boss_authority_required", "fail_closed": True}

    if kind == "boss_run":
        run_id = str(ev.get("run_id") or "").strip()
        if not run_id:
            return {"ok": False, "error": "boss_run_id_required", "fail_closed": True}
        # Evidence must bind the exact decision hash — run_id alone is not enough.
        ev_sha = str(ev.get("content_sha256") or "").strip()
        if not ev_sha or ev_sha != content_sha256:
            return {
                "ok": False,
                "error": "boss_run_hash_mismatch",
                "fail_closed": True,
            }
        try:
            from app.agents.coordinator import recent_runs

            for run in recent_runs(80):
                if str(run.get("run_id") or "") != run_id:
                    continue
                if str(run.get("boss") or "").lower() != _BOSS_ID:
                    continue
                if str(run.get("pattern") or "") != "hierarchical":
                    continue
                run_sha = str(run.get("content_sha256") or "").strip()
                if run_sha and run_sha != content_sha256:
                    return {
                        "ok": False,
                        "error": "boss_run_hash_mismatch",
                        "fail_closed": True,
                    }
                return {"ok": True, "actor_id": _BOSS_ID, "via": "boss_run", "run_id": run_id}
        except Exception as e:
            logger.warning("[boss_gov] boss_run lookup failed: %s", type(e).__name__)
        return {"ok": False, "error": "boss_run_not_found", "fail_closed": True}

    if kind == "hmac":
        secret = (os.getenv("BOSS_GOV_AUTHORITY_KEY") or "").strip()
        if not secret:
            return {"ok": False, "error": "authority_key_unset", "fail_closed": True}
        msg = f"{decision_id}|{content_sha256}".encode()
        expect = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()
        got = str(ev.get("sig") or "").strip().lower()
        if got and hmac.compare_digest(expect, got):
            return {"ok": True, "actor_id": _BOSS_ID, "via": "hmac"}
        return {"ok": False, "error": "bad_boss_hmac", "fail_closed": True}

    if kind == "owner_os":
        # Owner OS identity evidence is only valid for needs_owner transitions,
        # not as a substitute Boss GREEN signature.
        return {"ok": False, "error": "owner_os_not_boss_authority", "fail_closed": True}

    return {"ok": False, "error": "unknown_authority_kind", "fail_closed": True}


def verify_and_consume_owner_decision(
    owner_decision_id: str,
    *,
    tenant_id: str,
    agent_id: str,
    decision_type: str,
    content_sha256: str,
    decision_id: str,
    lane: str,
) -> dict[str, Any]:
    """Verify Owner OS / verification approval bindings + one-time consume."""
    oid = (owner_decision_id or "").strip()
    if not oid:
        return {"ok": False, "error": "owner_decision_id_required", "fail_closed": True}
    try:
        from app.platform import approvals_bridge
    except Exception as e:
        logger.error("[boss_gov] approvals_bridge import failed: %s", type(e).__name__)
        return {"ok": False, "error": "owner_verifier_unavailable", "fail_closed": True}

    draft = approvals_bridge.get_verification_draft(oid)
    if not draft:
        return {"ok": False, "error": "owner_decision_not_found", "fail_closed": True}

    status = "pending"
    try:
        status_fn = getattr(approvals_bridge, "_status_for", None)
        if callable(status_fn):
            status = str(status_fn("owner_os_verification", oid) or "pending").lower()
        else:
            listed = approvals_bridge.list_drafts(include_decided=True)
            for it in listed.get("drafts") or []:
                if str(it.get("id") or "") == oid:
                    status = str(it.get("status") or "pending").lower()
                    break
    except Exception as e:
        logger.error("[boss_gov] owner status lookup failed: %s", type(e).__name__)
        return {"ok": False, "error": "owner_status_unverified", "fail_closed": True}

    if status != "approved":
        return {
            "ok": False,
            "error": "owner_decision_not_approved",
            "status": status,
            "fail_closed": True,
        }

    meta = draft.get("meta") if isinstance(draft.get("meta"), dict) else {}
    checks = {
        "content_sha256": content_sha256,
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "decision_type": decision_type,
        "decision_id": decision_id,
        "lane": lane,
        "mission_id": decision_id,
        "action": decision_type,
    }
    for field, expect in checks.items():
        got = str(meta.get(field) or "").strip()
        if got != str(expect):
            return {
                "ok": False,
                "error": f"owner_binding_mismatch:{field}",
                "fail_closed": True,
            }

    if not _atomic_claim(f"owner:{oid}"):
        return {
            "ok": False,
            "error": "owner_decision_already_consumed",
            "fail_closed": True,
        }
    return {"ok": True, "owner_decision_id": oid, "status": status}


def record_second_brain_advice(
    decision_id: str,
    *,
    query: str | None = None,
    use_council: bool = False,
) -> dict[str, Any]:
    """Record advisory Second Brain output. Never authoritative.

    Fail-closed when unavailable/stale/malformed/cross-tenant.
    Tests monkeypatch ``_fetch_second_brain_advice`` — no production inject hook.
    """
    if not enabled():
        return {"ok": True, "inert": True, "flag": _FLAG}
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    # proposed → advice_requested first (checked return); other states refuse.
    if str(cur.get("state")) == "proposed":
        req = request_advice(decision_id)
        if not req.get("ok"):
            return {
                "ok": False,
                "error": req.get("error") or "request_advice_failed",
                "fail_closed": True,
            }
        cur = req.get("decision") or get_decision(decision_id) or cur
    elif str(cur.get("state")) != "advice_requested":
        return {"ok": False, "error": "bad_state", "state": cur.get("state")}

    tenant_id = str(cur.get("tenant_id") or "")
    sha = str(cur.get("content_sha256") or "")
    q = (query or f"{cur.get('decision_type')} {cur.get('title')} {tenant_id}").strip()

    fetched = _fetch_second_brain_advice(
        query=q, tenant_id=tenant_id, content_sha256=sha, use_council=use_council
    )
    if not fetched.get("ok"):
        _transition(
            decision_id,
            "refused",
            {"refuse_reason": fetched.get("error") or "advice_unavailable", "advice": None},
        )
        return {
            "ok": False,
            "error": fetched.get("error") or "advice_unavailable",
            "fail_closed": True,
        }
    advice = dict(fetched.get("advice") or {})

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
    prov_err = _validate_note_tenant_provenance(list(advice.get("notes") or []), tenant_id)
    if prov_err:
        _transition(decision_id, "refused", {"refuse_reason": prov_err})
        return {"ok": False, "error": prov_err, "fail_closed": True}
    try:
        recorded = datetime.fromisoformat(
            str(advice.get("recorded_at") or "").replace("Z", "+00:00")
        )
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        age = (_now() - recorded).total_seconds()
        if age < -_ADVICE_FUTURE_SKEW_S:
            _transition(decision_id, "refused", {"refuse_reason": "advice_future_timestamp"})
            return {"ok": False, "error": "advice_future_timestamp", "fail_closed": True}
        if age > _ADVICE_MAX_AGE_S:
            _transition(decision_id, "refused", {"refuse_reason": "advice_stale"})
            return {"ok": False, "error": "advice_stale", "fail_closed": True}
    except Exception:
        _transition(decision_id, "refused", {"refuse_reason": "advice_malformed_ts"})
        return {"ok": False, "error": "advice_malformed", "fail_closed": True}

    return _transition(decision_id, "advice_recorded", {"advice": advice})


def boss_review_decision(
    decision_id: str,
    *,
    reviewer_id: str = _BOSS_ID,
    verdict: str = "proceed",
    reason: str = "",
    authority_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not enabled():
        return {"ok": True, "inert": True, "flag": _FLAG}
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) != "advice_recorded":
        return {"ok": False, "error": "advice_required_before_review", "state": cur.get("state")}
    auth = verify_boss_authority(
        decision_id=decision_id,
        content_sha256=str(cur.get("content_sha256") or ""),
        evidence=authority_evidence,
    )
    if not auth.get("ok"):
        return auth
    reviewer_id = str(auth.get("actor_id") or _BOSS_ID)
    # Spoofed request reviewer_id must not override authenticated identity
    review = {
        "by": reviewer_id,
        "verdict": (verdict or "proceed")[:40],
        "reason": (reason or "")[:200],
        "at": _now_iso(),
        "bound_content_sha256": cur.get("content_sha256"),
        "authority_via": auth.get("via"),
    }
    return _transition(decision_id, "boss_reviewed", {"boss_review": review})


def boss_approve(
    decision_id: str,
    *,
    actor_id: str = _BOSS_ID,
    expected_sha256: str = "",
    owner_decision_id: str | None = None,
    authority_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """GREEN Boss approve after advice+review. AMBER needs verified Owner OS decision."""
    if not enabled():
        return {"ok": True, "inert": True, "flag": _FLAG}
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    lane = str(cur.get("lane") or "")
    state = str(cur.get("state") or "")

    if expected_sha256 and expected_sha256 != cur.get("content_sha256"):
        return {"ok": False, "error": "stale_hash", "fail_closed": True}
    if cur.get("consumed"):
        return {"ok": False, "error": "replay_rejected", "fail_closed": True}

    auth = verify_boss_authority(
        decision_id=decision_id,
        content_sha256=str(cur.get("content_sha256") or ""),
        evidence=authority_evidence,
    )
    if not auth.get("ok"):
        # Spoofed actor_id="manager" without evidence must fail
        return auth
    actor_id = str(auth.get("actor_id") or _BOSS_ID)

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
        verified = verify_and_consume_owner_decision(
            oid,
            tenant_id=str(cur.get("tenant_id") or ""),
            agent_id=str(cur.get("agent_id") or ""),
            decision_type=str(cur.get("decision_type") or ""),
            content_sha256=str(cur.get("content_sha256") or ""),
            decision_id=decision_id,
            lane=lane,
        )
        if not verified.get("ok"):
            return verified
        return _transition(
            decision_id,
            "boss_approved",
            {
                "owner_decision_id": oid,
                "approved_by": actor_id,
                "approved_at": _now_iso(),
                "authority_via": auth.get("via"),
                "owner_verified": True,
            },
        )

    # GREEN — needs_owner still requires verified one-time Owner OS binding
    if state == "needs_owner":
        oid = (owner_decision_id or cur.get("owner_decision_id") or "").strip()
        if not oid:
            return {"ok": False, "error": "owner_decision_id_required"}
        verified = verify_and_consume_owner_decision(
            oid,
            tenant_id=str(cur.get("tenant_id") or ""),
            agent_id=str(cur.get("agent_id") or ""),
            decision_type=str(cur.get("decision_type") or ""),
            content_sha256=str(cur.get("content_sha256") or ""),
            decision_id=decision_id,
            lane=lane or "GREEN",
        )
        if not verified.get("ok"):
            return verified
        return _transition(
            decision_id,
            "boss_approved",
            {
                "owner_decision_id": oid,
                "approved_by": actor_id,
                "approved_at": _now_iso(),
                "authority_via": auth.get("via"),
                "owner_verified": True,
            },
        )

    if actor_id != _BOSS_ID:
        return {"ok": False, "error": "boss_or_owner_required"}

    return _transition(
        decision_id,
        "boss_approved",
        {
            "approved_by": actor_id,
            "approved_at": _now_iso(),
            "owner_decision_id": owner_decision_id or cur.get("owner_decision_id"),
            "authority_via": auth.get("via"),
        },
    )


def boss_reject(
    decision_id: str,
    *,
    actor_id: str = _BOSS_ID,
    reason: str = "",
    authority_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not enabled():
        return {"ok": True, "inert": True, "flag": _FLAG}
    cur = get_decision(decision_id)
    if not cur:
        return {"ok": False, "error": "not_found"}
    if str(cur.get("state")) not in ("boss_reviewed", "needs_owner", "advice_recorded"):
        return {"ok": False, "error": "bad_state", "state": cur.get("state")}
    auth = verify_boss_authority(
        decision_id=decision_id,
        content_sha256=str(cur.get("content_sha256") or ""),
        evidence=authority_evidence,
    )
    if not auth.get("ok"):
        return auth
    actor_id = str(auth.get("actor_id") or _BOSS_ID)
    # from advice_recorded, must pass boss_reviewed first for reject? Allow reject from reviewed/needs_owner.
    if str(cur.get("state")) == "advice_recorded":
        br = boss_review_decision(
            decision_id,
            reviewer_id=actor_id,
            verdict="reject",
            reason=reason,
            authority_evidence=authority_evidence,
        )
        if not br.get("ok"):
            return br
    return _transition(
        decision_id,
        "boss_rejected",
        {
            "rejected_by": actor_id,
            "reject_reason": (reason or "")[:200],
            "authority_via": auth.get("via"),
        },
    )


def mark_needs_owner(decision_id: str, *, owner_decision_id: str = "") -> dict[str, Any]:
    if not enabled():
        return {"ok": True, "inert": True, "flag": _FLAG}
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
    """One-time consume with cross-process CAS. Requires boss_approved + hash match."""
    if not enabled():
        return {
            "ok": False,
            "error": "flag_off",
            "flag": _FLAG,
            "fail_closed": True,
            "note": "Governance execute path INERT until BOSS_DECISION_GOVERNANCE=1",
        }
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

    # Cross-process one-time consume claim BEFORE ledger transition
    if not _atomic_claim(f"consume:{decision_id}"):
        return {"ok": False, "error": "replay_rejected", "fail_closed": True, "cas": True}

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
                mirror = approvals_bridge.decide(
                    "owner_os_verification",
                    vid,
                    "approve",
                    by=actor_id,
                    reason="governed_consume",
                )
                if not isinstance(mirror, dict) or not mirror.get("ok"):
                    logger.error(
                        "[boss_gov] consume audit mirror failed decision_id=%s",
                        decision_id,
                    )
                    out["ok"] = False
                    out["error"] = "audit_mirror_failed"
                    out["fail_closed"] = True
                    out["audit_mirror_ok"] = False
                else:
                    out["audit_mirror_ok"] = True
        except Exception as e:
            logger.error("[boss_gov] consume audit mirror exception: %s", type(e).__name__)
            out["ok"] = False
            out["error"] = "audit_mirror_failed"
            out["fail_closed"] = True
            out["audit_mirror_ok"] = False
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


def owner_os_decide_governed(
    decision_id: str,
    *,
    decision: str,
    actor: str = "admin",
    reason: str = "",
    expected_sha256: str = "",
) -> dict[str, Any]:
    """Real Owner OS consumer for hash-bound governed decisions.

    Flag OFF → fail-closed refuse (existing non-governed paths untouched).
    Approve on ``needs_owner``: create bound verification → stamp approve →
    ``boss_approve`` → one-time ``consume`` (no customer/prod side effects).
    Reject: Owner refuse transition (not spoofed Boss authority).
    """
    if not enabled():
        return {
            "ok": False,
            "error": "flag_off",
            "flag": _FLAG,
            "fail_closed": True,
            "inert": True,
            "note": "Governed execute path INERT until BOSS_DECISION_GOVERNANCE=1",
        }
    did = (decision_id or "").strip()
    verdict = (decision or "").strip().lower()
    if verdict == "request_changes":
        verdict = "reject"
        reason = (reason or "request_changes").strip() or "request_changes"
    if verdict not in ("approve", "reject"):
        return {"ok": False, "error": "decision must be approve|reject", "fail_closed": True}
    cur = get_decision(did)
    if not cur:
        return {"ok": False, "error": "not_found", "fail_closed": True}
    sha = str(cur.get("content_sha256") or "")
    if expected_sha256 and expected_sha256 != sha:
        return {"ok": False, "error": "stale_hash", "fail_closed": True}
    if str(cur.get("decision_type") or "") in _OWNER_ONLY_TYPES:
        return {"ok": False, "error": "upi_owner_only", "fail_closed": True}
    if str(cur.get("lane") or "") == "RED":
        return {"ok": False, "error": "red_lane_owner_refuse_only", "fail_closed": True}
    state = str(cur.get("state") or "")

    if verdict == "reject":
        if state not in ("needs_owner", "boss_reviewed", "advice_recorded", "boss_approved"):
            return {"ok": False, "error": "bad_state", "state": state, "fail_closed": True}
        return _transition(
            did,
            "refused",
            {
                "refuse_reason": (reason or "owner_rejected")[:200],
                "refused_by": (actor or "admin")[:80],
                "owner_os": True,
            },
        )

    # approve
    if state == "boss_approved":
        return consume_or_execute(
            did, expected_sha256=sha or expected_sha256, mode="consume", actor_id=actor
        )
    if state != "needs_owner":
        return {
            "ok": False,
            "error": "not_decidable_here",
            "state": state,
            "fail_closed": True,
            "note": "Owner OS only decides needs_owner; Boss GREEN path stays Boss-gated.",
        }

    lane = str(cur.get("lane") or "AMBER")
    meta = {
        "content_sha256": sha,
        "tenant_id": str(cur.get("tenant_id") or ""),
        "agent_id": str(cur.get("agent_id") or ""),
        "decision_type": str(cur.get("decision_type") or ""),
        "decision_id": did,
        "lane": lane,
        "mission_id": did,
        "action": str(cur.get("decision_type") or ""),
    }
    try:
        from app.platform import approvals_bridge
    except Exception as e:
        logger.error("[boss_gov] approvals_bridge import failed: %s", type(e).__name__)
        return {"ok": False, "error": "owner_verifier_unavailable", "fail_closed": True}

    created = approvals_bridge.create_verification_approval(
        by=actor,
        title=f"Governed decision {did[:12]}",
        note="Hash-bound Owner OS gate — no customer/outbound side effects",
        meta=meta,
    )
    if not isinstance(created, dict) or not created.get("ok"):
        return {
            "ok": False,
            "error": "owner_verification_create_failed",
            "fail_closed": True,
            "detail": created if isinstance(created, dict) else None,
        }
    oid = str(created.get("id") or "").strip()
    if not oid:
        return {"ok": False, "error": "owner_verification_id_missing", "fail_closed": True}

    # Persist audit evidence (verification stamp) BEFORE consume side-effect.
    stamped = approvals_bridge.decide(
        "owner_os_verification",
        oid,
        "approve",
        by=actor,
        reason=(reason or "owner_os_governed")[:200],
    )
    if not isinstance(stamped, dict) or not stamped.get("ok"):
        return {
            "ok": False,
            "error": "owner_verification_stamp_failed",
            "fail_closed": True,
            "owner_decision_id": oid,
        }

    # Boss HMAC authority still required for the approve transition itself.
    secret = (os.getenv("BOSS_GOV_AUTHORITY_KEY") or "").strip()
    if not secret:
        return {"ok": False, "error": "authority_key_unset", "fail_closed": True}
    sig = hmac.new(secret.encode("utf-8"), f"{did}|{sha}".encode(), hashlib.sha256).hexdigest()
    approved = boss_approve(
        did,
        expected_sha256=sha,
        owner_decision_id=oid,
        authority_evidence={"kind": "hmac", "sig": sig},
    )
    if not approved.get("ok"):
        return approved

    consumed = consume_or_execute(did, expected_sha256=sha, mode="consume", actor_id=actor)
    if not consumed.get("ok"):
        return consumed
    return {
        "ok": True,
        "decision_id": did,
        "owner_decision_id": oid,
        "state": (consumed.get("decision") or {}).get("state"),
        "content_sha256": sha,
        "consumer": "owner_os_decide_governed",
        "side_effects": False,
        "note": "Consumed via hash-bound adapter; no customer/outbound mutation.",
    }


__all__ = [
    "STATES",
    "DECISION_TYPE_REGISTRY",
    "DecisionAdapter",
    "enabled",
    "content_hash",
    "classify_lane_strict",
    "routing_coverage",
    "build_adapter_registry",
    "adapter_registry",
    "adapter_propose_for_agent",
    "propose_from_hierarchical_run",
    "propose_decision",
    "request_advice",
    "record_second_brain_advice",
    "boss_review_decision",
    "boss_approve",
    "boss_reject",
    "mark_needs_owner",
    "consume_or_execute",
    "owner_os_decide_governed",
    "verify_boss_authority",
    "verify_and_consume_owner_decision",
    "get_decision",
    "list_pending",
    "owner_os_visibility",
    "buzz_ro_projection",
    "assert_aggregate_is_not_approval",
    "metrics_snapshot",
]
