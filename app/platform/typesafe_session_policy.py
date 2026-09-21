"""One bounded TypeSafe judgment per substantial orchestrator task/session.

System safety/compliance gates remain authoritative. TypeSafe may route an
otherwise-eligible task to human review, but provider failure never bypasses a
deterministic gate and never crashes dispatch.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.platform.typesafe_integration import Choice, Noul, get_typesafe_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
_TRACE = Path("logs/typesafe_session_decisions.jsonl")
_LOCK = threading.Lock()


def _enabled() -> bool:
    # Reuse the canonical integration switch. A second flag would let the
    # gateway appear armed while session governance silently stayed disabled.
    return os.getenv("TYPESAFE_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}


def _append(path: Path, row: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except Exception as exc:
        logger.warning("TypeSafe session trace write failed: %s", exc)
        return False


def judge_task(*, record: Any, contract: Any, client: Any | None = None, trace_path: Path | None = None) -> dict[str, Any]:
    """Return a compact dispatch verdict; task payload values/PII never leave."""
    decision_id = f"tss-{uuid.uuid4().hex[:12]}"
    base = {"decision_id": decision_id, "route": "proceed", "reason": "policy_disabled", "traced": False}
    if not _enabled():
        return base
    api = client or get_typesafe_client()
    if not getattr(api, "enabled", False):
        return {**base, "reason": "credential_unavailable"}
    tenant_scope = str((record.input_payload or {}).get("tenant_id") or (record.input_payload or {}).get("client_id") or "platform")
    state = {
        "task_id": record.task_id,
        "tenant_scope": tenant_scope,
        "purpose": "substantial_agent_session_dispatch",
        "owner_bot": record.owner_bot,
        "assigned_agent": record.assigned_agent,
        "agent_lane": str(getattr(contract, "lane", "")),
        "priority": str(getattr(record.priority, "value", record.priority)),
        "payload_keys": sorted(str(k) for k in (record.input_payload or {}) if not str(k).startswith("_")),
        "evidence_refs": [f"data/orchestrator_ledger.db#task_records:{record.task_id}"],
    }
    questions = {
        "route": Choice(
            "Should this governed task proceed or require owner review?",
            {
                "proceed": "Task is sufficiently scoped and safe under existing deterministic gates",
                "review": "Semantic uncertainty or business-risk merits owner review before execution",
            },
        ),
        "material": Noul("Will this task materially change a customer, revenue, or operational outcome?"),
    }
    reason = ""
    try:
        response = api.system_one(
            state,
            questions,
            connect_timeout_sec=2.0,
            read_timeout_sec=5.0,
            max_attempts=1,
        )
        response_success = bool(response.success)
        resolved_model = response.model
        answer = (response.answers or {}).get("route") or {}
        route = str(answer.get("choice") or "proceed").strip().lower()
    except Exception as exc:
        logger.warning("TypeSafe session judgment failed for %s: %s", record.task_id, type(exc).__name__)
        response_success = False
        resolved_model = None
        route = "proceed"
        reason = "provider_exception"
    if not response_success or route not in {"proceed", "review"}:
        route = "proceed"
        reason = reason if reason == "provider_exception" else "provider_fallback"
    else:
        reason = "typesafe_judgment"
    raw = json.dumps({"state": state, "questions": sorted(questions)}, sort_keys=True, default=str)
    row = {
        "kind": "session_decision",
        "decision_id": decision_id,
        "task_id": record.task_id,
        "tenant_scope": tenant_scope,
        "purpose": state["purpose"],
        "state_hash": hashlib.sha256(raw.encode()).hexdigest()[:16],
        "evidence_refs": state["evidence_refs"],
        "requested_model": getattr(api, "model", "jev-latest"),
        "resolved_model": resolved_model,
        "route": route,
        "reason": reason,
        "success": response_success,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    traced = _append(trace_path or _TRACE, row)
    return {"decision_id": decision_id, "route": route, "reason": reason, "traced": traced}


__all__ = ["judge_task"]
