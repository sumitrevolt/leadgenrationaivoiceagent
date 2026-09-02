"""White-label monthly client report — branded HTML "is mahine kya kiya" (retention #1).

Per-client stats best-effort collect (inquiries by source_slug, content packs, bookings,
review requests, coupons) → brand-colored HTML data/client_reports/<id>_<YYYY-MM>.html
→ email (gated `CLIENT_REPORTS=1`; OFF = sirf file banti). NEVER raises.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_OUT_DIR = os.path.join("data", "client_reports")


def _month() -> str:
    return time.strftime("%Y-%m")


def _count_jsonl(path: str, pred) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip() and pred(json.loads(line)))
    except Exception:
        return 0


def collect_stats(client: dict[str, Any], month: str = "") -> dict[str, Any]:
    month = month or _month()
    cid = str(client.get("id") or "")
    slug = str(client.get("slug") or "")

    def in_month(r: dict[str, Any], k: str = "ts") -> bool:
        return str(r.get(k) or r.get("created_at") or "").startswith(month)

    stats = {
        "month": month,
        "inquiries": _count_jsonl(
            os.path.join("data", "inquiries.jsonl"),
            lambda r: in_month(r) and (r.get("source_slug") == slug or r.get("client_id") == cid),
        ),
        "bookings": _count_jsonl(
            os.path.join("data", "bookings.jsonl"), lambda r: in_month(r) and r.get("slug") == slug
        ),
        "review_requests": _count_jsonl(
            os.path.join("data", "review_requests.jsonl"),
            lambda r: in_month(r) and r.get("client_id") == cid,
        ),
        "coupon_redemptions": 0,
        "content_pack": os.path.exists(os.path.join("data", "client_packs", f"{cid}.html")),
    }
    try:
        from app.marketing import loyalty

        stats["coupon_redemptions"] = loyalty.stats(cid)["redemptions"]
    except Exception:
        pass
    return stats


_LEDGER_EVENT_MAP: dict[str, str] = {
    "post_draft_created": "posts_created",
    "post_approved": "posts_approved",
    "post_published": "posts_published",
    "post_failed": "posts_failed",
    "lead_captured": "leads_captured",
    "followup_sent": "followups_sent",
}


def collect_delivery(client_id: str, month: str = "") -> dict[str, Any]:
    """Month-windowed delivery proof from delivery_ledger + GBP audit snapshot.

    Pure read, never raises. Extra keys (gbp_score, approvals_pending) feed the
    Method-12 analytics section of the monthly report without inventing ROAS.
    """
    month = month or _month()
    d: dict[str, Any] = {
        "month": month,
        "posts_created": 0,
        "posts_approved": 0,
        "posts_published": 0,
        "posts_failed": 0,
        "leads_captured": 0,
        "followups_sent": 0,
        "gbp_score": None,
        "approvals_pending": 0,
    }
    try:
        from app.marketing import delivery_ledger

        for e in delivery_ledger.timeline(client_id, limit=10000, customer_only=False):
            if not str(e.get("at") or "").startswith(month):
                continue
            key = _LEDGER_EVENT_MAP.get(str(e.get("event") or ""))
            if key:
                d[key] = int(d[key]) + 1
    except Exception as exc:
        logger.warning(f"collect_delivery failed: {exc}")
    try:
        from app.marketing import product_one_delivery as pod

        audit = pod._gbp_scored_audit(client_id)
        if audit and audit.get("score") is not None:
            d["gbp_score"] = int(audit.get("score") or 0)
    except Exception:
        pass
    try:
        from app.marketing import content_approval

        pending = [
            a
            for a in (content_approval.list_all(client_id, limit=200) or [])
            if str(a.get("status") or "") == "pending"
        ]
        d["approvals_pending"] = len(pending)
    except Exception:
        pass
    gbp_bit = f" GBP audit score {d['gbp_score']}/100." if d.get("gbp_score") is not None else ""
    appr_bit = (
        f" {d['approvals_pending']} posts approval wait me."
        if int(d.get("approvals_pending") or 0) > 0
        else ""
    )
    d["summary_hi"] = (
        f"Is mahine: {d['posts_created']} naye posts bane, "
        f"{d['posts_published']} publish hue, "
        f"{d['leads_captured']} naye leads aaye."
        f"{gbp_bit}{appr_bit}"
    )
    return d


def _next_actions(delivery: dict[str, Any], client: dict[str, Any]) -> list[str]:
    """Small Hinglish next-step list for the report. Never raises."""
    actions: list[str] = []
    try:
        failed = int(delivery.get("posts_failed", 0) or 0)
        created = int(delivery.get("posts_created", 0) or 0)
        approved = int(delivery.get("posts_approved", 0) or 0)
        pending = max(0, created - approved)
        socials = client.get("socials") if isinstance(client.get("socials"), dict) else {}
        has_channel = any(
            str(socials.get(k) or "").strip() for k in ("instagram", "facebook", "gbp")
        )
        if failed > 0:
            actions.append("Kuch posts publish nahi ho paaye - team ise theek kar rahi hai.")
        if pending > 0:
            actions.append(
                f"{pending} post approval ke intezaar me - approve karein taaki publish ho saken."
            )
        if not has_channel:
            actions.append(
                "Instagram / Google Business profile link karein taaki publishing smooth ho."
            )
        if not actions:
            actions.append(
                "Sab set hai - agle mahine festival posts aur review replies par focus rahega."
            )
    except Exception as exc:
        logger.warning(f"next_actions failed: {exc}")
    return actions[:4]


def _render_html(
    client: dict[str, Any],
    s: dict[str, Any],
    delivery: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
) -> str:
    brand = client.get("brand") if isinstance(client.get("brand"), dict) else {}
    primary = brand.get("primary") or "#2563eb"
    name = client.get("business_name") or "Client"
    rows = [
        ("📥 Nayi inquiries / leads", s["inquiries"]),
        ("📅 Bookings", s["bookings"]),
        ("⭐ Review requests bheje", s["review_requests"]),
        ("🎁 Coupon redemptions", s["coupon_redemptions"]),
        ("📱 Content pack ready", "Haan" if s["content_pack"] else "—"),
    ]
    trs = "".join(
        f"<tr><td style='padding:10px 14px;border-bottom:1px solid #eee'>{k}</td>"
        f"<td style='padding:10px 14px;border-bottom:1px solid #eee;font-weight:700;text-align:right'>{v}</td></tr>"
        for k, v in rows
    )
    delivery = delivery or {}
    next_actions = next_actions or []
    d_rows = [
        ("Naye posts bane", delivery.get("posts_created", 0)),
        ("Posts approve hue", delivery.get("posts_approved", 0)),
        ("Posts publish hue", delivery.get("posts_published", 0)),
        ("Naye leads captured", delivery.get("leads_captured", 0)),
        ("Follow-ups bheje", delivery.get("followups_sent", 0)),
        (
            "GBP audit score",
            (
                f"{delivery.get('gbp_score')}/100"
                if delivery.get("gbp_score") is not None
                else "— (Reports → GBP Audit)"
            ),
        ),
        ("Pending approvals", delivery.get("approvals_pending", 0)),
    ]
    d_trs = "".join(
        f"<tr><td style='padding:10px 14px;border-bottom:1px solid #eee'>{k}</td>"
        f"<td style='padding:10px 14px;border-bottom:1px solid #eee;font-weight:700;text-align:right'>{v}</td></tr>"
        for k, v in d_rows
    )
    summary_hi = str(delivery.get("summary_hi") or "")
    summary_block = (
        f"<div style='padding:14px 24px;background:#f0f7ff;color:#064e3b;font-size:14px;font-weight:600'>{summary_hi}</div>"
        if summary_hi
        else ""
    )
    delivery_block = (
        "<div style='padding:14px 24px 4px;color:#333;font-weight:700;font-size:14px'>"
        f"AI team ne is mahine kya kiya</div><table style='width:100%;border-collapse:collapse;font-size:15px'>{d_trs}</table>"
    )
    na_items = "".join(f"<li style='margin:4px 0'>{a}</li>" for a in next_actions)
    next_block = (
        "<div style='padding:14px 24px 4px;color:#333;font-weight:700;font-size:14px'>Agle steps</div>"
        f"<ul style='margin:0 0 8px;padding:0 24px 0 40px;color:#444;font-size:14px'>{na_items}</ul>"
        if na_items
        else ""
    )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px">
<div style="max-width:560px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07)">
<div style="background:{primary};color:#fff;padding:22px 24px">
<h2 style="margin:0">{name}</h2><div style="opacity:.9">Monthly Marketing Report — {s["month"]}</div></div>
{summary_block}
<table style="width:100%;border-collapse:collapse;font-size:15px">{trs}</table>
{delivery_block}
{next_block}
<div style="padding:18px 24px;color:#555;font-size:13px">Aapki AI marketing team ne yeh sab automate kiya 🤖 —
posts, follow-ups, reviews aur leads. Sawal ho to reply karo.<br><br>— Team LeadsGenAI · leadsgenai.in</div>
</div></body></html>"""


async def build_report(client_id: str, month: str = "", send: bool | None = None) -> dict[str, Any]:
    """Report HTML banao (+email agar CLIENT_REPORTS=1 ya send=True aur client email ho)."""
    try:
        from app.marketing import clients_store

        # Billing alias (invoice id) → canonical marketing client id
        client = clients_store.resolve_client(client_id) or clients_store.get_client(client_id)
        if not client:
            return {"ok": False, "error": "client not found"}
        cid = str(client.get("id") or client_id).strip()
        month = month or _month()
        s = collect_stats(client, month)
        delivery = collect_delivery(cid, month)
        next_actions_hi = _next_actions(delivery, client)
        html = _render_html(client, s, delivery, next_actions_hi)
        os.makedirs(_OUT_DIR, exist_ok=True)
        path = os.path.join(_OUT_DIR, f"{cid}_{month}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        emailed = False
        flag = (os.getenv("CLIENT_REPORTS") or "").strip().lower() in ("1", "true", "yes")
        do_send = flag if send is None else bool(send)
        to = str(client.get("email") or "").strip()
        if do_send and to:
            try:
                from app.integrations.email_sender import email_sender

                emailed = bool(
                    await email_sender.send_email(
                        [to], f"📊 {client.get('business_name')} — Marketing Report {month}", html
                    )
                )
            except Exception as e:
                logger.warning(f"report email failed: {e}")
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                cid, "weekly_report_generated", detail=month, key=f"report:{cid}:{month}"
            )
        except Exception:
            pass
        return {
            "ok": True,
            "path": path,
            "client_id": cid,
            "stats": s,
            "delivery": delivery,
            "next_actions_hi": next_actions_hi,
            "emailed": emailed,
        }
    except Exception as e:
        logger.warning(f"build_report failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


async def run_monthly(send: bool | None = None) -> dict[str, Any]:
    """Saare active clients ke liye (mahine ke pehle hafte me chalana)."""
    try:
        from app.marketing import clients_store

        out = []
        for c in clients_store.list_clients():
            cid = str(c.get("id") or "")
            r = await build_report(cid, send=send)
            out.append({"client_id": c.get("id"), "ok": r.get("ok"), "emailed": r.get("emailed")})
            # Per-customer automation-log row (ADR-065 deeper logs). Platform jobs
            # log blank client_id, so the admin Automation Runs "customer" filter
            # was useless. Attribute this report run to THIS client + surface the
            # generated report file path as proof in output_summary. Never break loop.
            try:
                from app.platform.automation_log_service import log_event as _log_auto

                _ok = bool(r.get("ok"))
                _path = str(r.get("path") or "")
                _log_auto(
                    client_id=cid,
                    job_type="client_report",
                    status="success" if _ok else "failed",
                    output_summary=(
                        (("report: " + _path) if _path else "report generated")
                        if _ok
                        else str(r.get("error") or "report failed")[:200]
                    ),
                    error_message="" if _ok else str(r.get("error") or "")[:500],
                    evidence_url=_path if _ok else "",  # ADR-068: report file = proof artifact
                    triggered_by="scheduler",
                    meta_json={"emailed": bool(r.get("emailed")), "path": _path},
                )
            except Exception:
                pass
        return {"ok": True, "reports": out}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}
