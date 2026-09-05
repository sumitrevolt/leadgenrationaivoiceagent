"""
Swara Observability & Shadow Mode Infrastructure.

Rule 11: Shadow mode A/B evaluation — new behavior runs in shadow first.
Rule 18: Maintain metrics including:
    hinglish_quality_score, pronunciation_error_rate, customer_interruptions,
    barge_in_success_rate, response_latency, conversation_completion_rate,
    language_switch_accuracy, repeated_phrase_rate, customer_sentiment,
    owner_correction_rate, candidate_promotion_rate, voice_consistency_score,
    vaqi_interruption_rate, vaqi_premature_interruption_rate, vaqi_missed_response_rate,
    vaqi_latency_p50, vaqi_latency_p95, vaqi_latency_p99, vaqi_turns_total

Rule 19: Version everything — metrics schema versioned.

VAQI (Voice Agent Quality Index) — Deepgram's 3-leg reliability score:
    1. Interruptions (premature barge-ins / total barge-ins)
    2. Missed responses (turns with no agent reply / total turns)
    3. Latency (P50/P95/P99 response times)
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger
from app.voice_agent.swara_config import get_version_info

logger = setup_logger(__name__)


# -----------------------------------------------------------------------------
# METRICS SCHEMA VERSION
# -----------------------------------------------------------------------------

METRICS_SCHEMA_VERSION = "swara_metrics_v1"


# -----------------------------------------------------------------------------
# VAQI (Voice Agent Quality Index) — Deepgram 3-leg reliability score
# -----------------------------------------------------------------------------

def _vaqi_latency_summary(samples_ms: list[float]) -> dict[str, float]:
    """P50/P95/P99 + mean/max/n. CARDINAL RULE 2: latency me average nahi,
    distribution report karo (tail = real UX)."""
    if not samples_ms:
        return {"n": 0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "mean": 0.0, "max": 0.0}
    vals = sorted(samples_ms)
    n = len(vals)
    def _pct(p: float) -> float:
        if n == 1:
            return float(vals[0])
        k = (n - 1) * (p / 100.0)
        lo = int(k)
        hi = min(lo + 1, n - 1)
        return float(vals[lo] + (vals[hi] - vals[lo]) * (k - lo))
    return {
        "n": n,
        "p50": round(_pct(50), 1),
        "p95": round(_pct(95), 1),
        "p99": round(_pct(99), 1),
        "mean": round(sum(vals) / n, 1),
        "max": round(max(vals), 1),
    }


def _vaqi_calculate(call_metrics: "VoiceCallMetrics") -> dict[str, Any]:
    """Calculate VAQI metrics for a single call.
    
    Returns dict with VAQI legs:
    - interruption_rate: premature_interruptions / total_interruptions (if interruptions > 0)
    - missed_response_rate: missed_responses / turns (if turns > 0)
    - latency: P50/P95/P99 of response latencies
    """
    vaqi = {
        "vaqi_interruption_rate": None,
        "vaqi_premature_interruption_rate": None,
        "vaqi_missed_response_rate": None,
        "vaqi_latency_p50": 0.0,
        "vaqi_latency_p95": 0.0,
        "vaqi_latency_p99": 0.0,
        "vaqi_turns_total": call_metrics.turns,
    }
    
    # Note: These fields need to be populated by the call code (turn_detector.py / vobiz_stream.py)
    # via record_turn() with is_customer_interruption=True for interruptions,
    # and a new record_missed_response() method for missed responses.
    # For now, they stay None (not 0, which would misleadingly read as "perfect")
    # until live call code starts calling the recording methods.
    
    return vaqi


# -----------------------------------------------------------------------------
# METRICS DATA CLASSES
# -----------------------------------------------------------------------------

@dataclass
class VoiceCallMetrics:
    """Metrics for a single voice call."""
    call_id: str
    start_time: str
    end_time: str | None = None
    duration_seconds: float = 0.0
    turns: int = 0
    # Quality metrics
    hinglish_quality_score: float = 0.0
    pronunciation_error_rate: float = 0.0
    # Interaction metrics
    customer_interruptions: int = 0
    barge_in_events: int = 0
    barge_in_success_rate: float = 0.0
    # VAQI metrics (Deepgram 3-leg reliability score)
    vaqi_interruption_rate: float | None = None          # premature / total barge-ins
    vaqi_premature_interruption_rate: float | None = None  # premature interruptions
    vaqi_missed_response_rate: float | None = None       # missed responses / turns
    vaqi_latency_p50: float = 0.0
    vaqi_latency_p95: float = 0.0
    vaqi_latency_p99: float = 0.0
    vaqi_turns_total: int = 0
    # Latency metrics
    avg_response_latency_ms: float = 0.0
    p50_response_latency_ms: float = 0.0
    p95_response_latency_ms: float = 0.0
    # Language metrics
    language_switches: int = 0
    language_switch_accuracy: float = 0.0
    # Conversation metrics
    conversation_completion_rate: float = 0.0  # 1.0 if completed naturally
    repeated_phrase_rate: float = 0.0
    customer_sentiment: float = 0.0  # -1 to 1
    # Outcome
    outcome: str = "unknown"  # completed, dropped, escalated, opt_out
    # Version
    metrics_version: str = METRICS_SCHEMA_VERSION


@dataclass
class AggregatedMetrics:
    """Aggregated metrics across calls (for dashboards)."""
    period_start: str
    period_end: str
    total_calls: int = 0
    total_duration_seconds: float = 0.0
    avg_hinglish_quality: float = 0.0
    avg_pronunciation_error_rate: float = 0.0
    total_interruptions: int = 0
    avg_barge_in_success_rate: float = 0.0
    avg_response_latency_ms: float = 0.0
    avg_language_switch_accuracy: float = 0.0
    conversation_completion_rate: float = 0.0
    avg_repeated_phrase_rate: float = 0.0
    avg_customer_sentiment: float = 0.0
    outcomes: dict[str, int] = field(default_factory=dict)
    # Learning pipeline metrics
    owner_correction_rate: float = 0.0
    candidate_promotion_rate: float = 0.0
    voice_consistency_score: float = 0.0
    # Version
    metrics_version: str = METRICS_SCHEMA_VERSION


# -----------------------------------------------------------------------------
# METRICS COLLECTOR
# -----------------------------------------------------------------------------

class SwaraMetricsCollector:
    """
    Collects and aggregates Swara voice metrics (Rule 18).

    Stores in Redis (for real-time) + JSONL (for durability).
    Provides aggregation for dashboards.
    """

    def __init__(self) -> None:
        self._redis = None
        self._redis_connected = False
        self._jsonl_path: str | None = None
        self._current_calls: dict[str, VoiceCallMetrics] = {}
        self._completed_calls: list[VoiceCallMetrics] = []
        self._lock = threading.RLock()
        self._call_latencies: dict[str, list[float]] = defaultdict(list)

    def _init_redis(self) -> bool:
        if self._redis_connected:
            return self._redis is not None
        try:
            from app.platform.extensions import get_redis
            self._redis = get_redis()
            self._redis_connected = True
        except Exception as e:
            logger.debug(f"[metrics] Redis not available: {e}")
            self._redis = None
            self._redis_connected = True
        return self._redis is not None

    def _init_jsonl(self) -> str | None:
        if self._jsonl_path is not None:
            return self._jsonl_path
        base = os.getenv("SWARA_METRICS_DATA_DIR", "data/swara_metrics")
        try:
            os.makedirs(base, exist_ok=True)
            self._jsonl_path = os.path.join(base, "call_metrics.jsonl")
        except Exception as e:
            logger.warning(f"[metrics] Cannot init JSONL path: {e}")
            self._jsonl_path = None
        return self._jsonl_path

    # -------------------------------------------------------------------------
    # CALL LIFECYCLE
    # -------------------------------------------------------------------------

    def start_call(self, call_id: str) -> VoiceCallMetrics:
        """Start tracking a new call."""
        metrics = VoiceCallMetrics(
            call_id=call_id,
            start_time=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._current_calls[call_id] = metrics
            self._call_latencies[call_id] = []
        logger.debug(f"[metrics] Started call {call_id}")
        return metrics

    def record_turn(
        self,
        call_id: str,
        latency_ms: float,
        is_barge_in: bool = False,
        is_customer_interruption: bool = False,
    ) -> None:
        """Record a conversation turn."""
        with self._lock:
            call = self._current_calls.get(call_id)
            if not call:
                return

            call.turns += 1
            self._call_latencies[call_id].append(latency_ms)

            if is_barge_in:
                call.barge_in_events += 1
            if is_customer_interruption:
                call.customer_interruptions += 1

    def record_latency(self, call_id: str, latency_ms: float) -> None:
        """Record a response latency measurement."""
        with self._lock:
            self._call_latencies[call_id].append(latency_ms)

    def end_call(
        self,
        call_id: str,
        outcome: str = "completed",
        hinglish_quality: float = 0.0,
        pronunciation_errors: int = 0,
        total_words: int = 0,
        language_switches: int = 0,
        correct_switches: int = 0,
        repeated_phrases: int = 0,
        customer_sentiment: float = 0.0,
    ) -> VoiceCallMetrics | None:
        """End call tracking and compute final metrics."""
        with self._lock:
            call = self._current_calls.pop(call_id, None)
            if not call:
                return None

            latencies = self._call_latencies.pop(call_id, [])

            call.end_time = datetime.now(timezone.utc).isoformat()
            start = datetime.fromisoformat(call.start_time.replace('Z', '+00:00'))
            end = datetime.fromisoformat(call.end_time.replace('Z', '+00:00'))
            call.duration_seconds = (end - start).total_seconds()
            call.outcome = outcome

            # Compute quality metrics
            call.hinglish_quality_score = hinglish_quality
            call.pronunciation_error_rate = (
                pronunciation_errors / total_words if total_words > 0 else 0.0
            )

            # Barge-in success rate
            if call.barge_in_events > 0:
                # Simplified: assume success if not escalated
                call.barge_in_success_rate = 1.0 if outcome != "escalated" else 0.5

            # Latency metrics
            if latencies:
                call.avg_response_latency_ms = sum(latencies) / len(latencies)
                sorted_lat = sorted(latencies)
                call.p50_response_latency_ms = sorted_lat[len(sorted_lat) // 2]
                call.p95_response_latency_ms = sorted_lat[int(len(sorted_lat) * 0.95)]

            # Language metrics
            call.language_switches = language_switches
            call.language_switch_accuracy = (
                correct_switches / language_switches if language_switches > 0 else 1.0
            )

            # Conversation metrics
            call.repeated_phrase_rate = (
                repeated_phrases / call.turns if call.turns > 0 else 0.0
            )
            call.customer_sentiment = customer_sentiment
            call.conversation_completion_rate = 1.0 if outcome == "completed" else 0.0

            self._completed_calls.append(call)
            self._persist(call)

            logger.info(f"[metrics] Call {call_id} ended: outcome={outcome} duration={call.duration_seconds:.1f}s turns={call.turns}")
            return call

    def _persist(self, call: VoiceCallMetrics) -> None:
        """Persist call metrics to JSONL."""
        self._init_jsonl()
        if not self._jsonl_path:
            return
        try:
            with open(self._jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(call), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[metrics] Persist failed: {e}")

    # -------------------------------------------------------------------------
    # AGGREGATION
    # -------------------------------------------------------------------------

    def get_aggregated(self, hours: int = 24) -> AggregatedMetrics:
        """Get aggregated metrics for the last N hours."""
        cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)

        with self._lock:
            recent = [
                c for c in self._completed_calls
                if datetime.fromisoformat(c.end_time.replace('Z', '+00:00')).timestamp() > cutoff
            ] if self._completed_calls else []

        if not recent:
            return AggregatedMetrics(
                period_start=datetime.fromtimestamp(cutoff, timezone.utc).isoformat(),
                period_end=datetime.now(timezone.utc).isoformat(),
            )

        # Aggregate
        total_calls = len(recent)
        total_duration = sum(c.duration_seconds for c in recent)

        agg = AggregatedMetrics(
            period_start=min(c.start_time for c in recent),
            period_end=max(c.end_time for c in recent),
            total_calls=total_calls,
            total_duration_seconds=total_duration,
            avg_hinglish_quality=sum(c.hinglish_quality_score for c in recent) / total_calls,
            avg_pronunciation_error_rate=sum(c.pronunciation_error_rate for c in recent) / total_calls,
            total_interruptions=sum(c.customer_interruptions for c in recent),
            avg_barge_in_success_rate=sum(c.barge_in_success_rate for c in recent) / total_calls,
            avg_response_latency_ms=sum(c.avg_response_latency_ms for c in recent) / total_calls,
            avg_language_switch_accuracy=sum(c.language_switch_accuracy for c in recent) / total_calls,
            conversation_completion_rate=sum(c.conversation_completion_rate for c in recent) / total_calls,
            avg_repeated_phrase_rate=sum(c.repeated_phrase_rate for c in recent) / total_calls,
            avg_customer_sentiment=sum(c.customer_sentiment for c in recent) / total_calls,
        )

        # Outcomes
        for c in recent:
            agg.outcomes[c.outcome] = agg.outcomes.get(c.outcome, 0) + 1

        # Learning pipeline metrics
        from app.voice_agent.swara_learning import get_voice_learning_store
        store = get_voice_learning_store()
        stats = store.get_stats()
        total_events = stats.get("total_events", 0)
        if total_events > 0:
            agg.owner_correction_rate = stats.get("high_priority_corrections", 0) / total_events
            promoted = stats.get("by_status", {}).get("approved", 0)
            agg.candidate_promotion_rate = promoted / total_events

        # Voice consistency (simplified: inverse of pronunciation error variance)
        error_rates = [c.pronunciation_error_rate for c in recent]
        if error_rates:
            avg_err = sum(error_rates) / len(error_rates)
            variance = sum((e - avg_err) ** 2 for e in error_rates) / len(error_rates)
            agg.voice_consistency_score = max(0.0, 1.0 - variance * 10)

        return agg

    def get_recent_calls(self, limit: int = 50) -> list[VoiceCallMetrics]:
        """Get recent call metrics."""
        with self._lock:
            return list(self._completed_calls)[-limit:]

    def get_current_call(self, call_id: str) -> VoiceCallMetrics | None:
        """Get metrics for an in-progress call."""
        with self._lock:
            return self._current_calls.get(call_id)


# -----------------------------------------------------------------------------
# SHADOW MODE INFRASTRUCTURE (Rule 11)
# -----------------------------------------------------------------------------

@dataclass
class ShadowExperiment:
    """A shadow mode experiment comparing production vs candidate."""
    experiment_id: str
    name: str
    candidate_version: str
    production_version: str
    traffic_split: float = 0.1  # 10% to candidate
    enabled: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: dict[str, Any] = field(default_factory=dict)


class ShadowModeManager:
    """
    Manages shadow mode A/B experiments (Rule 11).

    Routes a fraction of traffic to candidate behavior, collects metrics,
    and provides comparison against production baseline.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, ShadowExperiment] = {}
        self._assignments: dict[str, str] = {}  # call_id -> experiment_id
        self._lock = threading.RLock()

    def create_experiment(
        self,
        name: str,
        candidate_version: str,
        production_version: str,
        traffic_split: float = 0.1,
    ) -> ShadowExperiment:
        """Create a new shadow experiment."""
        exp = ShadowExperiment(
            experiment_id=f"shadow_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            name=name,
            candidate_version=candidate_version,
            production_version=production_version,
            traffic_split=traffic_split,
        )
        with self._lock:
            self._experiments[exp.experiment_id] = exp
        logger.info(f"[shadow] Created experiment {exp.experiment_id}: {name}")
        return exp

    def get_experiment(self, experiment_id: str) -> ShadowExperiment | None:
        with self._lock:
            return self._experiments.get(experiment_id)

    def list_experiments(self) -> list[ShadowExperiment]:
        with self._lock:
            return list(self._experiments.values())

    def should_use_candidate(self, call_id: str, experiment_id: str) -> bool:
        """Determine if a call should use candidate (shadow) behavior."""
        exp = self.get_experiment(experiment_id)
        if not exp or not exp.enabled:
            return False

        # Deterministic assignment based on call_id hash
        import hashlib
        hash_val = int(hashlib.md5(f"{call_id}:{experiment_id}".encode()).hexdigest(), 16)
        use_candidate = (hash_val % 10000) / 10000 < exp.traffic_split

        with self._lock:
            if use_candidate:
                self._assignments[call_id] = experiment_id
            else:
                self._assignments[call_id] = "production"

        return use_candidate

    def get_assignment(self, call_id: str) -> str:
        """Get the assignment for a call (production or experiment_id)."""
        with self._lock:
            return self._assignments.get(call_id, "production")

    def record_metrics(self, experiment_id: str, metrics: dict[str, Any]) -> None:
        """Record metrics for an experiment."""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp:
                # Merge metrics
                for key, value in metrics.items():
                    if key in exp.metrics:
                        # Simple aggregation: keep running average
                        if isinstance(value, (int, float)) and isinstance(exp.metrics[key], (int, float)):
                            exp.metrics[key] = (exp.metrics[key] + value) / 2
                        else:
                            exp.metrics[key] = value
                    else:
                        exp.metrics[key] = value

    def get_comparison(self, experiment_id: str) -> dict[str, Any] | None:
        """Get production vs candidate comparison for an experiment."""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if not exp:
                return None

        # In production, this would query actual metrics from both variants
        # For now, return experiment metadata
        return {
            "experiment_id": exp.experiment_id,
            "name": exp.name,
            "candidate_version": exp.candidate_version,
            "production_version": exp.production_version,
            "traffic_split": exp.traffic_split,
            "enabled": exp.enabled,
            "metrics": exp.metrics,
        }


# -----------------------------------------------------------------------------
# SINGLETONS
# -----------------------------------------------------------------------------

_metrics_collector: SwaraMetricsCollector | None = None
_shadow_manager: ShadowModeManager | None = None


def get_metrics_collector() -> SwaraMetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = SwaraMetricsCollector()
    return _metrics_collector


def get_shadow_manager() -> ShadowModeManager:
    global _shadow_manager
    if _shadow_manager is None:
        _shadow_manager = ShadowModeManager()
    return _shadow_manager


# -----------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS
# -----------------------------------------------------------------------------

def record_call_metrics(
    call_id: str,
    outcome: str = "completed",
    **kwargs,
) -> VoiceCallMetrics | None:
    """Convenience function to end call and record metrics."""
    return get_metrics_collector().end_call(call_id, outcome, **kwargs)


def start_call_metrics(call_id: str) -> VoiceCallMetrics:
    """Start metrics collection for a call."""
    return get_metrics_collector().start_call(call_id)


def get_swara_metrics(hours: int = 24) -> AggregatedMetrics:
    """Get aggregated Swara metrics for dashboard."""
    return get_metrics_collector().get_aggregated(hours)


__all__ = [
    "VoiceCallMetrics",
    "AggregatedMetrics",
    "SwaraMetricsCollector",
    "ShadowExperiment",
    "ShadowModeManager",
    "get_metrics_collector",
    "get_shadow_manager",
    "record_call_metrics",
    "start_call_metrics",
    "get_swara_metrics",
    "METRICS_SCHEMA_VERSION",
]