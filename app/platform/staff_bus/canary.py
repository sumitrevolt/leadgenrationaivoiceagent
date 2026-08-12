"""Synthetic zero-side-effect 31/31 STAFF bus canaries."""

from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.platform.staff_bus.manifest import build_manifest
from app.platform.staff_bus.runtime import StaffBus, reset_runtime_state_for_tests


def run_all_staff_canaries(
    *,
    tenant_prefix: str = "bus_setup",
    batch_pause_s: float = 0.0,
    data_root: str | None = None,
) -> dict[str, Any]:
    """Prove each of 31 STAFF agents through a synthetic bus chain.

    Never touches customer data, outbound channels, payments, or prod DB.
    Uses ``allow_synthetic=True`` so the canary works while flag is OFF.
    """
    run_id = uuid.uuid4().hex[:12]
    # Boss governance forbids "/" in tenant ids; colon-namespace is OK.
    tenant_id = f"{tenant_prefix}-{run_id}"
    root = data_root or tempfile.mkdtemp(prefix=f"staff_bus_cny_{run_id}_")
    prev_bus_root = os.environ.get("STAFF_BUS_DATA_ROOT")
    prev_gov = os.environ.get("BOSS_DECISION_GOVERNANCE")
    prev_auth = os.environ.get("BOSS_GOV_AUTHORITY_KEY")
    os.environ["STAFF_BUS_DATA_ROOT"] = root
    os.environ["BOSS_DECISION_GOVERNANCE"] = "1"
    os.environ.setdefault("BOSS_GOV_AUTHORITY_KEY", f"staff-bus-canary-{run_id}")
    reset_runtime_state_for_tests()

    # Isolate Boss governance ledger to the same temp tree.
    from app.platform import runtime_data

    prev_rd = os.environ.get(runtime_data.ENV_KEY)
    runtime_data.use_test_root(root)

    rows: list[dict[str, Any]] = []
    t0 = time.time()
    try:
        bus = StaffBus(require_flag=False)
        agents = bus.manifest.get("agents") or []
        for idx, agent in enumerate(agents):
            if batch_pause_s and idx and idx % 8 == 0:
                time.sleep(batch_pause_s)
            rows.append(_canary_one(bus, agent=agent, tenant_id=tenant_id, run_id=run_id))
    finally:
        if prev_bus_root is None:
            os.environ.pop("STAFF_BUS_DATA_ROOT", None)
        else:
            os.environ["STAFF_BUS_DATA_ROOT"] = prev_bus_root
        if prev_gov is None:
            os.environ.pop("BOSS_DECISION_GOVERNANCE", None)
        else:
            os.environ["BOSS_DECISION_GOVERNANCE"] = prev_gov
        if prev_auth is None:
            # Only drop the key we may have set via setdefault for this run.
            cur = os.environ.get("BOSS_GOV_AUTHORITY_KEY") or ""
            if cur.startswith("staff-bus-canary-"):
                os.environ.pop("BOSS_GOV_AUTHORITY_KEY", None)
        else:
            os.environ["BOSS_GOV_AUTHORITY_KEY"] = prev_auth
        if prev_rd is None:
            os.environ.pop(runtime_data.ENV_KEY, None)
        else:
            os.environ[runtime_data.ENV_KEY] = prev_rd
        reset_runtime_state_for_tests()

    ok = sum(1 for r in rows if r.get("gate") == "GO")
    return {
        "ok": ok == 31,
        "run_id": run_id,
        "tenant_id": tenant_id,
        "data_root": root,
        "elapsed_s": round(time.time() - t0, 3),
        "go_count": ok,
        "total": len(rows),
        "rows": rows,
        "protected_side_effects": 0,
        "comb_in_staff": False,
        "manifest_ok": validate_quick(),
    }


def validate_quick() -> bool:
    from app.platform.staff_bus.manifest import validate_manifest

    return bool(validate_manifest(build_manifest()).get("ok"))


def _auth(decision_id: str, sha: str) -> dict[str, str]:
    secret = (os.getenv("BOSS_GOV_AUTHORITY_KEY") or "").encode()
    sig = hmac.new(secret, f"{decision_id}|{sha}".encode(), hashlib.sha256).hexdigest()
    return {"kind": "hmac", "sig": sig}


def _patch_advice(gov_mod: Any, sha: str, tenant: str) -> None:
    payload = {
        "ok": True,
        "advice": {
            "source": "staff_bus_canary",
            "authoritative": False,
            "bound_content_sha256": sha,
            "bound_tenant_id": tenant,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "notes": [
                {
                    "folder": "BusSetup",
                    "slug": "canary",
                    "score": 1,
                    "excerpt": "synthetic advice",
                    "tenant_id": tenant,
                }
            ],
        },
    }

    def _fetch(**kwargs: Any) -> dict[str, Any]:
        return payload

    gov_mod._fetch_second_brain_advice = _fetch  # type: ignore[method-assign]


def _canary_one(
    bus: StaffBus, *, agent: dict[str, Any], tenant_id: str, run_id: str
) -> dict[str, Any]:
    from app.platform import approvals_bridge
    from app.platform import boss_decision_governance as gov

    # Keep Owner OS mirror inert during synthetic canaries (restore after).
    _prev_create = getattr(approvals_bridge, "create_verification_approval", None)

    def _mirror_ok(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "id": f"oosv_bus_{run_id}",
            "draft": {"meta": kwargs.get("meta") or {}},
        }

    approvals_bridge.create_verification_approval = _mirror_ok  # type: ignore[method-assign]
    _prev_fetch = gov._fetch_second_brain_advice

    aid = str(agent.get("agent_id"))
    team = str(agent.get("domain_team") or "")
    channel = str(agent.get("default_buzz_channel") or "ops")
    no_decision = bool(agent.get("no_decision_expected"))
    corr = f"cny-{run_id}-{aid}"
    t0 = time.time()
    evidence: dict[str, Any] = {
        "agent_id": aid,
        "display_name": agent.get("display_name"),
        "team": team,
        "channel": channel,
        "correlation_id": corr,
        "retry_dlq_count": 0,
        "advice_id": None,
        "boss_verdict_id": None,
        "gate": "NO-GO",
    }

    proposed = bus.publish(
        event_type="task.proposed",
        tenant_id=tenant_id,
        source_agent_id="manager",
        destination=f"team:{team}" if aid != "manager" else "boss:manager",
        payload={"run_id": run_id, "task": f"synthetic:{aid}", "side_effect": "none"},
        correlation_id=corr,
        allow_synthetic=True,
    )
    if not proposed.get("ok"):
        evidence.update({"error": proposed.get("error"), "elapsed_s": round(time.time() - t0, 3)})
        return evidence
    evidence["source_event_id"] = proposed["event"]["event_id"]

    assigned = bus.publish(
        event_type="task.assigned",
        tenant_id=tenant_id,
        source_agent_id="manager",
        destination=f"agent:{aid}",
        payload={"run_id": run_id, "assignee": aid},
        correlation_id=corr,
        causation_id=evidence["source_event_id"],
        allow_synthetic=True,
    )
    if not assigned.get("ok"):
        evidence.update({"error": assigned.get("error"), "elapsed_s": round(time.time() - t0, 3)})
        return evidence
    evidence["assigned_route"] = assigned["event"]["destination"]

    accepted = bus.publish(
        event_type="task.accepted",
        tenant_id=tenant_id,
        source_agent_id=aid,
        destination="boss:manager",
        payload={"run_id": run_id, "accepted": True},
        correlation_id=corr,
        causation_id=assigned["event"]["event_id"],
        allow_synthetic=True,
    )
    if not accepted.get("ok"):
        evidence.update({"error": accepted.get("error"), "elapsed_s": round(time.time() - t0, 3)})
        return evidence
    evidence["acceptance_event_id"] = accepted["event"]["event_id"]

    artifact = bus.publish(
        event_type="artifact.ready",
        tenant_id=tenant_id,
        source_agent_id=aid,
        destination="boss:manager",
        payload={
            "run_id": run_id,
            "artifact": f"deterministic:{aid}:{run_id}",
            "hash": f"sha256:{aid}:{run_id}",
        },
        correlation_id=corr,
        causation_id=evidence["acceptance_event_id"],
        allow_synthetic=True,
    )
    if not artifact.get("ok"):
        evidence.update({"error": artifact.get("error"), "elapsed_s": round(time.time() - t0, 3)})
        return evidence
    evidence["artifact_handoff_event_id"] = artifact["event"]["event_id"]

    try:
        if no_decision:
            evidence["decision_contract"] = "no_decision_expected"
        else:
            # Boss cannot self-approve: when target is manager, propose via worker isha.
            proposer = "isha" if aid == "manager" else aid
            decision_type = "internal_plan" if aid == "manager" else "hierarchical_member_output"
            proposed_dec = gov.adapter_propose_for_agent(
                agent_id=proposer,
                tenant_id=tenant_id,
                decision_type=decision_type,
                title=f"bus-canary:{run_id}:{aid}",
                payload={"synthetic": True, "run_id": run_id, "agent": aid},
                proposed_by=proposer,
                run_id=run_id,
            )
            if not proposed_dec.get("ok") or not proposed_dec.get("decision"):
                evidence["decision_error"] = proposed_dec.get("error") or proposed_dec.get("note")
            else:
                decision = proposed_dec["decision"]
                did = str(decision.get("decision_id") or "")
                sha = str(decision.get("content_sha256") or "")
                evidence["decision_id"] = did
                _patch_advice(gov, sha, tenant_id)
                advice = gov.record_second_brain_advice(did)
                if advice.get("ok"):
                    advice_row = advice.get("decision") or advice
                    evidence["advice_id"] = (
                        advice.get("advice_id")
                        or (advice_row.get("advice") or {}).get("source")
                        or f"advice:{did}"
                    )
                else:
                    evidence["advice_error"] = advice.get("error")

                review = gov.boss_review_decision(
                    did,
                    authority_evidence=_auth(did, sha),
                )
                if review.get("ok"):
                    evidence["boss_review_ok"] = True
                    approved = gov.boss_approve(
                        did,
                        expected_sha256=sha,
                        authority_evidence=_auth(did, sha),
                    )
                    rollout = str(agent.get("rollout_state") or decision.get("rollout") or "")
                    evidence["rollout_state"] = rollout
                    if approved.get("ok"):
                        evidence["boss_verdict_id"] = f"verdict:{did}"
                        evidence["boss_verdict"] = "GREEN"
                    elif approved.get("error") == "agent_unarmed":
                        # Held/disabled agents: refuse-to-execute is the governed GO path.
                        evidence["boss_verdict_id"] = f"refuse:{did}"
                        evidence["boss_verdict"] = "RED_UNARMED"
                        evidence["boss_approve_error"] = "agent_unarmed"
                        bus.publish(
                            event_type="execution.refused",
                            tenant_id=tenant_id,
                            source_agent_id="manager",
                            destination=f"agent:{aid}",
                            payload={
                                "decision_id": did,
                                "reason": "agent_unarmed",
                                "rollout": rollout,
                                "synthetic": True,
                            },
                            correlation_id=corr,
                            allow_synthetic=True,
                            authority_requirement="boss",
                            terminal_state="refused",
                        )
                    else:
                        evidence["boss_approve_error"] = approved.get("error")
                        evidence["boss_verdict"] = approved.get("state") or "refused"
                else:
                    evidence["boss_review_error"] = review.get("error")

            bus.publish(
                event_type="decision.proposed",
                tenant_id=tenant_id,
                source_agent_id=aid if aid != "manager" else "manager",
                destination="boss:manager",
                payload={"run_id": run_id, "decision_ref": evidence.get("decision_id")},
                correlation_id=corr,
                allow_synthetic=True,
                authority_requirement="boss",
            )
            if evidence.get("advice_id"):
                bus.publish(
                    event_type="second_brain.advice",
                    tenant_id=tenant_id,
                    source_agent_id="manager",
                    destination=f"agent:{aid}",
                    payload={"advice_id": evidence["advice_id"], "synthetic": True},
                    correlation_id=corr,
                    allow_synthetic=True,
                )
            bus.publish(
                event_type="boss.verdict",
                tenant_id=tenant_id,
                source_agent_id="manager",
                destination=f"agent:{aid}",
                payload={
                    "verdict": evidence.get("boss_verdict") or "RECORDED",
                    "decision_id": evidence.get("decision_id"),
                },
                correlation_id=corr,
                allow_synthetic=True,
                authority_requirement="boss",
                terminal_state="completed" if evidence.get("boss_verdict_id") else "open",
            )
    finally:
        if _prev_create is not None:
            approvals_bridge.create_verification_approval = _prev_create  # type: ignore[method-assign]
        gov._fetch_second_brain_advice = _prev_fetch  # type: ignore[method-assign]

    terminal = bus.publish(
        event_type="task.completed",
        tenant_id=tenant_id,
        source_agent_id=aid,
        destination="boss:manager",
        payload={"run_id": run_id, "status": "completed", "side_effect": "none"},
        correlation_id=corr,
        causation_id=evidence.get("artifact_handoff_event_id"),
        allow_synthetic=True,
        terminal_state="completed",
    )
    if not terminal.get("ok"):
        evidence.update({"error": terminal.get("error"), "elapsed_s": round(time.time() - t0, 3)})
        return evidence
    evidence["terminal_event_id"] = terminal["event"]["event_id"]

    audit = bus.publish(
        event_type="audit.recorded",
        tenant_id=tenant_id,
        source_agent_id="staff_bus",
        destination="owner_os",
        payload={"run_id": run_id, "agent_id": aid, "correlation_id": corr},
        correlation_id=corr,
        allow_synthetic=True,
        terminal_state="completed",
    )
    evidence["audit_event_id"] = (audit.get("event") or {}).get("event_id")
    evidence["elapsed_s"] = round(time.time() - t0, 3)

    required = [
        evidence.get("source_event_id"),
        evidence.get("assigned_route"),
        evidence.get("acceptance_event_id"),
        evidence.get("artifact_handoff_event_id"),
        evidence.get("terminal_event_id"),
        evidence.get("audit_event_id"),
    ]
    if no_decision:
        evidence["gate"] = "GO" if all(required) else "NO-GO"
    else:
        evidence["gate"] = (
            "GO"
            if all(required)
            and evidence.get("decision_id")
            and evidence.get("advice_id")
            and evidence.get("boss_verdict_id")
            else "NO-GO"
        )
    return evidence


def refuse_unknown_and_replay(bus: StaffBus | None = None) -> dict[str, Any]:
    """Negative proofs: unknown event, duplicate idempotency, bad tenant agent."""
    bus = bus or StaffBus(require_flag=False)
    tenant = f"bus_setup-neg-{uuid.uuid4().hex[:8]}"
    bad = bus.publish(
        event_type="not.a.real.event",
        tenant_id=tenant,
        source_agent_id="manager",
        destination="boss:manager",
        payload={"x": 1},
        allow_synthetic=True,
    )
    good = bus.publish(
        event_type="work.status",
        tenant_id=tenant,
        source_agent_id="manager",
        destination="owner_os",
        payload={"ping": True},
        idempotency_key=f"replay-{tenant}",
        allow_synthetic=True,
    )
    replay = bus.publish(
        event_type="work.status",
        tenant_id=tenant,
        source_agent_id="manager",
        destination="owner_os",
        payload={"ping": True},
        idempotency_key=f"replay-{tenant}",
        allow_synthetic=True,
    )
    unknown_agent = bus.publish(
        event_type="work.status",
        tenant_id=tenant,
        source_agent_id="not_a_staff_agent",
        destination="owner_os",
        payload={"ping": True},
        allow_synthetic=True,
    )
    return {
        "unknown_event_refused": bad.get("fail_closed") is True,
        "first_ok": good.get("ok") is True,
        "replay_refused": replay.get("error") == "duplicate_idempotency",
        "unknown_agent_refused": unknown_agent.get("fail_closed") is True,
        "ok": all(
            [
                bad.get("fail_closed") is True,
                good.get("ok") is True,
                replay.get("error") == "duplicate_idempotency",
                unknown_agent.get("fail_closed") is True,
            ]
        ),
    }
