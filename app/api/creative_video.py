"""Creative Video Command Center — read-only L1→L4 admin API for the video pipeline.

Self-contained router mounted at ``/api/admin/video``. Every response uses the
envelope ``{"ok": bool, "data": <payload>, "error": <str|null>}``.

Design constraints honoured
---------------------------
* **C4 — server-side tenant scoping.** A tenant id is only ever a FILTER over the
  tenants this server already owns (the union of the video stores). A tenant the
  server does not own yields an honest empty — never another tenant's data. The
  client can never name a tenant to widen its reach.
* **C3 — no secret is echoed.** Bot tokens, raw chat ids and JWT material never
  appear in any payload; delivery bindings are surfaced masked only.
* **Read-only GETs.** Every GET is side-effect-free and safe to poll. The single
  mutating endpoint is ``POST /generate`` and it is flag-gated + fail-closed.
* **Never raises.** Each block is individually guarded so partial data is fine.

Rollback: remove the ``creative_video`` include_router block and the
``/app/admin/video`` page route from ``app/main.py``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/video", tags=["Admin Video"])

#: The ONLY evidence vocabulary this surface may emit.
EVIDENCE_LABELS = (
    "PRODUCTION-PROVEN",
    "CODE-PROVEN",
    "TEST-PROVEN",
    "LOCAL-ONLY",
    "PARTIAL",
    "STALE",
    "UNKNOWN",
)

#: A tenant whose sanitised store segment collapses to this is not a real tenant.
_INVALID_SEGMENT = "_invalid"


# --------------------------------------------------------------------------- #
# Envelope + small helpers
# --------------------------------------------------------------------------- #
def _ok(data: Any) -> dict[str, Any]:
    """Success envelope."""
    return {"ok": True, "data": data, "error": None}


def _err(msg: str, data: Any = None) -> dict[str, Any]:
    """Failure envelope. `ok` is False so a caller can never mistake it for success."""
    return {"ok": False, "data": data, "error": str(msg)[:240]}


def _tenant_ids() -> list[str]:
    """Tenants this SERVER owns — union of the video stores. Never raises.

    This is the C4 authority: the server enumerates its own tenants; a client
    never supplies the scoping set.
    """
    ids: set[str] = set()
    try:
        from app.marketing.creative_os import store as _store

        root = _store._root()
        if os.path.isdir(root):
            for name in os.listdir(root):
                if os.path.isdir(os.path.join(root, name)):
                    ids.add(name)
    except Exception as exc:  # noqa: BLE001 - partial data is acceptable
        logger.debug("tenant scan (creative store) failed: %s", exc)
    try:
        from app.marketing import delivery_ledger

        ledger_dir = delivery_ledger._LEDGER_DIR()
        if os.path.isdir(ledger_dir):
            for name in os.listdir(ledger_dir):
                if name.endswith(".jsonl"):
                    ids.add(name[: -len(".jsonl")])
    except Exception as exc:  # noqa: BLE001
        logger.debug("tenant scan (ledger) failed: %s", exc)
    return sorted(i for i in ids if i and i != _INVALID_SEGMENT)


def _timeline_row(rec: dict[str, Any]) -> dict[str, Any]:
    """Map one ledger event to the L3 timeline row contract.

    ``label_hi`` is the Hinglish customer label (present only on the
    ``customer_only`` view); ``message_id`` is the Telegram delivery receipt.
    """
    meta = rec.get("meta") or {}
    return {
        "event": str(rec.get("event") or ""),
        "at": rec.get("at"),
        "label_hi": str(rec.get("label") or ""),
        "customer_visible": bool(rec.get("customer_visible")),
        "message_id": str(meta.get("message_id") or "") or None,
    }


def _network_isolation() -> dict[str, Any]:
    """Honest network-isolation state for the evidence panel.

    T02 ships isolation as a PROBE only, so today this reports
    ``enforced: False`` -> the panel labels it PARTIAL. We never claim the word
    "hermetic"; the only honest claim is what the probe can prove.
    """
    method = ""
    enforced = False
    try:
        from app.marketing.creative_os import network_guard  # T02-owned module

        for attr in ("isolation_method", "method", "METHOD"):
            value = getattr(network_guard, attr, None)
            if isinstance(value, str) and value.strip():
                method = value.strip()
                break
        probe = getattr(network_guard, "is_enforced", None)
        if callable(probe):
            enforced = bool(probe())
        else:
            enforced = bool(getattr(network_guard, "ENFORCED", False))
    except Exception as exc:  # noqa: BLE001 - module may not exist yet
        logger.debug("network_guard probe unavailable: %s", exc)
    return {"method": method or "probe-only", "enforced": bool(enforced)}


def _evidence_label(evidence_complete: bool, isolation: dict[str, Any]) -> str:
    """The single overall evidence label. Missing evidence is UNKNOWN, not PROVEN."""
    if not evidence_complete:
        return "UNKNOWN"
    if not bool((isolation or {}).get("enforced")):
        return "PARTIAL"
    return "PRODUCTION-PROVEN"


# --------------------------------------------------------------------------- #
# L1 — end-to-end automation health
# --------------------------------------------------------------------------- #
@router.get("/health", response_model=None)
async def video_health_l1(_user=Depends(require_admin)) -> dict[str, Any]:
    """L1 — end-to-end video automation health.

    Surfaces ``video_health.health()`` verbatim, including the **ran vs produced**
    split: a job that only has a heartbeat is ``warn``, never ``ok``. A
    liveness-only number here would be the exact fake-green this project keeps
    getting burned by, so the two signals are passed through, never collapsed.
    """
    try:
        from app.marketing import video_health

        data = video_health.health()
    except Exception as exc:  # noqa: BLE001
        logger.debug("video health probe failed: %s", exc)
        return _err(f"health_probe_failed: {exc}")
    return _ok(data)


# --------------------------------------------------------------------------- #
# L2 — tenant cards
# --------------------------------------------------------------------------- #
@router.get("/customers", response_model=None)
async def video_customers_l2(_user=Depends(require_admin)) -> dict[str, Any]:
    """L2 — one card per tenant the SERVER owns. Honest empty when there are none.

    No tenants is a valid, successful state: ``ok:true`` with an empty list — not
    a fabricated placeholder row.
    """
    cards: list[dict[str, Any]] = []
    for tid in _tenant_ids():
        card: dict[str, Any] = {"tenant_id": tid}
        try:
            from app.marketing.creative_os import lifecycle

            proj = lifecycle.project_tenant(tid, limit=50)
            counts = proj.get("counts") or {}
            card["creatives"] = len(proj.get("items") or [])
            card["complete"] = int(counts.get("complete", 0) or 0)
            card["stuck"] = {k: v for k, v in counts.items() if k != "complete"}
        except Exception as exc:  # noqa: BLE001
            card["lifecycle_error"] = str(exc)[:120]
        try:
            from app.marketing import delivery_ledger

            s = delivery_ledger.summary(tid)
            card["events_total"] = s.get("events_total")
            card["value_delivered"] = bool(s.get("value_delivered"))
            card["last_event_at"] = s.get("last_event_at")
        except Exception as exc:  # noqa: BLE001
            card["ledger_error"] = str(exc)[:120]
        try:
            from app.marketing import video_delivery

            ds = video_delivery.delivery_status(tid)
            card["delivery_enabled"] = bool(ds.get("enabled"))
            card["bound"] = bool((ds.get("binding") or {}).get("bound"))
            card["pending_retries"] = int((ds.get("retry_queue") or {}).get("pending", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            card["delivery_error"] = str(exc)[:120]
        cards.append(card)
    return _ok({"tenants": cards, "count": len(cards)})


# --------------------------------------------------------------------------- #
# L3 — lifecycle detail + customer timeline
# --------------------------------------------------------------------------- #
@router.get("/customers/{tenant_id}", response_model=None)
async def video_customer_l3(tenant_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    """L3 — 9-stage lifecycle + the CUSTOMER-facing timeline for one tenant.

    C4: ``tenant_id`` is accepted only when the SERVER owns it. An unknown or
    foreign id returns ``found:false`` (honest empty) — never another tenant's
    data, and never a 500.

    The customer timeline uses ``customer_only=True`` so genuine delivery is keyed
    on ``video_delivered`` only. ``video_delivered_ops`` (internal ops-group
    receipt, ``customer_visible=False``) is surfaced SEPARATELY under
    ``ops_timeline`` and must never be rendered as a customer delivery.
    """
    tid = str(tenant_id or "").strip()
    owned = _tenant_ids()
    if not tid or tid not in owned:
        return _ok(
            {
                "tenant_id": tid,
                "found": False,
                "reason": "tenant_not_owned_by_server",
                "timeline": [],
                "ops_timeline": [],
            }
        )

    detail: dict[str, Any] = {"tenant_id": tid, "found": True}
    try:
        from app.marketing.creative_os import lifecycle

        detail["lifecycle"] = lifecycle.project_tenant(tid, limit=20)
    except Exception as exc:  # noqa: BLE001
        detail["lifecycle_error"] = str(exc)[:160]
    try:
        from app.marketing import delivery_ledger

        # Customer view — Hinglish labels, customer_visible events only.
        customer_rows = delivery_ledger.timeline(tid, limit=50, customer_only=True)
        detail["timeline"] = [_timeline_row(r) for r in customer_rows]
        # Internal/ops view — admin English labels, NON-customer-visible events only.
        full_rows = delivery_ledger.timeline(tid, limit=80)
        detail["ops_timeline"] = [
            _timeline_row(r) for r in full_rows if not r.get("customer_visible")
        ]
    except Exception as exc:  # noqa: BLE001
        detail["timeline_error"] = str(exc)[:160]
        detail.setdefault("timeline", [])
        detail.setdefault("ops_timeline", [])
    try:
        from app.marketing import video_delivery

        detail["delivery"] = video_delivery.delivery_status(tid)
    except Exception as exc:  # noqa: BLE001
        detail["delivery_error"] = str(exc)[:160]
    return _ok(detail)


# --------------------------------------------------------------------------- #
# L4 — evidence panel
# --------------------------------------------------------------------------- #
def _find_creative_for_asset(asset_id: str) -> tuple[str, str]:
    """Locate the (tenant, creative) whose output asset is ``asset_id``.

    Scans ONLY server-owned tenants (C4). Returns ``("", "")`` when not found.
    """
    try:
        from app.marketing.creative_os import store as _store
    except Exception:
        return "", ""
    for tid in _tenant_ids():
        try:
            listed = _store.list_records(tid, limit=200)
        except Exception:
            continue
        for item in listed.get("items") or []:
            crid = str(item.get("creative_id") or "")
            if not crid:
                continue
            try:
                got = _store.get_record(tid, crid)
            except Exception:
                continue
            if not got.get("ok"):
                continue
            rec = got.get("record") or {}
            spec = rec.get("spec") or {}
            if str(spec.get("output_asset_id") or rec.get("output_asset_id") or "") == asset_id:
                return tid, crid
    return "", ""


def _evidence_panel(tenant_id: str, creative_id: str, asset_id: str) -> dict[str, Any]:
    """Assemble the L4 evidence panel from the lifecycle projection.

    The three hashes a reviewer needs live on different lifecycle stages: the
    content hash on ``render``, the approval binding on ``approval`` and the
    delivery receipt on ``delivery``. The ``evidence`` stage carries only their
    PRESENCE flags — we read the values from the stages that actually hold them.
    """
    panel: dict[str, Any] = {
        "tenant_id": tenant_id,
        "creative_id": creative_id,
        "asset_id": asset_id,
        "output_hash": "",
        "bundle_hash": "",
        "message_id": "",
        "evidence_complete": False,
    }
    try:
        from app.marketing.creative_os import lifecycle

        proj = lifecycle.project(tenant_id, creative_id)
        stages = {str(r.get("stage")): r for r in (proj.get("stages") or [])}
        render_ev = (stages.get("render") or {}).get("evidence") or {}
        approval_ev = (stages.get("approval") or {}).get("evidence") or {}
        delivery_ev = (stages.get("delivery") or {}).get("evidence") or {}
        evidence_ev = (stages.get("evidence") or {}).get("evidence") or {}
        panel["output_hash"] = str(render_ev.get("output_hash") or "")
        panel["bundle_hash"] = str(approval_ev.get("bundle_hash") or "")
        panel["message_id"] = str(delivery_ev.get("message_id") or "")
        panel["evidence_complete"] = bool(
            evidence_ev.get("output_hash")
            and evidence_ev.get("bundle_hash")
            and evidence_ev.get("delivery_receipt")
        )
        panel["lifecycle_status"] = proj.get("status")
        panel["failed_stage"] = proj.get("failed_stage")
    except Exception as exc:  # noqa: BLE001
        panel["error"] = str(exc)[:160]
    isolation = _network_isolation()
    panel["network_isolation"] = isolation
    panel["label"] = _evidence_label(bool(panel.get("evidence_complete")), isolation)
    return panel


@router.get("/assets/{asset_id}", response_model=None)
async def video_asset_l4(asset_id: str, _user=Depends(require_admin)) -> dict[str, Any]:
    """L4 — evidence panel for one asset.

    C4: the client supplies an asset id, never a tenant; the server searches only
    its OWN tenants. Not found is an honest empty (``found:false``), never a
    fabricated row.
    """
    aid = str(asset_id or "").strip()
    if not aid:
        return _err("asset_id_required")
    tid, crid = _find_creative_for_asset(aid)
    if not tid:
        return _ok(
            {
                "asset_id": aid,
                "found": False,
                "evidence": None,
                "network_isolation": _network_isolation(),
                "label": "UNKNOWN",
            }
        )
    return _ok({"asset_id": aid, "found": True, "evidence": _evidence_panel(tid, crid, aid)})


# --------------------------------------------------------------------------- #
# POST /generate — the single mutating endpoint (flag-gated, fail-closed)
# --------------------------------------------------------------------------- #
@router.post("/generate", response_model=None)
async def video_generate(
    tenant_id: str = Query(..., description="target tenant (validated server-side)"),
    business_name: str = Query("", description="verified business name for the brief"),
    recipe: str = Query("offer_announcement"),
    niche: str = Query("general"),
    platform: str = Query("instagram"),
    aspect_ratio: str = Query("9:16"),
    language: str = Query("hinglish"),
    offer: str = Query(""),
    cta: str = Query(""),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Enqueue a creative generation for one tenant.

    The ONLY mutating endpoint. Flag-gated on the existing creative-OS master
    gate (``CREATIVE_OS_ENABLED``) and fail-closed: gate off (or unreadable) =>
    honest ``{ok:false, error:...}``, never a fake success and never an
    unhandled raise. ``enqueue_generate`` re-checks the same gate internally.
    """
    try:
        from app.marketing.creative_os import flags as _flags

        if not _flags.os_enabled():
            return _err("generation disabled: CREATIVE_OS_ENABLED off")
    except Exception as exc:  # noqa: BLE001 - unreadable gate must fail CLOSED
        return _err(f"generation gate unavailable (fail-closed): {exc}")

    tid = str(tenant_id or "").strip()
    if not tid:
        return _err("tenant_id_required")
    if tid not in _tenant_ids():
        return _err("tenant_not_owned_by_server")

    try:
        from app.marketing.creative_os import service

        result = service.enqueue_generate(
            tenant_id=tid,
            business_name=str(business_name or ""),
            recipe=str(recipe or "offer_announcement"),
            offer=str(offer or ""),
            niche=str(niche or "general"),
            language=str(language or "hinglish"),
            platform=str(platform or "instagram"),
            aspect_ratio=str(aspect_ratio or "9:16"),
            cta=str(cta or ""),
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("enqueue_generate failed: %s", exc)
        return _err(f"enqueue_failed: {exc}")

    if not isinstance(result, dict) or not result.get("ok"):
        reason = ""
        if isinstance(result, dict):
            reason = str(result.get("error") or result.get("outcome") or "")
        return _err(reason or "enqueue_rejected", data={"tenant_id": tid})
    return _ok({"tenant_id": tid, "enqueued": True, "result": result})


__all__ = ["EVIDENCE_LABELS", "router"]
