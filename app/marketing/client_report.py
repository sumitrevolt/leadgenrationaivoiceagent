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
    in_month = lambda r, k="ts": str(r.get(k) or r.get("created_at") or "").startswith(
        month
    )  # noqa: E731
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


def _render_html(client: dict[str, Any], s: dict[str, Any]) -> str:
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
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f6f7fb;margin:0;padding:24px">
<div style="max-width:560px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.07)">
<div style="background:{primary};color:#fff;padding:22px 24px">
<h2 style="margin:0">{name}</h2><div style="opacity:.9">Monthly Marketing Report — {s['month']}</div></div>
<table style="width:100%;border-collapse:collapse;font-size:15px">{trs}</table>
<div style="padding:18px 24px;color:#555;font-size:13px">Aapki AI marketing team ne yeh sab automate kiya 🤖 —
posts, follow-ups, reviews aur leads. Sawal ho to reply karo.<br><br>— Team LeadsGenAI · leadsgenai.in</div>
</div></body></html>"""


async def build_report(client_id: str, month: str = "", send: bool | None = None) -> dict[str, Any]:
    """Report HTML banao (+email agar CLIENT_REPORTS=1 ya send=True aur client email ho)."""
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(client_id)
        if not client:
            return {"ok": False, "error": "client not found"}
        month = month or _month()
        s = collect_stats(client, month)
        html = _render_html(client, s)
        os.makedirs(_OUT_DIR, exist_ok=True)
        path = os.path.join(_OUT_DIR, f"{client_id}_{month}.html")
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

            delivery_ledger.log_event(client_id, "weekly_report_generated", detail=month)
        except Exception:
            pass
        return {"ok": True, "path": path, "stats": s, "emailed": emailed}
    except Exception as e:
        logger.warning(f"build_report failed: {e}")
        return {"ok": False, "error": str(e)[:150]}


async def run_monthly(send: bool | None = None) -> dict[str, Any]:
    """Saare active clients ke liye (mahine ke pehle hafte me chalana)."""
    try:
        from app.marketing import clients_store

        out = []
        for c in clients_store.list_clients():
            r = await build_report(str(c.get("id")), send=send)
            out.append({"client_id": c.get("id"), "ok": r.get("ok"), "emailed": r.get("emailed")})
        return {"ok": True, "reports": out}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}
