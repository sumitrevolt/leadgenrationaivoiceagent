"""GST-compliant invoice engine — revenue loop ka missing piece (payment hota tha, invoice nahi banta tha).

Research (Rule 46 CGST, June 2026): unique sequential number ≤16 chars per FY
(`INV/2026-27/0001`), SAC SaaS = 998313, intra-state = CGST 9% + SGST 9%,
inter-state = IGST 18%. GST registration sirf >₹20L services turnover pe
mandatory — tab tak GSTIN unset rakho aur invoice BINA tax-lines banta hai
("GST not applicable — unregistered"). E-invoicing IRP threshold ₹5Cr — irrelevant.
GST invoice fields per CGST Rule-46 (statutory mandatory fields — public-domain schema, clean-room implementation).

Design:
  - Store: data/invoices.jsonl (append; numbering = FY-count+1, file_lock atomic).
  - Amount: charged plan price = GROSS (inclusive). Registered mode me taxable
    back-calculate hota hai (gross/1.18) — jo actually pay hua wahi invoice total.
  - Place of supply: client `state_code` (clients_store, optional) vs supplier
    `GST_SUPPLIER_STATE_CODE` (default 27 = Maharashtra). Match/blank = intra.
  - Hook: app/api/billing._provision_usage (saare gateways ka single choke-point)
    -> on_payment_success() — payment_ref/period dedupe (double webhooks safe).
  - Email send GATED `AUTO_INVOICE=1` (record HAMESHA banta — additive, send nahi).

Env (sab optional): GST_SUPPLIER_NAME, GST_GSTIN, GST_SUPPLIER_ADDRESS,
GST_SUPPLIER_STATE_CODE, AUTO_INVOICE. Kabhi raise nahi karta.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _STORE() -> str:
    """GST invoice ledger — resolved per call, never frozen at import."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="billing.invoices",
            legacy_path=Path("data") / "invoices.jsonl",
            target_segments=("billing", "invoices.jsonl"),
        )
    )


def _lock_path() -> str:
    """Lock beside the ACTIVE invoice ledger (follows monkeypatched ``_STORE``)."""
    from app.platform import runtime_data_authority as _auth

    store = _STORE()
    auth_store = str(
        _auth.resolve_store_path(
            store_id="billing.invoices",
            legacy_path=Path("data") / "invoices.jsonl",
            target_segments=("billing", "invoices.jsonl"),
        )
    )
    try:
        same = os.path.normpath(store) == os.path.normpath(auth_store)
    except Exception:
        same = False
    if same:
        return str(
            _auth.resolve_lock_path(
                store_id="billing.invoices",
                legacy_path=Path("data") / "invoices.jsonl",
                target_segments=("billing", "invoices.jsonl"),
            )
        )
    return store + ".lock"


SAC_CODE = "998313"  # IT/cloud services (SaaS)
GST_RATE = 0.18
SUPPORT_EMAIL = "admin@leadsgenai.in"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _send_enabled() -> bool:
    return os.environ.get("AUTO_INVOICE", "0").strip().lower() in ("1", "true", "yes")


def _supplier() -> dict[str, str]:
    return {
        "name": os.environ.get("GST_SUPPLIER_NAME", "LeadsGenAI").strip(),
        "gstin": os.environ.get("GST_GSTIN", "").strip().upper(),
        "address": os.environ.get("GST_SUPPLIER_ADDRESS", "Mumbai, Maharashtra, India").strip(),
        "state_code": os.environ.get("GST_SUPPLIER_STATE_CODE", "27").strip(),
        "email": SUPPORT_EMAIL,
    }


def fy_label(when: datetime | None = None) -> str:
    """India FY (Apr-Mar) label, e.g. 2026-06 -> '2026-27'."""
    d = when or _now()
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _read() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        # Resolver at each I/O site — binding to a local re-attributes the
        # scanner finding and unbinds the allowlist (A3 lesson).
        if os.path.exists(_STORE()):
            with open(_STORE(), encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _append(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STORE()) or ".", exist_ok=True)
        with open(_STORE(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[invoice] append failed: {e}")


def _void_map(rows: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """number -> void-marker record. Void markers = append-only rows with
    ``kind: "void"`` + ``voids: <number>`` (2026-07-18 accountant-safe correction:
    Rule-46 sequential ledger me DELETE forbidden — original row preserved, number
    consumed rehta hai, reporting/dedupe voided ko exclude karti hai)."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows if rows is not None else _read():
        if r.get("kind") == "void" and r.get("voids"):
            out[str(r["voids"])] = r
    return out


def next_number(fy: str | None = None) -> str:
    """Sequential per-FY number, Rule 46 compliant (<=16 chars): INV/2026-27/0001.

    NOTE: count-based; MUST be called inside ``_reserve_number_and_append`` so the
    read-count and the append are atomic — otherwise two concurrent invoices compute
    the same number (duplicate Rule-46 number = GST violation). Void markers carry
    no ``fy`` key, so they never inflate the count; voided invoices DO keep their
    number consumed (no reuse)."""
    fy = fy or fy_label()
    n = sum(1 for r in _read() if r.get("fy") == fy) + 1
    return f"INV/{fy}/{n:04d}"


_LOCK = threading.Lock()


def _reserve_number_and_append(inv: dict[str, Any], fy: str) -> None:
    """Atomically assign the next per-FY number and append the record. Cross-process
    safe via an flock on a sidecar lock file (Linux/prod, e.g. Celery prefork + uvicorn
    workers); the threading.Lock covers in-process; both degrade gracefully where flock
    is unavailable (Windows dev)."""
    # Resolver at each I/O site — do not bind to a local (A3 allowlist lesson).
    with _LOCK:
        fh = None
        try:
            os.makedirs(os.path.dirname(_STORE()) or ".", exist_ok=True)
            try:
                import fcntl

                fh = open(_lock_path(), "w")
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except Exception:
                fh = None  # no fcntl (Windows) — in-process _LOCK still applies
            inv["number"] = next_number(fy)
            _append(inv)
        finally:
            if fh is not None:
                try:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                    fh.close()
                except Exception:
                    pass


def _plan_amount(plan: str) -> int:
    try:
        from app.marketing.packages import PACKAGES

        for p in PACKAGES:
            if p.get("key") == (plan or "").strip().lower():
                return int(p.get("price_inr_month") or 0)
    except Exception:
        pass
    return 0


def _client(client_id: str) -> dict[str, Any]:
    try:
        from app.marketing.clients_store import get_client

        return get_client(str(client_id)) or {}
    except Exception:
        return {}


def _tax_lines(gross: float, recipient_state: str, supplier: dict[str, str]) -> dict[str, Any]:
    """Tax breakdown. Supplier GSTIN unset => unregistered (no tax lines)."""
    if not supplier.get("gstin"):
        return {
            "tax_mode": "unregistered",
            "taxable_value": round(gross, 2),
            "cgst": 0.0,
            "sgst": 0.0,
            "igst": 0.0,
            "note": "GST not applicable — supplier not registered under GST (turnover below threshold).",
        }
    taxable = round(gross / (1 + GST_RATE), 2)
    tax = round(gross - taxable, 2)
    intra = (not recipient_state) or recipient_state == supplier.get("state_code")
    if intra:
        half = round(tax / 2, 2)
        return {
            "tax_mode": "intra",
            "taxable_value": taxable,
            "cgst": half,
            "sgst": round(tax - half, 2),
            "igst": 0.0,
            "note": "",
        }
    return {
        "tax_mode": "inter",
        "taxable_value": taxable,
        "cgst": 0.0,
        "sgst": 0.0,
        "igst": tax,
        "note": "",
    }


def create_invoice(
    client_id: str,
    plan: str,
    amount_inr: float | None = None,
    payment_ref: str = "",
    gateway: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Invoice record banao (store + return). Best-effort, kabhi raise nahi ({} on hard fail)."""
    try:
        cid = (client_id or "").strip()
        plan_k = (plan or "").strip().lower()
        gross = float(amount_inr if amount_inr is not None else _plan_amount(plan_k))
        if gross <= 0:
            return {}
        sup = _supplier()
        cl = _client(cid)
        rstate = str(cl.get("state_code") or "").strip()
        now = _now()
        fy = fy_label(now)
        inv = {
            "number": "",  # assigned atomically below (race-safe)
            "fy": fy,
            "date": now.strftime("%Y-%m-%d"),
            "created_at": now.isoformat(),
            "client_id": cid,
            "recipient": {
                "name": str(cl.get("business_name") or cl.get("name") or cid),
                "gstin": str(cl.get("gstin") or "").strip().upper(),
                "address": str(cl.get("address") or cl.get("city") or ""),
                "state_code": rstate,
                "email": str(cl.get("email") or ""),
            },
            "supplier": sup,
            "sac_code": SAC_CODE,
            "description": description or f"LeadsGenAI subscription — {plan_k or 'plan'} (monthly)",
            "plan": plan_k,
            "gross_inr": round(gross, 2),
            "place_of_supply": rstate or sup["state_code"],
            "reverse_charge": False,
            "payment_ref": payment_ref,
            "gateway": gateway,
            **_tax_lines(gross, rstate, sup),
        }
        _reserve_number_and_append(inv, fy)
        logger.info(f"[invoice] {inv['number']} client={cid} plan={plan_k} ₹{gross}")
        return inv
    except Exception as e:
        logger.warning(f"[invoice] create failed: {e}")
        return {}


def invoice_html(inv: dict[str, Any]) -> str:
    """Self-contained printable HTML invoice (brandable, GST-format)."""
    try:
        import html as _h

        e = _h.escape
        sup, rec = inv.get("supplier", {}), inv.get("recipient", {})
        rows = (
            f"<tr><td>{e(str(inv.get('description', '')))}<br><small>SAC: {e(str(inv.get('sac_code', '')))}</small></td>"
            f'<td style="text-align:right">₹{inv.get("taxable_value", 0):,.2f}</td></tr>'
        )
        tax_rows = ""
        if inv.get("tax_mode") == "intra":
            tax_rows = (
                f'<tr><td>CGST @ 9%</td><td style="text-align:right">₹{inv.get("cgst", 0):,.2f}</td></tr>'
                f'<tr><td>SGST @ 9%</td><td style="text-align:right">₹{inv.get("sgst", 0):,.2f}</td></tr>'
            )
        elif inv.get("tax_mode") == "inter":
            tax_rows = f'<tr><td>IGST @ 18%</td><td style="text-align:right">₹{inv.get("igst", 0):,.2f}</td></tr>'
        note = (
            f'<p style="color:#777;font-size:12px">{e(str(inv.get("note", "")))}</p>'
            if inv.get("note")
            else ""
        )
        gstin_line = f"GSTIN: {e(sup.get('gstin', ''))}<br>" if sup.get("gstin") else ""
        rec_gstin = f"GSTIN: {e(rec.get('gstin', ''))}<br>" if rec.get("gstin") else ""
        void_banner = (
            f'<div style="border:2px solid #c00;color:#c00;text-align:center;'
            f'font-weight:bold;padding:8px;margin:8px 0">VOIDED — '
            f"{e(str(inv.get('void_reason', '') or 'cancelled'))} "
            f"({e(str(inv.get('voided_at', ''))[:10])})</div>"
            if inv.get("voided")
            else ""
        )
        return f"""<!doctype html><html><head><meta charset="utf-8"><title>{e(str(inv.get("number", "")))}</title>
<style>body{{font-family:Arial,sans-serif;max-width:720px;margin:24px auto;color:#222}}
table{{width:100%;border-collapse:collapse;margin:12px 0}}td,th{{border:1px solid #ddd;padding:8px}}
.h{{display:flex;justify-content:space-between}}.tot{{font-weight:bold;background:#f7f7f7}}</style></head><body>
{void_banner}
<div class="h"><div><h2 style="margin:0;color:#e85d04">{e(sup.get("name", ""))}</h2>
{gstin_line}{e(sup.get("address", ""))}<br>{e(sup.get("email", ""))}</div>
<div style="text-align:right"><h3 style="margin:0">{"TAX INVOICE" if inv.get("tax_mode") != "unregistered" else "INVOICE"}</h3>
<b>{e(str(inv.get("number", "")))}</b><br>Date: {e(str(inv.get("date", "")))}<br>
Place of supply: {e(str(inv.get("place_of_supply", "")))}<br>Reverse charge: No</div></div>
<p><b>Bill to:</b><br>{e(rec.get("name", ""))}<br>{rec_gstin}{e(rec.get("address", ""))}</p>
<table><tr><th>Description</th><th style="width:160px;text-align:right">Amount</th></tr>{rows}{tax_rows}
<tr class="tot"><td>Total</td><td style="text-align:right">₹{inv.get("gross_inr", 0):,.2f}</td></tr></table>
{note}<p style="color:#777;font-size:12px">Payment ref: {e(str(inv.get("payment_ref", "") or "—"))} ({e(str(inv.get("gateway", "") or "online"))})
· Computer-generated invoice. · leadsgenai.in</p></body></html>"""
    except Exception as e:
        logger.warning(f"[invoice] html failed: {e}")
        return "<html><body>Invoice render error</body></html>"


def _already_invoiced(client_id: str, plan: str, payment_ref: str) -> bool:
    """Dedupe — same payment_ref, ya (ref na ho to) same client+plan pichhle 20h me.
    Voided invoices dedupe me COUNT nahi hote (galat invoice void karke same ref pe
    corrected reissue possible rahe)."""
    try:
        rows = _read()
        voided = _void_map(rows)
        rows = [
            r for r in rows if r.get("kind") != "void" and str(r.get("number") or "") not in voided
        ]
        if payment_ref:
            return any(r.get("payment_ref") == payment_ref for r in rows)
        cutoff = _now() - timedelta(hours=20)
        for r in rows:
            if r.get("client_id") == client_id and r.get("plan") == (plan or "").lower():
                try:
                    ts = datetime.fromisoformat(str(r.get("created_at", "")).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False


async def on_payment_success(
    client_id: str,
    plan: str,
    payment_ref: str = "",
    gateway: str = "",
    amount_inr: float | None = None,
) -> dict[str, Any]:
    """Pay/renew hook (billing._provision_usage se) — invoice record + gated email. Never raises."""
    try:
        cid = (client_id or "").strip()
        if not cid or not (plan or "").strip():
            return {}
        if _already_invoiced(cid, plan, payment_ref):
            return {"deduped": True}
        inv = create_invoice(
            cid, plan, amount_inr=amount_inr, payment_ref=payment_ref, gateway=gateway
        )
        if not inv:
            return {}
        if _send_enabled() and inv.get("recipient", {}).get("email"):
            try:
                from app.integrations.email_sender import email_sender

                html = invoice_html(inv)
                body = (
                    f"Namaste {inv['recipient']['name']},\n\n"
                    f"Aapki payment mil gayi — dhanyavaad! Invoice {inv['number']} "
                    f"(₹{inv['gross_inr']:,.2f}) attached/below hai.\n\n— Team LeadsGenAI"
                )
                sent = await email_sender.send_email(
                    [inv["recipient"]["email"]],
                    f"Invoice {inv['number']} — LeadsGenAI",
                    body,
                    html_body=html,
                )
                inv["emailed"] = bool(sent)
            except Exception as e:
                logger.debug(f"[invoice] email skipped: {e}")
        return inv
    except Exception as e:
        logger.warning(f"[invoice] on_payment_success failed: {e}")
        return {}


def void_invoice(number: str, reason: str = "", by: str = "") -> dict[str, Any]:
    """Accountant-safe VOID (2026-07-18 billing containment): original invoice row
    kabhi delete/rewrite NAHI hota — ek append-only void marker judta hai. Number
    consumed rehta hai (Rule-46 sequence intact), reporting gross me count nahi
    hota, aur payment_ref dedupe se free ho jata hai (corrected reissue possible).
    Idempotent: dobara void = deduped:True. Never raises."""
    try:
        num = (number or "").strip()
        if not num:
            return {"ok": False, "error": "number required"}
        rows = _read()
        target = next((r for r in rows if r.get("kind") != "void" and r.get("number") == num), None)
        if not target:
            return {"ok": False, "error": f"invoice not found: {num}"}
        existing = _void_map(rows).get(num)
        if existing:
            return {"ok": True, "number": num, "deduped": True, "void": existing}
        marker = {
            "kind": "void",
            "voids": num,
            "voided_at": _now().isoformat(),
            "reason": str(reason or "")[:300],
            "by": str(by or "")[:120],
            "gross_inr": target.get("gross_inr"),
            "client_id": target.get("client_id"),
        }
        with _LOCK:
            _append(marker)
        logger.info(f"[invoice] VOID {num} reason={marker['reason'][:80]!r} by={marker['by']}")
        return {"ok": True, "number": num, "void": marker}
    except Exception as e:
        logger.warning(f"[invoice] void failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _annotate_voided(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Invoice rows only (markers hidden), voided ones flagged in-place."""
    voided = _void_map(rows)
    out: list[dict[str, Any]] = []
    for r in rows:
        if r.get("kind") == "void":
            continue
        v = voided.get(str(r.get("number") or ""))
        if v:
            r["voided"] = True
            r["void_reason"] = v.get("reason", "")
            r["voided_at"] = v.get("voided_at", "")
        out.append(r)
    return out


def list_invoices(limit: int = 50) -> list[dict[str, Any]]:
    rows = _annotate_voided(_read())
    return rows[-max(1, min(int(limit or 50), 500)) :][::-1]


def get_by_number(number: str) -> dict[str, Any]:
    for r in _annotate_voided(_read()):
        if r.get("number") == (number or "").strip():
            return r
    return {}


def stats() -> dict[str, Any]:
    rows = _annotate_voided(_read())
    fy = fy_label()
    fy_rows = [r for r in rows if r.get("fy") == fy]
    fy_live = [r for r in fy_rows if not r.get("voided")]
    fy_void = [r for r in fy_rows if r.get("voided")]
    return {
        "total": len(rows),
        "fy": fy,
        "fy_count": len(fy_rows),
        "fy_gross_inr": round(sum(float(r.get("gross_inr") or 0) for r in fy_live), 2),
        "fy_voided_count": len(fy_void),
        "fy_voided_gross_inr": round(sum(float(r.get("gross_inr") or 0) for r in fy_void), 2),
        "registered_mode": bool(_supplier().get("gstin")),
        "send_enabled": _send_enabled(),
    }


__all__ = [
    "create_invoice",
    "invoice_html",
    "on_payment_success",
    "list_invoices",
    "get_by_number",
    "void_invoice",
    "stats",
    "next_number",
    "fy_label",
]
