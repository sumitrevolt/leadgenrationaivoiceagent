"""lifecycle.py — one honest, tenant-scoped 9-stage projection per video.

WHY THIS EXISTS
---------------
A video's state is spread across five stores: `store` (spec/status), `assets`
(registered output), `qa`/`enterprise_qa` (quality), `approval` (the publish
gate binding) and `delivery_ledger` (what the customer actually received). No
single view answers "where exactly did this video stop, and what do I do?".

This module is a PROJECTION — it reads those stores and renders the 9 stages:

    spec → assets → render → qa → enterprise_grade → approval → publish
         → delivery → evidence

THE HONESTY RULE (design §7)
----------------------------
A missing stage is reported ``not_reached`` (or ``failed`` when it actively
failed). It is NEVER reported ``passed``. A dashboard that paints an un-run
stage green is exactly the false-green class this projection exists to remove.

Every public entry returns a dict and NEVER raises.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: The ordered lifecycle stages. Order is the contract — the dashboard stepper
#: and the "where did it stop" answer both depend on it.
STAGES: tuple[str, ...] = (
    "spec",
    "assets",
    "render",
    "qa",
    "enterprise_grade",
    "approval",
    "publish",
    "delivery",
    "evidence",
)

PASSED = "passed"
FAILED = "failed"
PENDING = "pending"
NOT_REACHED = "not_reached"

#: Stages that require the PREVIOUS stage to have passed. A stage behind a
#: failed predecessor is `not_reached`, not `failed` — the distinction is what
#: lets the UI name the single root cause instead of reddening the whole row.
_ORDER_INDEX = {name: i for i, name in enumerate(STAGES)}


def stages() -> list[str]:
    """The ordered stage names (copy)."""
    return list(STAGES)


def _row(stage: str, status: str, *, at: Any = None, reason: str = "", evidence: Any = None) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": status,
        "at": at,
        "reason": str(reason or "")[:240],
        "evidence": evidence if evidence is not None else {},
    }


def _first_unpassed(rows: list[dict[str, Any]]) -> str:
    for r in rows:
        if r["status"] != PASSED:
            return r["stage"]
    return ""


def _delivery_events(tenant_id: str) -> list[dict[str, Any]]:
    try:
        from app.marketing import delivery_ledger

        return delivery_ledger.timeline(tenant_id, limit=200)
    except Exception:
        return []


def project(tenant_id: str, creative_id: str) -> dict[str, Any]:
    """Project the 9 stages for ONE creative. Never raises.

    Returns ``{ok, tenant_id, creative_id, stages:[...], failed_stage,
    complete, status}``. ``ok:False`` only when the record cannot be resolved at
    all (missing / cross-tenant) — that is a tenant-scoped ``not_found``, never
    another tenant's data.
    """
    cid = str(tenant_id or "").strip()
    crid = str(creative_id or "").strip()
    out: dict[str, Any] = {
        "ok": False,
        "tenant_id": cid,
        "creative_id": crid,
        "stages": [],
        "failed_stage": "",
        "complete": False,
        "status": "not_found",
    }
    if not cid or not crid:
        out["error"] = "tenant_id_and_creative_id_required"
        return out
    try:
        from app.marketing.creative_os.store import get_record

        got = get_record(cid, crid)
    except Exception as exc:
        out["error"] = str(exc)[:160]
        return out
    if not got.get("ok"):
        out["error"] = str(got.get("error") or "not_found")
        out["status"] = str(got.get("error") or "not_found")
        return out

    rec = got["record"]
    spec = rec.get("spec") or {}
    status = str(rec.get("status") or "")
    rows: list[dict[str, Any]] = []

    # 1. spec ---------------------------------------------------------------- #
    scenes = spec.get("scenes") or []
    spec_ok = bool(spec.get("creative_id") and scenes)
    rows.append(
        _row(
            "spec",
            PASSED if spec_ok else FAILED,
            at=rec.get("updated_at"),
            reason="" if spec_ok else "spec_missing_or_empty",
            evidence={
                "recipe": spec.get("recipe"),
                "template_id": spec.get("template_id"),
                "hook_variant": spec.get("hook_variant"),
                "scene_count": len(scenes),
            },
        )
    )

    # 2. assets -------------------------------------------------------------- #
    asset_id = str(spec.get("output_asset_id") or rec.get("output_asset_id") or "")
    asset_ok = False
    asset_ref = ""
    if asset_id:
        try:
            from app.marketing.creative_os.assets import get_asset

            a = get_asset(cid, asset_id)
            if a.get("ok"):
                asset_ok = True
                asset_ref = str((a.get("asset") or {}).get("ref") or "")
        except Exception:
            asset_ok = False
    rows.append(
        _row(
            "assets",
            PASSED if asset_ok else NOT_REACHED,
            at=None,
            reason="" if asset_ok else ("asset_registered_but_unresolvable" if asset_id else "no_output_asset_yet"),
            evidence={"asset_id": asset_id, "has_ref": bool(asset_ref)},
        )
    )

    # 3. render -------------------------------------------------------------- #
    output_hash = str(spec.get("output_hash") or rec.get("output_hash") or "")
    render_failed = status in ("failed", "quarantined") and not output_hash
    rows.append(
        _row(
            "render",
            PASSED if output_hash else (FAILED if render_failed else NOT_REACHED),
            at=rec.get("updated_at"),
            reason="" if output_hash else str(rec.get("failure_reason") or "") or ("render_failed" if render_failed else "not_rendered"),
            evidence={
                "output_hash": output_hash[:16],
                "provider": rec.get("provider") or spec.get("provider"),
                "render_duration_ms": rec.get("render_duration_ms"),
            },
        )
    )

    # 4. qa ------------------------------------------------------------------ #
    qa = spec.get("qa_results") or {}
    qa_ok = qa.get("ok") is True
    qa_failed = bool(qa) and qa.get("ok") is not True
    rows.append(
        _row(
            "qa",
            PASSED if qa_ok else (FAILED if qa_failed else NOT_REACHED),
            at=None,
            reason="" if qa_ok else ",".join(str(b) for b in (qa.get("blockers") or []))[:240] or ("qa_failed" if qa_failed else "qa_not_run"),
            evidence={"ok": qa.get("ok"), "degraded": qa.get("degraded") or []},
        )
    )

    # 5. enterprise_grade ---------------------------------------------------- #
    ent = qa.get("enterprise") or {}
    ent_ok = ent.get("customer_approvable") is True
    ent_present = bool(ent)
    rows.append(
        _row(
            "enterprise_grade",
            PASSED if ent_ok else (FAILED if ent_present else NOT_REACHED),
            at=None,
            reason="" if ent_ok else ",".join(str(b) for b in (ent.get("blockers") or []))[:240] or ("enterprise_gate_failed" if ent_present else "enterprise_grade_not_run"),
            evidence={
                "classification": qa.get("classification") or ent.get("classification"),
                "customer_approvable": ent.get("customer_approvable"),
            },
        )
    )

    # 6. approval ------------------------------------------------------------ #
    approval = rec.get("approval") or {}
    approved = str(approval.get("status") or "") == "approved"
    if approved:
        appr_status = PASSED
    elif status == "approval_pending":
        appr_status = PENDING
    elif status in ("changes_requested", "qa_failed", "failed", "quarantined"):
        appr_status = NOT_REACHED
    else:
        appr_status = NOT_REACHED
    rows.append(
        _row(
            "approval",
            appr_status,
            at=approval.get("approved_at"),
            reason="" if approved else (f"awaiting_approval:{status}" if appr_status == PENDING else "not_reached"),
            evidence={
                "status": status,
                "bundle_hash": str(approval.get("bundle_hash") or "")[:16],
                "revision": approval.get("revision"),
            },
        )
    )

    # 7. publish ------------------------------------------------------------- #
    published = status == "published"
    rows.append(
        _row(
            "publish",
            PASSED if published else NOT_REACHED,
            at=None,
            reason="" if published else "not_published",
            evidence={"publish_targets": rec.get("publish_targets") or []},
        )
    )

    # 8. delivery ------------------------------------------------------------ #
    events = _delivery_events(cid)
    delivered_at = ""
    delivered_mid = ""
    for e in events:
        meta = e.get("meta") or {}
        if e.get("event") == "video_delivered" and str(meta.get("creative_id") or "") == crid:
            delivered_at = str(e.get("at") or "")
            delivered_mid = str(meta.get("message_id") or "")
            break
    rows.append(
        _row(
            "delivery",
            PASSED if delivered_at else NOT_REACHED,
            at=delivered_at or None,
            reason="" if delivered_at else "not_delivered",
            evidence={"message_id": delivered_mid},
        )
    )

    # 9. evidence ------------------------------------------------------------ #
    # The evidence bundle is complete only when the three hashes a reviewer
    # needs actually exist: content (output_hash), the approval binding
    # (bundle_hash) and the delivery receipt (message_id).
    bundle_hash = str(approval.get("bundle_hash") or "")
    ev_parts = {
        "output_hash": bool(output_hash),
        "bundle_hash": bool(bundle_hash),
        "delivery_receipt": bool(delivered_mid),
    }
    evidence_ok = all(ev_parts.values())
    rows.append(
        _row(
            "evidence",
            PASSED if evidence_ok else NOT_REACHED,
            at=None,
            reason="" if evidence_ok else "incomplete:" + ",".join(k for k, v in ev_parts.items() if not v),
            evidence=ev_parts,
        )
    )

    failed_stage = _first_unpassed(rows)
    complete = not failed_stage
    out.update(
        {
            "ok": True,
            "stages": rows,
            "failed_stage": failed_stage,
            "complete": complete,
            "status": "complete" if complete else f"stopped_at:{failed_stage}",
        }
    )
    return out


def project_tenant(tenant_id: str, *, limit: int = 20) -> dict[str, Any]:
    """Project the latest ``limit`` creatives for one tenant. Never raises."""
    cid = str(tenant_id or "").strip()
    out: dict[str, Any] = {"ok": True, "tenant_id": cid, "items": [], "counts": {}}
    if not cid:
        out["ok"] = False
        out["error"] = "tenant_id_required"
        return out
    try:
        from app.marketing.creative_os.store import list_records

        listed = list_records(cid, limit=max(1, min(int(limit or 20), 200)))
    except Exception as exc:
        out["ok"] = False
        out["error"] = str(exc)[:160]
        return out
    counts: dict[str, int] = {}
    for item in listed.get("items") or []:
        crid = str(item.get("creative_id") or "")
        if not crid:
            continue
        proj = project(cid, crid)
        if proj.get("ok"):
            stage = proj.get("failed_stage") or "complete"
            counts[stage] = counts.get(stage, 0) + 1
        out["items"].append(
            {
                "creative_id": crid,
                "status": item.get("status"),
                "recipe": item.get("recipe"),
                "failed_stage": proj.get("failed_stage"),
                "complete": proj.get("complete"),
                "stages": proj.get("stages") if proj.get("ok") else [],
            }
        )
    out["counts"] = counts
    return out


def reconcile(*, limit: int = 200) -> dict[str, Any]:
    """Sweep every tenant's creatives and report where each one is STUCK.

    Backs the ``video_lifecycle_reconcile`` scheduler job: one bounded, READ-ONLY
    pass that answers "which videos stopped, and at which stage?" across all
    tenants. It never mutates a record, so a reconcile tick can never change
    state — it only surfaces the projection. Cross-tenant rows are counted per
    tenant id, never merged. Never raises.
    """
    out: dict[str, Any] = {
        "ok": True,
        "tenants": 0,
        "creatives": 0,
        "complete": 0,
        "stuck": {},
        "items": [],
    }
    try:
        from app.marketing.creative_os.store import list_records

        listed = list_records("", limit=max(1, min(int(limit or 200), 500)))
    except Exception as exc:
        out["ok"] = False
        out["error"] = str(exc)[:160]
        return out
    tenants: set[str] = set()
    stuck: dict[str, int] = {}
    for item in listed.get("items") or []:
        cid = str(item.get("tenant_id") or "").strip()
        crid = str(item.get("creative_id") or "").strip()
        if not cid or not crid:
            continue
        tenants.add(cid)
        proj = project(cid, crid)
        if not proj.get("ok"):
            continue
        out["creatives"] += 1
        stage = str(proj.get("failed_stage") or "")
        if not stage:
            out["complete"] += 1
            continue
        stuck[stage] = stuck.get(stage, 0) + 1
        out["items"].append(
            {
                "tenant_id": cid,
                "creative_id": crid,
                "stuck_at": stage,
                "status": proj.get("status"),
            }
        )
    out["tenants"] = len(tenants)
    out["stuck"] = stuck
    return out


__all__ = [
    "FAILED",
    "NOT_REACHED",
    "PASSED",
    "PENDING",
    "STAGES",
    "project",
    "project_tenant",
    "reconcile",
    "stages",
]
