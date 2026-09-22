"""TypeSafe multi-pass consumer (M00A + ADR-200).

Wraps the canonical TypeSafe client (`app.platform.typesafe_integration`) with
a deterministic 8-stage lifecycle that any governed worker, agent or session
can inherit:

    intake → plan → generate (host) → intermediate_qa → revise → final_qa → outcome → session

Each stage that calls TypeSafe:
  - emits a `MultipassTraceRecord` (decision_id, task_id, stage, primitive,
    model, state_hash, evidence_refs, latency_sec, result_kind, value,
    confidence, downstream_action, side_effect_id, observed_outcome, ts).
  - is REAL when the canonical credential_state() reports PRESENT
    (`TYPESAFE_API_KEY` configured and not in the COMPROMISED set).
  - is a deterministic MOCK (based on SHA-256 of normalized inputs) when
    ABSENT, so tests + ABSENT-credential local runs are reproducible.
  - is SKIPPED with `value=None, confidence=0.5` when the caller passes
    `enabled=False` or the stage is excluded by stage_filter.

Generation (the actual artifact: code, copy, email, call summary) is performed
by the host (MiniMax-M3 + tools), NOT by TypeSafe. TypeSafe only provides the
semantic judgment at decision points where additional evaluation materially
improves the result.

Exempt / non-applicable calls (per M00A):
  - greetings, exact arithmetic, rote status reads, deterministic gates
    (RED/HARD_OFF/frozen/compliance, permission, exact schema).
  - identical input over a single session is reused (`cache_window_sec`) —
    not a separate "duplicate call" metric; the cached response is reused
    with the original record's decision_id.

Cache key: (task_id, stage, primitive, SHA-256 of normalized state+questions).
TTL: `cache_window_sec` (default 300 s).

The module DOES NOT duplicate the canonical client. All real HTTP traffic
flows through `app.platform.typesafe_integration.typesafe_*`. No duplicate
secret store, no duplicate SDK, no second key pool.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping

from app.platform import typesafe_integration as _ts

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- #
# Trace record                                                                  #
# ----------------------------------------------------------------------------- #


@dataclass
class MultipassTraceRecord:
    """One consumed TypeSafe call. NEVER carries the API key, only its sha256
    fingerprint and the canonical model id."""

    decision_id: str
    task_id: str
    stage: str
    primitive: str
    model: str
    state_hash: str
    evidence_refs: list[str]
    request_latency_sec: float
    result_kind: str  # "real" | "mock" | "cached" | "skipped"
    value: Any | None
    confidence: float
    downstream_action: str | None = None
    side_effect_id: str | None = None
    observed_outcome: Any | None = None
    timestamp: str = ""
    # Audit-only fingerprint of the credential that armed the call. The key
    # itself is NEVER stored. EMPTY for ABSENT/mock/cached paths.
    credential_fingerprint: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- #
# Mocked answer (deterministic, no network)                                     #
# ----------------------------------------------------------------------------- #


def _stable_mock_value(
    primitive: str,
    stage: str,
    state: Mapping[str, Any],
    questions: Mapping[str, Any],
    default_value: Any,
) -> tuple[Any, float]:
    """Deterministic mock. Same input -> same answer; confidence carries a
    placeholder 0.5 to make "no real judgment" obvious to downstream readers.

    Hashing: SHA-256 over canonical JSON of {primitive, stage, normalized
    state+questions}, take 8 hex chars, map to a value from the question's
    criteria (Choice/Score) or flip Noul deterministically.
    """
    canonical = json.dumps(
        {
            "primitive": primitive,
            "stage": stage,
            "state": _normalize(state),
            "questions": _normalize(questions),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    # Pull a single hex digit for primitive selection
    bucket = int(h[:2], 16)
    if primitive == "Noul":
        # mock answer flips based on parity of bucket
        return bool(bucket % 2), 0.5
    # Choice / Score
    criteria = _extract_criteria_values(questions, default_value)
    if isinstance(criteria, list) and criteria:
        return criteria[bucket % len(criteria)], 0.5
    return default_value, 0.5


def _normalize(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {str(k): _normalize(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def _extract_criteria_values(questions: Mapping[str, Any], default: Any) -> list[Any] | Any:
    """Pull criteria from the first question if it looks like a Choice/Score."""
    for q in questions.values():
        crit = getattr(q, "criteria", None)
        if isinstance(crit, dict) and crit:
            return list(crit.values())
        if isinstance(crit, (list, tuple)) and crit:
            return list(crit)
    return default


# ----------------------------------------------------------------------------- #
# Multi-pass consumer                                                           #
# ----------------------------------------------------------------------------- #


# Default schema path (also reflected in AGENTS.md §2.2)
MULTIPASS_SCHEMA_VERSION = "m00a-2026-09-22"


@dataclass
class MultipassConsumer:
    """8-stage multi-pass consumer.

    Stage methods:
      intake_pass(evidence, task) -> record
      plan_pass(task, options, evidence_refs) -> record
      qa_pass(artifact, stage_label="intermediate_qa", evidence_refs) -> record
      final_pass(artifact, downstream_action, evidence_refs) -> record
      outcome_pass(side_effect_id, observed_outcome) -> record

    Each method returns a `MultipassTraceRecord` (always; SKIPPED records are
    still emitted so audit consumers can see the lifecycle was honored).
    """

    task_id: str
    tenant_scope: str = "default"
    enabled: bool = True
    cache_window_sec: int = 300
    schema_version: str = MULTIPASS_SCHEMA_VERSION
    # Optional in-memory cache; cleared after each consumer goes out of scope.
    _cache: dict[str, tuple[float, MultipassTraceRecord]] = field(default_factory=dict)
    consumed_calls: list[MultipassTraceRecord] = field(default_factory=list)

    # ---- private helpers ---- #

    def _state_hash(self, state: Mapping[str, Any], questions: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            {"state": _normalize(state), "questions": _normalize(questions)},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def _cache_key(self, stage: str, primitive: str, state: Mapping[str, Any], questions: Mapping[str, Any]) -> str:
        return self._state_hash({"stage": stage, "primitive": primitive, **state}, questions)

    def _emit(
        self,
        *,
        stage: str,
        primitive: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Any],
        evidence_refs: list[str],
        downstream_action: str | None = None,
        side_effect_id: str | None = None,
        observed_outcome: Any = None,
    ) -> MultipassTraceRecord:
        if not self.enabled:
            rec = MultipassTraceRecord(
                decision_id=str(uuid.uuid4()),
                task_id=self.task_id,
                stage=stage,
                primitive=primitive,
                model=os.getenv("TYPESAFE_MODEL") or _ts._DEFAULT_MODEL,
                state_hash=self._state_hash(state, questions),
                evidence_refs=list(evidence_refs),
                request_latency_sec=0.0,
                result_kind="skipped",
                value=None,
                confidence=0.5,
                downstream_action=downstream_action,
                side_effect_id=side_effect_id,
                observed_outcome=observed_outcome,
                timestamp=_now_iso(),
            )
            self.consumed_calls.append(rec)
            return rec

        key = self._cache_key(stage, primitive, state, questions)
        cached = self._cache.get(key)
        if cached and (time.time() - cached[0]) <= self.cache_window_sec:
            rec = MultipassTraceRecord(
                decision_id=cached[1].decision_id,
                task_id=self.task_id,
                stage=stage,
                primitive=primitive,
                model=cached[1].model,
                state_hash=cached[1].state_hash,
                evidence_refs=list(evidence_refs),
                request_latency_sec=0.0,
                result_kind="cached",
                value=cached[1].value,
                confidence=cached[1].confidence,
                downstream_action=downstream_action,
                side_effect_id=side_effect_id,
                observed_outcome=observed_outcome,
                timestamp=_now_iso(),
                credential_fingerprint=cached[1].credential_fingerprint,
            )
            self.consumed_calls.append(rec)
            return rec

        cred = _ts.credential_state()
        model = cred.get("model") or _ts._DEFAULT_MODEL
        fingerprint = cred.get("fingerprint") or ""

        if cred.get("state") == "PRESENT":
            value, confidence, latency, error = self._call_real(primitive, state, questions)
            rec = MultipassTraceRecord(
                decision_id=str(uuid.uuid4()),
                task_id=self.task_id,
                stage=stage,
                primitive=primitive,
                model=model,
                state_hash=self._state_hash(state, questions),
                evidence_refs=list(evidence_refs),
                request_latency_sec=latency,
                result_kind="real",
                value=value,
                confidence=confidence,
                downstream_action=downstream_action,
                side_effect_id=side_effect_id,
                observed_outcome=observed_outcome,
                timestamp=_now_iso(),
                credential_fingerprint=fingerprint,
                error=error,
            )
            self._cache[key] = (time.time(), rec)
            self.consumed_calls.append(rec)
            return rec

        # ABSENT -> deterministic mock. Same input -> same answer.
        default_value = self._mock_default_for(stage, primitive, state)
        value, confidence = _stable_mock_value(primitive, stage, state, questions, default_value)
        rec = MultipassTraceRecord(
            decision_id=str(uuid.uuid4()),
            task_id=self.task_id,
            stage=stage,
            primitive=primitive,
            model=model,
            state_hash=self._state_hash(state, questions),
            evidence_refs=list(evidence_refs),
            request_latency_sec=0.0,
            result_kind="mock",
            value=value,
            confidence=confidence,
            downstream_action=downstream_action,
            side_effect_id=side_effect_id,
            observed_outcome=observed_outcome,
            timestamp=_now_iso(),
            credential_fingerprint="",
        )
        self._cache[key] = (time.time(), rec)
        self.consumed_calls.append(rec)
        return rec

    def _call_real(
        self,
        primitive: str,
        state: Mapping[str, Any],
        questions: Mapping[str, Any],
    ) -> tuple[Any, float, float, str | None]:
        """Single real TypeSafe call through the canonical client. Only runs
        when credential_state() == PRESENT. Returns (value, confidence,
        latency_sec, error_or_None)."""
        t0 = time.time()
        try:
            qmap: dict[str, _ts.Choice | _ts.Noul | _ts.Score] = {}
            for name, q in questions.items():
                if isinstance(q, (_ts.Choice, _ts.Noul, _ts.Score)):
                    qmap[name] = q
                elif isinstance(q, dict):
                    # map {type, instructions, criteria} into Choice/Noul/Score
                    qtype = str(q.get("type", "")).lower()
                    if qtype == "noul":
                        qmap[name] = _ts.Noul(q.get("instructions") or name)
                    elif qtype == "score":
                        qmap[name] = _ts.Score(q.get("instructions") or name, criteria=q.get("criteria") or [])
                    else:
                        qmap[name] = _ts.Choice(q.get("instructions") or name, criteria=q.get("criteria") or [])
                else:
                    qmap[name] = _ts.Choice(str(q), criteria=["yes", "no"])
            resp = _ts.typesafe_system_one(dict(state), qmap)
            latency = time.time() - t0
            if not resp.success:
                return None, 0.5, latency, resp.error or "unknown error"
            return resp.value, resp.confidence, latency, None
        except Exception as e:  # pragma: no cover - defensive
            return None, 0.5, time.time() - t0, f"{type(e).__name__}: {e}"

    def _mock_default_for(self, stage: str, primitive: str, state: Mapping[str, Any]) -> Any:
        if primitive == "Noul":
            return True
        # Choice / Score: pick a reasonable default per stage
        if stage == "intake":
            return "proceed"
        if stage == "plan":
            return "next_action"
        if stage.startswith("qa"):
            return "approve"
        if stage == "final":
            return "ready"
        if stage == "outcome":
            return "ok"
        return "default"

    # ---- public stages ---- #

    def intake_pass(
        self,
        evidence: Mapping[str, Any],
        task: str,
        evidence_refs: list[str] | None = None,
    ) -> MultipassTraceRecord:
        """Stage 1 — evidence sufficiency + task fit assessment."""
        state = {"stage": "intake", "task": task, "tenant_scope": self.tenant_scope}
        questions = {
            "fit": _ts.Choice(
                question="Is the task well-scoped given the evidence?",
                criteria=["proceed", "request_more_evidence", "abstain"],
            )
        }
        return self._emit(
            stage="intake",
            primitive="Choice",
            state={**state, "evidence_size": _approx_evidence_size(evidence)},
            questions=questions,
            evidence_refs=evidence_refs or [],
        )

    def plan_pass(
        self,
        task: str,
        options: list[str],
        evidence_refs: list[str] | None = None,
    ) -> MultipassTraceRecord:
        """Stage 2 — pick the next-best eligible action from a small option set."""
        state = {"stage": "plan", "task": task, "tenant_scope": self.tenant_scope}
        questions = {
            "next_action": _ts.Choice(
                question="Which option should the host execute next?",
                criteria=options or ["next_action"],
            )
        }
        return self._emit(
            stage="plan",
            primitive="Choice",
            state=state,
            questions=questions,
            evidence_refs=evidence_refs or [],
        )

    def qa_pass(
        self,
        artifact: Mapping[str, Any],
        stage_label: str = "intermediate_qa",
        evidence_refs: list[str] | None = None,
    ) -> MultipassTraceRecord:
        """Stage 4 — relevance/source-grounding/fit judgment on a draft artifact."""
        state = {
            "stage": stage_label,
            "tenant_scope": self.tenant_scope,
            "artifact_kind": str(artifact.get("kind", "")),
            "artifact_size": len(str(artifact.get("body", ""))),
        }
        questions = {
            "relevance": _ts.Score(
                question="How relevant is this artifact to the original task?",
                criteria=["low", "medium", "high"],
            ),
            "grounding": _ts.Score(
                question="Is the artifact grounded in provided evidence?",
                criteria=["unsupported", "partial", "grounded"],
            ),
        }
        return self._emit(
            stage=stage_label,
            primitive="Score",
            state=state,
            questions=questions,
            evidence_refs=evidence_refs or [],
        )

    def final_pass(
        self,
        artifact: Mapping[str, Any],
        downstream_action: str,
        evidence_refs: list[str] | None = None,
    ) -> MultipassTraceRecord:
        """Stage 6 — delivery-readiness gate before the host dispatches."""
        state = {
            "stage": "final",
            "tenant_scope": self.tenant_scope,
            "action": downstream_action,
            "artifact_kind": str(artifact.get("kind", "")),
        }
        questions = {
            "ready": _ts.Choice(
                question="Is this artifact ready to dispatch via the proposed action?",
                criteria=["ready", "revise", "block"],
            )
        }
        return self._emit(
            stage="final",
            primitive="Choice",
            state=state,
            questions=questions,
            evidence_refs=evidence_refs or [],
            downstream_action=downstream_action,
        )

    def outcome_pass(
        self,
        side_effect_id: str,
        observed_outcome: Any,
        evidence_refs: list[str] | None = None,
    ) -> MultipassTraceRecord:
        """Stage 7 — post-action outcome evaluation. Pure Noul.
        Used to detect downstream-action feedback loops."""
        state = {
            "stage": "outcome",
            "tenant_scope": self.tenant_scope,
            "side_effect_id": side_effect_id,
        }
        questions = {
            "ok": _ts.Noul(
                question="Did the downstream action complete as expected?",
            )
        }
        return self._emit(
            stage="outcome",
            primitive="Noul",
            state=state,
            questions=questions,
            evidence_refs=evidence_refs or [],
            side_effect_id=side_effect_id,
            observed_outcome=observed_outcome,
        )

    # ---- helpers ---- #

    def summary(self) -> dict[str, Any]:
        """Aggregate stats across all consumed calls in this consumer's life."""
        kinds: dict[str, int] = {}
        stages: dict[str, int] = {}
        for r in self.consumed_calls:
            kinds[r.result_kind] = kinds.get(r.result_kind, 0) + 1
            stages[r.stage] = stages.get(r.stage, 0) + 1
        return {
            "task_id": self.task_id,
            "tenant_scope": self.tenant_scope,
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "consumed_total": len(self.consumed_calls),
            "by_kind": kinds,
            "by_stage": stages,
            "real_calls": kinds.get("real", 0),
            "mock_calls": kinds.get("mock", 0),
            "cached_calls": kinds.get("cached", 0),
            "skipped_calls": kinds.get("skipped", 0),
        }


# ----------------------------------------------------------------------------- #
# Utility functions                                                             #
# ----------------------------------------------------------------------------- #


def _approx_evidence_size(evidence: Mapping[str, Any]) -> int:
    """Compact size estimate — used only as state for mock hashing, never logged."""
    try:
        return len(json.dumps(_normalize(evidence)))
    except Exception:
        return 0


def _now_iso() -> str:
    """ISO-8601 UTC, second-precision. Avoids importing datetime for portability."""
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def multipass_consumer(
    task_id: str,
    tenant_scope: str = "default",
    enabled: bool = True,
    cache_window_sec: int = 300,
) -> MultipassConsumer:
    """Convenience constructor."""
    return MultipassConsumer(
        task_id=task_id,
        tenant_scope=tenant_scope,
        enabled=enabled,
        cache_window_sec=cache_window_sec,
    )


# ----------------------------------------------------------------------------- #
# CLI for fixture replay + sanity check (used by tests + ops scripts)           #
# ----------------------------------------------------------------------------- #


def _main(argv: list[str]) -> int:
    """Small CLI to dump a fixture-mode trace for the canonical 5 stages.
    Useful for owner-visible audit. Never logs API key (uses canonical state
    via `_ts.credential_state`)."""
    import argparse

    parser = argparse.ArgumentParser(description="TypeSafe multi-pass fixture replay")
    parser.add_argument("--task-id", default="cli-fixture", help="Task id label")
    parser.add_argument("--tenant", default="default", help="Tenant scope")
    parser.add_argument(
        "--mode",
        choices=("fixture", "live"),
        default="fixture",
        help="fixture = mock-only (no network); live = real API (requires key)",
    )
    args = parser.parse_args(argv)

    if args.mode == "live":
        cred = _ts.credential_state()
        if cred.get("state") != "PRESENT":
            print("LIVE mode requires TYPESAFE_API_KEY (state != PRESENT)")
            return 2

    cons = multipass_consumer(task_id=args.task_id, tenant_scope=args.tenant)
    cons.intake_pass(evidence={"evidence_size": 1}, task="cli fixture")
    cons.plan_pass(task="cli fixture", options=["a", "b", "c"])
    cons.qa_pass(artifact={"kind": "cli_artifact", "body": "hello"}, evidence_refs=["ref-1"])
    cons.final_pass(
        artifact={"kind": "cli_artifact", "body": "hello"},
        downstream_action="publish",
        evidence_refs=["ref-1"],
    )
    cons.outcome_pass(side_effect_id="cli-side-1", observed_outcome="ok")

    summary = cons.summary()
    print(json.dumps(summary, indent=2))
    print()
    print("=== trace records ===")
    for r in cons.consumed_calls:
        d = r.to_dict()
        # Never include credential_fingerprint outside an owner-privileged shell.
        d.pop("credential_fingerprint", None)
        print(json.dumps(d, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
