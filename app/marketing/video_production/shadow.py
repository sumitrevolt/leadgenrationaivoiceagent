"""Stage 1 shadow harness — observe + compare, zero customer/social side effects.

Does NOT execute WhatsApp, Postiz, or live tenant campaign mutations.
Writes structured comparison records under data/video_stage1_shadow/ (gitignored).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from typing import Any

from app.marketing.video_production import flags, states
from app.marketing.video_production.feedback import classify_feedback
from app.marketing.video_production.publish_gate import evaluate_publish_gate
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Process-local counters — Stage 1 observability only (not multi-worker durable).
_COUNTERS: dict[str, int] = {
    "shadow_runs": 0,
    "shadow_successes": 0,
    "shadow_failures": 0,
    "decision_mismatches": 0,
    "tenant_isolation_blocks": 0,
    "whatsapp_outbound_attempts": 0,
    "whatsapp_inbound_mutations": 0,
    "postiz_api_attempts": 0,
    "social_schedules": 0,
    "social_publishes": 0,
    "customer_approval_mutations": 0,
    "jiya_records_touched": 0,
}


def reset_counters() -> dict[str, int]:
    for k in _COUNTERS:
        _COUNTERS[k] = 0
    return dict(_COUNTERS)


def counters() -> dict[str, int]:
    return dict(_COUNTERS)


def bump(name: str, n: int = 1) -> None:
    if name in _COUNTERS:
        _COUNTERS[name] += n


def _out_dir() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    path = os.path.join(root, "data", "video_stage1_shadow")
    os.makedirs(path, exist_ok=True)
    return path


def apply_stage1_env() -> dict[str, str]:
    """Set Stage 1 flag posture in-process (tests/scripts). Never touch prod .env."""
    posture = {
        "VIDEO_PRODUCTION_ENABLED": "1",
        "VIDEO_HARNESS_SHADOW_ENABLED": "1",
        "VIDEO_HARNESS_ENFORCE": "0",
        "VIDEO_DAILY_SCHEDULER_ENABLED": "0",
        "VIDEO_CUSTOMER_REVIEW_ENABLED": "0",
        "VIDEO_WHATSAPP_REVIEW_ENABLED": "0",
        "VIDEO_SOCIAL_PUBLISH_ENABLED": "0",
        "VIDEO_OWN_BRAND_ENABLED": "0",
        "VIDEO_AD_CYCLE": "0",
    }
    for k, v in posture.items():
        os.environ[k] = v
    return posture


def _harness_eval(tool: str, agent: str, args: dict[str, Any], risk: Any) -> dict[str, Any]:
    from app.agents.harness.registry import REGISTRY

    return REGISTRY.evaluate_action(
        tool_name=tool,
        tool_version="1.0.0",
        arguments=args,
        agent_id=agent,
        tenant_id=str(args.get("client_id") or "fixture-tenant-a"),
        idempotency_key=f"shadow:{uuid.uuid4().hex[:12]}",
        claimed_risk=risk,
    )


def _compare_brief(niche: str, language: str) -> dict[str, Any]:
    from app.marketing.video_production.cell import create_daily_brief, write_script

    # Fixture client via monkeypatch is preferred in tests; here use synthetic brief path.
    brief = {
        "id": uuid.uuid4().hex[:12],
        "client_id": "fixture-tenant-a",
        "content_date": time.strftime("%Y-%m-%d"),
        "business_name": f"Fixture {niche.title()}",
        "niche": niche,
        "offer": "",
        "offer_missing": True,
        "purpose": "organic_daily",
        "language": language,
        "hook": f"Fixture {niche} update",
        "cta": "Call ya WhatsApp karo",
        "agent": "isha",
        "workflow_state": states.BRIEF_CREATED,
    }
    script = write_script(brief)
    from app.agents.harness.registry import RiskLane

    ev = _harness_eval(
        "video.brief.create",
        "isha",
        {"client_id": "fixture-tenant-a"},
        RiskLane.GREEN,
    )
    mismatch = bool(ev.get("would_deny"))
    if mismatch:
        bump("decision_mismatches")
    return {
        "kind": "brief_script",
        "niche": niche,
        "language": language,
        "legacy": {
            "offer_missing": True,
            "fabricated_claims": script.get("script", {}).get("fabricated_claims"),
            "slides": len(script.get("script", {}).get("slides") or []),
        },
        "harness": {
            "would_deny": ev.get("would_deny"),
            "would_require_approval": ev.get("would_require_approval"),
            "registry_risk_class": ev.get("registry_risk_class"),
        },
        "category": "HARNESS_BUG" if mismatch else "MATCH",
        "ok": script.get("ok") and not mismatch,
    }


# Deterministic synthetic content identity. The shadow matrix must never touch
# the filesystem (zero-side-effect + repeatability), so it evaluates the PURE
# gate with a fixed observation instead of hashing a real artifact.
_SHADOW_OBSERVED_SHA256 = "5" * 64
_SHADOW_OBSERVED_BYTES = 2048


def _compare_publish_gate(case: str) -> dict[str, Any]:
    approved = {
        "status": "approved",
        "workflow_state": states.APPROVED,
        "approval_id": "fixture-approval-1",
        "video_path": "data/video_ads/fixture.mp4",
        "revision": 0,
        "approved_version": 0,
        "final_approved": True,
        "client_id": "fixture-tenant-a",
        "id": "fixture-video-project-a",
        # Stored identity matches the synthetic observation, so the intended
        # SUCCESS row stays a success without any file existing on disk.
        "approved_content_sha256": _SHADOW_OBSERVED_SHA256,
        "approved_content_bytes": _SHADOW_OBSERVED_BYTES,
        # Stage 3B-close: publish eligibility also requires a FINALIZED
        # saga-owned snapshot identity. The `approval_present` scenario exists
        # to prove the gate's OK path, so its fixture must now be a properly
        # COORDINATED approval — otherwise the row would be asserting that an
        # uncoordinated legacy record publishes, which is the bypass itself.
        # The refusal cases below all still refuse, for their own reasons.
        "approval_txn_state": "finalized",
        "approval_txn": "shadow-fixture-txn",
        "approval_snapshot_path": "data/approved_media/fixture.snap.mp4",
        "approval_snapshot_sha256": _SHADOW_OBSERVED_SHA256,
        "approval_snapshot_bytes": _SHADOW_OBSERVED_BYTES,
    }
    if case == "missing_approval":
        rec = {**approved, "status": "pending", "workflow_state": states.CLIENT_REVIEW_PENDING}
        expect_ok = False
    elif case == "stale_version":
        rec = {**approved, "approved_version": 1}
        expect_ok = False
    elif case == "social_flag_off":
        rec = approved
        expect_ok = False  # production cell ON + social OFF
    elif case == "approval_present":
        # Temporarily allow social to prove gate ok path, then restore — caller sets env.
        rec = approved
        expect_ok = True
    else:
        rec = approved
        expect_ok = False

    # PURE evaluation only — no hashing, no file access, no mutation.
    gate = evaluate_publish_gate(
        rec,
        observed_sha256=_SHADOW_OBSERVED_SHA256,
        observed_bytes=_SHADOW_OBSERVED_BYTES,
    )
    ok = bool(gate.get("ok")) == expect_ok
    if not ok:
        bump("decision_mismatches")
    return {
        "kind": "publish_gate",
        "case": case,
        "gate": gate,
        "expected_ok": expect_ok,
        "category": "MATCH" if ok else "HARNESS_BUG",
        "ok": ok,
    }


def _compare_feedback(text: str, expect_intent: str) -> dict[str, Any]:
    got = classify_feedback(text)
    ok = got.get("intent") == expect_intent
    if not ok:
        bump("decision_mismatches")
    return {
        "kind": "feedback",
        "text": text[:80],
        "intent": got.get("intent"),
        "expected": expect_intent,
        "ambiguous": got.get("ambiguous"),
        "category": "MATCH" if ok else "CONTRACT_GAP",
        "ok": ok,
    }


def _isolation_case(name: str, fn) -> dict[str, Any]:
    try:
        out = fn()
        blocked = not out.get("handled", True) if "handled" in out else not out.get("ok", True)
        if blocked:
            bump("tenant_isolation_blocks")
        ok = bool(out.get("ok_expected", blocked))
        return {
            "kind": "isolation",
            "case": name,
            "result": {k: out.get(k) for k in ("handled", "reason", "ok", "error") if k in out},
            "category": "MATCH" if ok else "POLICY_GAP",
            "ok": ok,
        }
    except Exception as e:
        bump("shadow_failures")
        return {"kind": "isolation", "case": name, "error": str(e)[:160], "ok": False}


def run_shadow_matrix(*, write_report: bool = True) -> dict[str, Any]:
    """Bounded deterministic Stage 1 matrix. No network, no Jiya, no Postiz."""
    apply_stage1_env()
    reset_counters()
    correlation_id = uuid.uuid4().hex[:16]
    started = time.time()
    rows: list[dict[str, Any]] = []

    # --- flag posture ---
    snap = flags.flag_snapshot()
    posture_ok = bool(snap.get("stage1_shadow_active"))
    rows.append(
        {
            "kind": "posture",
            "flags": snap,
            "ok": posture_ok,
            "category": "MATCH" if posture_ok else "POLICY_GAP",
        }
    )
    if not posture_ok:
        bump("shadow_failures")

    # --- brief/script × niches × languages ---
    for niche in ("salon", "solar", "clinic"):
        for lang in ("hi", "en"):
            bump("shadow_runs")
            row = _compare_brief(niche, lang)
            rows.append(row)
            bump("shadow_successes" if row.get("ok") else "shadow_failures")

    # --- ratios harness eval ---
    from app.agents.harness.registry import RiskLane
    from app.marketing.video_production.profiles import resolve_profile

    for ratio in ("9:16", "1:1", "16:9"):
        bump("shadow_runs")
        prof = resolve_profile(ratio)
        ev = _harness_eval(
            "video.render.social",
            "isha",
            {"client_id": "fixture-tenant-a", "ratio": ratio},
            RiskLane.GREEN,
        )
        ok = bool(prof.get("width")) and not ev.get("would_deny")
        rows.append(
            {
                "kind": "render_profile",
                "ratio": ratio,
                "profile": prof,
                "harness_deny": ev.get("would_deny"),
                "ok": ok,
                "category": "MATCH" if ok else "HARNESS_BUG",
            }
        )
        bump("shadow_successes" if ok else "shadow_failures")

    # --- publish gate cases ---
    for case in ("missing_approval", "stale_version", "social_flag_off"):
        bump("shadow_runs")
        row = _compare_publish_gate(case)
        rows.append(row)
        bump("shadow_successes" if row.get("ok") else "shadow_failures")

    # approval_present with temporary social ON (still fixture-only, no Postiz call)
    bump("shadow_runs")
    os.environ["VIDEO_SOCIAL_PUBLISH_ENABLED"] = "1"
    row = _compare_publish_gate("approval_present")
    os.environ["VIDEO_SOCIAL_PUBLISH_ENABLED"] = "0"
    rows.append(row)
    bump("shadow_successes" if row.get("ok") else "shadow_failures")

    # --- feedback ---
    for text, intent in (
        ("APPROVE", "approve"),
        ("theek", "ambiguous"),
        ("👍", "ambiguous"),
        ("looks okay", "ambiguous"),
        ("REJECT", "reject"),
        ("Logo bada karo", "changes"),
    ):
        bump("shadow_runs")
        row = _compare_feedback(text, intent)
        rows.append(row)
        bump("shadow_successes" if row.get("ok") else "shadow_failures")

    # --- WA/Postiz isolation (flags OFF → no mutation) ---
    from app.marketing.video_production import review_whatsapp

    bump("shadow_runs")
    wa_out = review_whatsapp.send_review_whatsapp(
        {"id": "fixture-video-project-a", "revision": 0, "client_id": "fixture-tenant-a"}
    )
    # send_review_whatsapp returns early — count as attempt only if it tried network
    if wa_out.get("sent") or wa_out.get("detail"):
        bump("whatsapp_outbound_attempts")
    wa_ok = wa_out.get("sent") is False and "VIDEO_WHATSAPP_REVIEW_ENABLED" in str(
        wa_out.get("reason") or ""
    )
    rows.append(
        {
            "kind": "wa_outbound",
            "result": wa_out,
            "ok": wa_ok,
            "category": "MATCH" if wa_ok else "POLICY_GAP",
        }
    )
    bump("shadow_successes" if wa_ok else "shadow_failures")

    bump("shadow_runs")
    wa_in = review_whatsapp.ingest_inbound("919876543210", "APPROVE", "shadow-mid-1")
    if wa_in.get("handled"):
        bump("whatsapp_inbound_mutations")
        bump("customer_approval_mutations")
    wa_in_ok = wa_in.get("handled") is False
    if wa_in_ok:
        bump("tenant_isolation_blocks")
    rows.append(
        {
            "kind": "wa_inbound",
            "result": wa_in,
            "ok": wa_in_ok,
            "category": "MATCH" if wa_in_ok else "POLICY_GAP",
        }
    )
    bump("shadow_successes" if wa_in_ok else "shadow_failures")

    # --- publish tool harness requires approval ---
    bump("shadow_runs")
    pub_ev = _harness_eval(
        "video.social.schedule",
        "zara",
        {"video_ad_id": "fixture-video-project-a"},
        RiskLane.AMBER,
    )
    pub_ok = bool(pub_ev.get("would_require_approval")) and not pub_ev.get("executed")
    rows.append(
        {
            "kind": "publish_harness",
            "harness": {
                "would_require_approval": pub_ev.get("would_require_approval"),
                "would_deny": pub_ev.get("would_deny"),
            },
            "ok": pub_ok,
            "category": "MATCH" if pub_ok else "HARNESS_BUG",
        }
    )
    bump("shadow_successes" if pub_ok else "shadow_failures")

    # --- wrong agent deny ---
    bump("shadow_runs")
    deny = _harness_eval(
        "video.social.schedule",
        "swara",
        {"video_ad_id": "fixture-video-project-a"},
        RiskLane.AMBER,
    )
    deny_ok = bool(deny.get("would_deny"))
    rows.append(
        {
            "kind": "wrong_agent",
            "ok": deny_ok,
            "category": "MATCH" if deny_ok else "HARNESS_BUG",
        }
    )
    bump("shadow_successes" if deny_ok else "shadow_failures")

    c = counters()
    side_effect_zero = (
        c["whatsapp_outbound_attempts"] == 0
        and c["whatsapp_inbound_mutations"] == 0
        and c["postiz_api_attempts"] == 0
        and c["social_schedules"] == 0
        and c["social_publishes"] == 0
        and c["customer_approval_mutations"] == 0
        and c["jiya_records_touched"] == 0
    )
    all_ok = posture_ok and side_effect_zero and c["shadow_failures"] == 0

    report = {
        "correlation_id": correlation_id,
        "stage": "stage1_shadow",
        "ok": all_ok,
        "duration_s": round(time.time() - started, 3),
        "flags": flags.flag_snapshot(),
        "counters": c,
        "side_effect_zero": side_effect_zero,
        "input_hash": hashlib.sha256(
            json.dumps([r.get("kind") for r in rows], sort_keys=True).encode()
        ).hexdigest()[:16],
        "rows": rows,
        "mismatches": [r for r in rows if not r.get("ok")],
    }

    if write_report:
        path = os.path.join(_out_dir(), f"shadow_{correlation_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        summary = os.path.join(_out_dir(), "latest_summary.json")
        with open(summary, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "correlation_id": correlation_id,
                    "ok": all_ok,
                    "counters": c,
                    "side_effect_zero": side_effect_zero,
                    "mismatches": len(report["mismatches"]),
                    "report_basename": os.path.basename(path),
                },
                f,
                indent=2,
            )
        report["report_path"] = path
        logger.info(
            f"[video_shadow] stage1 correlation={correlation_id} ok={all_ok} "
            f"runs={c['shadow_runs']} mismatches={c['decision_mismatches']}"
        )

    return report


def rollback_stage1_env() -> None:
    """Flag rollback drill — all VIDEO_* back to OFF."""
    for k in (
        "VIDEO_PRODUCTION_ENABLED",
        "VIDEO_HARNESS_SHADOW_ENABLED",
        "VIDEO_HARNESS_ENFORCE",
        "VIDEO_DAILY_SCHEDULER_ENABLED",
        "VIDEO_CUSTOMER_REVIEW_ENABLED",
        "VIDEO_WHATSAPP_REVIEW_ENABLED",
        "VIDEO_SOCIAL_PUBLISH_ENABLED",
        "VIDEO_OWN_BRAND_ENABLED",
        "VIDEO_AD_CYCLE",
    ):
        os.environ[k] = "0"


__all__ = [
    "apply_stage1_env",
    "bump",
    "counters",
    "reset_counters",
    "rollback_stage1_env",
    "run_shadow_matrix",
]
