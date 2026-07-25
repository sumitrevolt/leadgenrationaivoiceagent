"""Fail-closed publish gate — approval must bind to exact video version."""

from __future__ import annotations

from typing import Any

from app.marketing.video_production import flags, states


def assert_can_publish(rec: dict[str, Any]) -> dict[str, Any]:
    """Return {ok:True} or {ok:False, error:...}. Never raises."""
    try:
        if flags.production_enabled() and not flags.social_publish_enabled():
            return {"ok": False, "error": "VIDEO_SOCIAL_PUBLISH_ENABLED off"}

        if flags.own_brand_enabled():
            from app.marketing.video_production.allowlist import assert_own_brand_allowlist

            allow = assert_own_brand_allowlist(str(rec.get("client_id") or ""))
            if not allow.get("ok"):
                return allow

        ok, reason = states.publish_allowed(rec)
        if not ok:
            return {"ok": False, "error": reason}

        # Exact-version binding: approved_version must match revision when set
        av = rec.get("approved_version")
        if av is not None and int(av) != int(rec.get("revision") or 0):
            return {
                "ok": False,
                "error": "version_mismatch",
                "approved_version": av,
                "current_revision": rec.get("revision"),
            }

        # Editing after approve invalidates — status must still be approved
        if str(rec.get("status") or "") not in ("approved",):
            if str(rec.get("workflow_state") or "") not in (
                states.APPROVED,
                states.SCHEDULED,
            ):
                return {"ok": False, "error": f"status_not_approved:{rec.get('status')}"}

        if rec.get("final_approved") is False:
            return {"ok": False, "error": "final_approved_false"}

        return {"ok": True, "version": int(rec.get("revision") or 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def mark_version_approved(rec_id: str, revision: int) -> None:
    """Bind approval evidence to exact revision (immutable)."""
    try:
        from app.marketing import video_ad_cycle

        video_ad_cycle._update(
            rec_id,
            approved_version=int(revision),
            final_approved=True,
            workflow_state=states.APPROVED,
            status="approved",
        )
    except Exception:
        pass


__all__ = ["assert_can_publish", "mark_version_approved"]
