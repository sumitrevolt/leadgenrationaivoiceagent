"""
newsletter.py — Mailchimp-lite auto-newsletter (per-client, UNKE customers ke liye).
====================================================================================

Client (local business) apne customers ki email list de — hum mahine me EK
Hinglish newsletter ready karein: greeting + is mahine ka festival (festivals
reuse) + offer slot + products (product_catalog reuse) + review CTA.

Public API (sab never-raise, pure stdlib + lazy imports):
  - add_subscribers(client_id, rows)   -> import + email-dedupe (data/newsletter_subs.jsonl)
  - subscribers(client_id)             -> active subs (latest state per email)
  - unsubscribe(token)                 -> public 1-click opt-out (append event)
  - unsub_html(result)                 -> tiny Hinglish confirmation page
  - compose(client_id, month=None)     -> async; newsletter {subject, html, text}
                                          (free_ai polish + deterministic fallback)
  - run_due_if_enabled(force=False)    -> async; GATED `NEWSLETTER_ENGINE=1`:
                                          month me 1 baar per active client w/ subs>0,
                                          compose -> SEND via EmailSender SMTP (cap
                                          200 emails/run). Flag OFF = compose +
                                          RECORD-only (koi send nahi, LLM bhi skip).
  - rss_to_email(limit=5)              -> apne blog (seo_blog) ke naye posts ->
                                          digest DRAFT (send nahi karta)

Stores:
  data/newsletter_subs.jsonl  (append-only events: sub / unsub — latest wins)
  data/newsletter_runs.jsonl  (run log + month-dedupe + rss-digest markers)

Ban-safe: sirf OPTED-IN subscribers (client ne diye), har mail me unsubscribe
link. Auto-send sirf flag ON pe. KABHI raise nahi karta.
"""

from __future__ import annotations

import html as _html
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_SUBS_PATH = os.path.join("data", "newsletter_subs.jsonl")
_RUNS_PATH = os.path.join("data", "newsletter_runs.jsonl")
_FLAG = "NEWSLETTER_ENGINE"
_SEND_CAP_PER_RUN = 200  # total emails across all clients per run (SMTP-rep safe)
_SITE_URL = "https://leadsgenai.in"
_UNSUB_BASE = _SITE_URL + "/api/lifecycle/newsletter/unsub/"

_MONTH_HI = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return (os.getenv(_FLAG) or "").strip().lower() in ("1", "true", "yes", "on")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[newsletter] append {path} failed: {e}")


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"[newsletter] read {path} failed: {e}")
    return rows


def _valid_email(addr: str) -> bool:
    a = (addr or "").strip().lower()
    return "@" in a and "." in a.split("@")[-1] and 6 <= len(a) <= 254


# --------------------------------------------------------------------------- #
# Subscribers (append-only event log: type sub/unsub, latest wins per email)
# --------------------------------------------------------------------------- #
def add_subscribers(client_id: str, rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Subscribers import (dedupe by email per client). Never raises.
    Returns {ok, added, skipped, total}."""
    try:
        cid = str(client_id or "").strip()
        if not cid:
            return {"ok": False, "error": "client_id zaroori hai"}
        existing = {s["email"] for s in subscribers(cid, include_unsub=True)}
        added = skipped = 0
        for r in rows or []:
            if not isinstance(r, dict):
                skipped += 1
                continue
            em = str(r.get("email") or "").strip().lower()
            if not _valid_email(em) or em in existing:
                skipped += 1
                continue
            existing.add(em)
            _append(
                _SUBS_PATH,
                {
                    "type": "sub",
                    "id": uuid.uuid4().hex[:12],
                    "token": uuid.uuid4().hex[:20],  # unsubscribe token (unguessable)
                    "client_id": cid,
                    "name": str(r.get("name") or "").strip()[:80],
                    "email": em,
                    "status": "active",
                    "added_at": _now().isoformat(),
                },
            )
            added += 1
        return {"ok": True, "added": added, "skipped": skipped, "total": len(subscribers(cid))}
    except Exception as e:
        logger.warning(f"[newsletter] add_subscribers failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def subscribers(client_id: str, include_unsub: bool = False) -> list[dict[str, Any]]:
    """Latest state per email for a client. Never raises."""
    try:
        cid = str(client_id or "").strip()
        state: dict[str, dict[str, Any]] = {}
        unsub_tokens: set[str] = set()
        for r in _read(_SUBS_PATH):
            if r.get("type") == "unsub":
                unsub_tokens.add(str(r.get("token") or ""))
                continue
            if r.get("type") != "sub" or str(r.get("client_id") or "") != cid:
                continue
            em = str(r.get("email") or "").lower()
            if em:
                state[em] = r
        out: list[dict[str, Any]] = []
        for rec in state.values():
            if str(rec.get("token") or "") in unsub_tokens:
                rec = dict(rec)
                rec["status"] = "unsub"
            if rec.get("status") == "unsub" and not include_unsub:
                continue
            out.append(rec)
        return out
    except Exception as e:
        logger.warning(f"[newsletter] subscribers failed: {e}")
        return []


def unsubscribe(token: str) -> dict[str, Any]:
    """Public 1-click opt-out by token. Never raises."""
    try:
        tok = str(token or "").strip()
        if not (8 <= len(tok) <= 40) or not tok.isalnum():
            return {"ok": False, "error": "invalid token"}
        found = None
        for r in _read(_SUBS_PATH):
            if r.get("type") == "sub" and str(r.get("token") or "") == tok:
                found = r
        if not found:
            return {"ok": False, "error": "token nahi mila"}
        _append(_SUBS_PATH, {"type": "unsub", "token": tok, "at": _now().isoformat()})
        return {"ok": True, "email": found.get("email"), "client_id": found.get("client_id")}
    except Exception as e:
        logger.warning(f"[newsletter] unsubscribe failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def unsub_html(result: dict[str, Any] | None) -> str:
    """Tiny Hinglish confirmation page (never raises)."""
    ok = bool((result or {}).get("ok"))
    if ok:
        msg = (
            "Aap newsletter list se hata diye gaye hain. Ab aage emails nahi aayenge. Dhanyawad! 🙏"
        )
    else:
        msg = "Yeh link valid nahi hai ya pehle hi use ho chuka hai."
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Unsubscribe</title></head>"
        "<body style='font-family:Arial,sans-serif;background:#f7f7fb;margin:0;padding:40px 16px;'>"
        "<div style='max-width:480px;margin:0 auto;background:#fff;border-radius:12px;"
        "padding:28px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,.06);'>"
        f"<h2 style='margin:0 0 12px;color:#222;'>{'✅' if ok else '⚠️'} Unsubscribe</h2>"
        f"<p style='color:#444;font-size:15px;line-height:1.5;'>{_html.escape(msg)}</p>"
        "</div></body></html>"
    )


# --------------------------------------------------------------------------- #
# Compose (Hinglish monthly newsletter — festivals + offer + products + reviews)
# --------------------------------------------------------------------------- #
def _month_label(month: str | None) -> str:
    try:
        if month and len(str(month)) >= 7:  # "YYYY-MM"
            m = int(str(month)[5:7])
        else:
            m = _now().month
        return _MONTH_HI.get(m, "is mahine")
    except Exception:
        return "is mahine"


def _this_month_festivals(limit: int = 3) -> list[str]:
    """Agle ~30 din ke festivals (festivals.upcoming reuse, lazy). Never raises."""
    try:
        from app.marketing import festivals

        rows = festivals.upcoming(30) or []
        return [str(r.get("name") or "").strip() for r in rows[:limit] if r.get("name")]
    except Exception:
        return []


def _client_products(slug: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        if not slug:
            return []
        from app.marketing import product_catalog

        return (product_catalog.list_products(slug, include_out_of_stock=False) or [])[:limit]
    except Exception:
        return []


async def _llm_intro(biz: str, niche: str, fest_names: list[str]) -> str:
    """Free-LLM 2-3 line warm Hinglish intro — fail/empty par '' (template fallback)."""
    try:
        from app.voice_agent import free_ai

        fests = ", ".join(fest_names) if fest_names else "koi khaas festival nahi"
        system = (
            "Tu ek Indian local business ka friendly newsletter writer hai. "
            "Customers ke liye EK chhota (max 45 shabd) warm Hinglish (Roman script) "
            "monthly-newsletter intro paragraph likh — greeting + is mahine ki ek baat. "
            "Sirf paragraph do, koi heading/quotes nahi."
        )
        user = f"Business: {biz} ({(niche or 'general').replace('_', ' ')})\nIs mahine ke festivals: {fests}"
        text, _provider = await free_ai.chat(
            system, [{"role": "user", "content": user}], max_tokens=140, temperature=0.7
        )
        text = (text or "").strip().strip('"')
        if 15 < len(text) < 700:
            return text
    except Exception as e:
        logger.debug(f"[newsletter] llm intro skip: {e}")
    return ""


def _render_html(
    biz: str,
    month_label: str,
    intro: str,
    fest_names: list[str],
    offer: str,
    products: list[dict[str, Any]],
    minisite_url: str,
    primary: str,
) -> str:
    e = _html.escape
    color = primary if primary else "#4f46e5"
    parts = [
        "<html><body style='font-family:Arial,Helvetica,sans-serif;font-size:15px;"
        "line-height:1.55;color:#222;max-width:600px;margin:0 auto;'>",
        f"<div style='background:{e(color)};color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;'>"
        f"<h2 style='margin:0;font-size:20px;'>{e(biz)} — {e(month_label)} Newsletter 📬</h2></div>",
        "<div style='padding:18px 22px;border:1px solid #eee;border-top:0;border-radius:0 0 10px 10px;'>",
        f"<p>{e(intro)}</p>",
    ]
    if fest_names:
        parts.append(
            f"<p><b>🎉 Is mahine:</b> {e(', '.join(fest_names))} — celebration ki taiyari ho jaye!</p>"
        )
    if offer:
        parts.append(
            f"<p style='background:#fff8e6;border-left:3px solid {e(color)};padding:10px 14px;"
            f"border-radius:4px;'><b>🎁 Offer:</b> {e(offer)}</p>"
        )
    if products:
        parts.append("<p><b>🛍️ Hamare picks:</b></p><ul>")
        for p in products:
            nm = e(str(p.get("name") or "").strip()[:80] or "Product")
            pr = str(p.get("price") or "").strip()
            parts.append(f"<li>{nm}{(' — ₹' + e(pr)) if pr else ''}</li>")
        parts.append("</ul>")
    if minisite_url:
        parts.append(
            f"<p><a href='{e(minisite_url)}' style='background:{e(color)};color:#fff;"
            "padding:10px 18px;border-radius:6px;text-decoration:none;display:inline-block;'>"
            "Visit / Book karein</a></p>"
        )
    parts.append(
        "<p>⭐ Hamari service pasand aayi ho to ek chhota Google review zaroor dijiye — "
        "bahut madad hoti hai! 🙏</p>"
    )
    parts.append(
        "<p style='color:#888;font-size:12px;'>Yeh newsletter aapko isliye mila kyunki aap "
        f"{e(biz)} ke customer hain. Unsubscribe link neeche hai.</p>"
    )
    parts.append("</div></body></html>")
    return "".join(parts)


async def compose(client_id: str, month: str | None = None, use_llm: bool = True) -> dict[str, Any]:
    """Ek client ka monthly Hinglish newsletter banao. Never raises.
    Returns {ok, subject, html, text, month, festivals, products_count}."""
    try:
        cid = str(client_id or "").strip()
        client: dict[str, Any] = {}
        try:
            from app.marketing import clients_store

            client = clients_store.get_client(cid) or {}
        except Exception:
            client = {}
        biz = str(client.get("business_name") or "").strip() or "Hamari team"
        niche = str(client.get("niche") or "general")
        slug = str(client.get("slug") or "").strip()
        month_label = _month_label(month)
        fest_names = _this_month_festivals()
        products = _client_products(slug)
        offer = str(client.get("current_offer") or "").strip() or (
            f"Is mahine {biz} pe special discount — WhatsApp karke pooch lijiye!"
        )
        primary = ""
        try:
            from app.marketing import brand_kit

            brand = brand_kit.get_brand(cid) or {}
            primary = str((brand.get("colors") or {}).get("primary") or "")
        except Exception:
            primary = ""

        intro = ""
        if use_llm:
            intro = await _llm_intro(biz, niche, fest_names)
        if not intro:
            intro = (
                f"Namaste! {biz} ki taraf se {month_label} ki dher saari shubhkamnayein. "
                "Is mahine kya naya hai, neeche dekhiye — aur koi sawal ho to seedha "
                "WhatsApp kar dijiye. 😊"
            )

        minisite_url = f"{_SITE_URL}/b/{slug}?utm_source=newsletter" if slug else ""
        html_body = _render_html(
            biz, month_label, intro, fest_names, offer, products, minisite_url, primary
        )
        text_lines = [intro, ""]
        if fest_names:
            text_lines.append("Is mahine: " + ", ".join(fest_names))
        text_lines.append("Offer: " + offer)
        if minisite_url:
            text_lines.append("Visit/Book: " + minisite_url)
        text_lines.append("")
        text_lines.append("Pasand aaye to ek Google review zaroor dijiye!")
        subject = f"{biz} — {month_label} ki khaas baatein 📬"
        return {
            "ok": True,
            "client_id": cid,
            "subject": subject,
            "html": html_body,
            "text": "\n".join(text_lines),
            "month": (month or _now().strftime("%Y-%m")),
            "festivals": fest_names,
            "products_count": len(products),
        }
    except Exception as e:
        logger.warning(f"[newsletter] compose failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


# --------------------------------------------------------------------------- #
# Run (monthly per client; GATED NEWSLETTER_ENGINE=1 for actual sending)
# --------------------------------------------------------------------------- #
async def _send_one(to_email: str, subject: str, text: str, html_body: str) -> bool:
    """EmailSender SMTP reuse (lazy). Tests monkeypatch this. Never raises."""
    try:
        from app.integrations.email_sender import EmailSender

        sender = EmailSender()
        return bool(await sender.send_email([to_email], subject, text, html_body))
    except Exception as e:
        logger.warning(f"[newsletter] send to {to_email} failed: {e}")
        return False


def _already_ran(client_id: str, month: str) -> bool:
    try:
        for r in _read(_RUNS_PATH):
            if (
                r.get("type") == "run"
                and str(r.get("client_id") or "") == str(client_id)
                and str(r.get("month") or "") == month
            ):
                return True
    except Exception:
        pass
    return False


async def run_due_if_enabled(force: bool = False) -> dict[str, Any]:
    """Monthly sweep. Flag ON = compose + SEND (cap 200 emails/run);
    flag OFF = compose (LLM skip) + RECORD-only. Month-dedupe per client.
    `force=True` month-dedupe bypass (manual testing). Never raises."""
    enabled = _enabled()
    out: dict[str, Any] = {"enabled": enabled, "clients": 0, "sent": 0, "recorded": 0}
    try:
        month = _now().strftime("%Y-%m")
        try:
            from app.marketing import clients_store

            clients = clients_store.list_clients() or []
        except Exception:
            clients = []
        budget = _SEND_CAP_PER_RUN
        for c in clients:
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue
            subs = subscribers(cid)
            if not subs:
                continue
            if not force and _already_ran(cid, month):
                continue
            news = await compose(cid, month=month, use_llm=enabled)
            if not news.get("ok"):
                continue
            out["clients"] += 1
            # Month-dedupe marker PEHLE likho (crash/timeout mid-send par dobara
            # run hone se DUPLICATE emails na jayein — under-send > re-send).
            _append(
                _RUNS_PATH,
                {
                    "type": "run",
                    "client_id": cid,
                    "month": month,
                    "subject": news.get("subject"),
                    "subscribers": len(subs),
                    "auto_sent": enabled,
                    "at": _now().isoformat(),
                },
            )
            out["recorded"] += 1
            sent_count = 0
            if enabled and budget > 0:
                batch = subs[: min(len(subs), budget)]
                for idx, s in enumerate(batch):
                    tok = str(s.get("token") or "")
                    unsub_url = _UNSUB_BASE + tok
                    html_body = str(news["html"]).replace(
                        "</body></html>",
                        f"<p style='color:#999;font-size:11px;text-align:center;'>"
                        f"<a href='{_html.escape(unsub_url)}' style='color:#999;'>Unsubscribe</a></p>"
                        "</body></html>",
                    )
                    text = str(news["text"]) + f"\n\nUnsubscribe: {unsub_url}"
                    ok = await _send_one(str(s.get("email")), str(news["subject"]), text, html_body)
                    if ok:
                        sent_count += 1
                        budget -= 1
                    if budget <= 0:
                        break
                    if idx < len(batch) - 1:  # SMTP-reputation throttle
                        try:
                            import asyncio as _aio
                            import random as _rnd

                            await _aio.sleep(_rnd.uniform(0.4, 1.0))
                        except Exception:
                            pass
                _append(
                    _RUNS_PATH,
                    {
                        "type": "run_result",
                        "client_id": cid,
                        "month": month,
                        "sent": sent_count,
                        "at": _now().isoformat(),
                    },
                )
            out["sent"] += sent_count
        if out["recorded"]:
            try:
                from app.platform.team import log_event

                log_event(
                    "isha",
                    "newsletter_run",
                    f"{out['recorded']} client newsletters ({out['sent']} emails sent, flag={'ON' if enabled else 'OFF'})",
                )
            except Exception:
                pass
        return out
    except Exception as e:
        logger.warning(f"[newsletter] run_due failed: {e}")
        out["error"] = str(e)[:200]
        return out


# --------------------------------------------------------------------------- #
# RSS-to-email (apne blog ke naye posts -> digest DRAFT; send nahi)
# --------------------------------------------------------------------------- #
def rss_to_email(limit: int = 5) -> dict[str, Any]:
    """Apne blog (seo_blog store) ke naye posts ka email-digest DRAFT.
    Pichhle digest ke baad ke naye slugs hi uthata hai (marker in runs log).
    Never raises."""
    try:
        try:
            limit = max(1, min(int(limit), 20))
        except Exception:
            limit = 5
        try:
            from app.marketing import seo_blog

            articles = seo_blog.list_articles(limit=100) or []
        except Exception:
            articles = []
        seen: set[str] = set()
        for r in _read(_RUNS_PATH):
            if r.get("type") == "rss_digest":
                for s in r.get("slugs") or []:
                    seen.add(str(s))
        fresh = [a for a in articles if str(a.get("slug") or "") not in seen][:limit]
        if not fresh:
            return {"ok": True, "posts": [], "note": "Koi naya blog post nahi."}
        e = _html.escape
        items_html = "".join(
            f"<li style='margin-bottom:8px;'><a href='{e(_SITE_URL)}/blog/{e(str(a.get('slug')))}'>"
            f"{e(str(a.get('title') or a.get('slug')))}</a><br>"
            f"<span style='color:#666;font-size:13px;'>{e(str(a.get('meta_description') or '')[:140])}</span></li>"
            for a in fresh
        )
        html_body = (
            "<html><body style='font-family:Arial,sans-serif;font-size:15px;line-height:1.5;"
            "color:#222;max-width:600px;margin:0 auto;'>"
            "<h2>📰 LeadGen AI — naye blog posts</h2>"
            f"<ul>{items_html}</ul>"
            f"<p><a href='{e(_SITE_URL)}/blog'>Saare posts dekhein</a></p>"
            "</body></html>"
        )
        text = "\n".join(f"- {a.get('title')}: {_SITE_URL}/blog/{a.get('slug')}" for a in fresh)
        _append(
            _RUNS_PATH,
            {
                "type": "rss_digest",
                "slugs": [str(a.get("slug")) for a in fresh],
                "at": _now().isoformat(),
            },
        )
        return {
            "ok": True,
            "subject": f"LeadGen AI blog — {len(fresh)} naye posts",
            "html": html_body,
            "text": text,
            "posts": fresh,
            "status": "draft",  # send NAHI hota — human/scheduler decide kare
        }
    except Exception as e:
        logger.warning(f"[newsletter] rss_to_email failed: {e}")
        return {"ok": False, "error": str(e)[:200], "posts": []}


__all__ = [
    "add_subscribers",
    "subscribers",
    "unsubscribe",
    "unsub_html",
    "compose",
    "run_due_if_enabled",
    "rss_to_email",
]
