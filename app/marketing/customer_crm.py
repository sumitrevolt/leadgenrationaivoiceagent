"""
customer_crm.py — end-customer mini-CRM + birthday/anniversary WISH ENGINE.
============================================================================

Dhanda-app edge: client (local business) apne CUSTOMERS ki list rakhe
(naam/phone/birthday/anniversary/tags) aur hum unke liye roz ke occasion
wishes READY kar dein — Hinglish caption + AI image + wa.me 1-click link.

IMPORTANT — yeh module EXISTING `app/marketing/crm_lite.py` ke UPAR bana hai
(woh store + basic add/list/wishes pehle se deta hai, /api/marketing/crm/*
pe wired). Store wahi ek hai: `data/crm/<client_id>.jsonl` — do stores
banakar data split NAHI kiya. Yahan ADD hota hai:

  - import_rows()        : Apollo/Excel-style alias mapping (Name/Mobile/DOB…)
                           + csv_text support
  - todays_occasions()   : aaj (IST) ke birthday/anniversary customers (sync)
  - all_clients_todays_occasions() : saare marketing clients ke liye ek saath
  - run_wishes()         : occasion → Hinglish wish caption (free-LLM, template
                           fallback) + AI image URL (ai_image, key-safe proxy)
                           + wa.me prefilled link → DRAFTS
                           `data/customer_wish_drafts.jsonl`. KABHI auto-send
                           nahi — human 1-click hi bhejta hai (WA ban-safe).
  - run_wishes_if_enabled(): scheduler hook — sirf `CUSTOMER_WISHES=1` pe
                           run_wishes() chalata, warna graceful skip.

Free stack, pure stdlib + lazy imports, NEVER raises (error dicts).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_DRAFTS_PATH = os.path.join("data", "customer_wish_drafts.jsonl")
_MAX_LLM_WISHES_PER_RUN = 15  # token discipline — baaki template se

# ---- import alias mapping (Apollo/Excel/Google-Contacts style headers) ---- #
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": (
        "name",
        "full name",
        "customer name",
        "first name",
        "naam",
        "client name",
        "contact name",
    ),
    "phone": (
        "phone",
        "mobile",
        "phone number",
        "mobile number",
        "contact",
        "contact number",
        "whatsapp",
        "number",
    ),
    "birthday": ("birthday", "dob", "date of birth", "birth date", "birthdate", "janamdin", "bday"),
    "anniversary": (
        "anniversary",
        "anniv",
        "marriage anniversary",
        "wedding anniversary",
        "shaadi",
        "anniversary date",
    ),
    "tags": ("tags", "tag", "labels", "label", "group", "segment", "category"),
}


def _norm_header(h: Any) -> str:
    return str(h or "").strip().lower().replace("_", " ").replace("-", " ").strip()


def _map_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Ek raw row (kisi bhi header naming me) → canonical customer dict."""
    out: dict[str, Any] = {}
    lowered = {_norm_header(k): v for k, v in raw.items() if k is not None}
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            if alias in lowered and str(lowered[alias] or "").strip():
                out[field] = lowered[alias]
                break
    # tags string "vip, regular" → list
    if isinstance(out.get("tags"), str):
        out["tags"] = [t.strip() for t in str(out["tags"]).split(",") if t.strip()]
    return out


# --------------------------------------------------------------------------- #
# CRUD (thin reuse layer over crm_lite — single store data/crm/<id>.jsonl)
# --------------------------------------------------------------------------- #
def add_customer(
    client_id: str,
    name: str,
    phone: str,
    birthday: str = "",
    anniversary: str = "",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Ek customer add karo. Returns {ok, added, skipped, total} — never raises."""
    try:
        from app.marketing import crm_lite

        res = crm_lite.add_customers(
            client_id,
            [
                {
                    "name": name,
                    "phone": phone,
                    "birthday": birthday,
                    "anniversary": anniversary,
                    "tags": tags or [],
                }
            ],
        )
        return {"ok": res.get("added", 0) > 0, **res}
    except Exception as e:
        logger.warning(f"[customer_crm] add_customer failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def import_rows(
    client_id: str,
    rows: list[dict[str, Any]] | None = None,
    csv_text: str = "",
) -> dict[str, Any]:
    """Bulk import — dict rows YA raw CSV text (Excel paste). Alias-mapped headers
    (Name/Full Name, Mobile/Phone Number, DOB/Birthday, Anniversary, Tags).
    Phone-dedupe crm_lite karta hai. Never raises."""
    try:
        parsed: list[dict[str, Any]] = []
        if csv_text and str(csv_text).strip():
            import csv as _csv
            import io

            try:
                reader = _csv.DictReader(io.StringIO(str(csv_text).strip()))
                parsed.extend(dict(r) for r in reader)
            except Exception as e:
                return {"ok": False, "error": f"CSV parse fail: {str(e)[:120]}"}
        for r in rows or []:
            if isinstance(r, dict):
                parsed.append(r)
        if not parsed:
            return {"ok": False, "error": "Koi rows nahi mile — rows ya csv_text bhejo."}

        mapped = [_map_row(r) for r in parsed]
        mapped = [m for m in mapped if m.get("phone")]
        if not mapped:
            return {
                "ok": False,
                "error": "Kisi row me phone nahi mila (Phone/Mobile column zaroori).",
            }

        from app.marketing import crm_lite

        res = crm_lite.add_customers(client_id, mapped)
        return {"ok": True, "parsed": len(parsed), "with_phone": len(mapped), **res}
    except Exception as e:
        logger.warning(f"[customer_crm] import_rows failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def list_customers(client_id: str, tag: str | None = None) -> list[dict[str, Any]]:
    """Saved customers (crm_lite passthrough). Never raises."""
    try:
        from app.marketing import crm_lite

        return crm_lite.list_customers(client_id, tag=tag)
    except Exception as e:
        logger.warning(f"[customer_crm] list failed: {e}")
        return []


# --------------------------------------------------------------------------- #
# Occasions (aaj IST)
# --------------------------------------------------------------------------- #
def _today_mmdd() -> str:
    return datetime.now(_IST).strftime("%m-%d")


def todays_occasions(client_id: str) -> list[dict[str, Any]]:
    """Aaj jinke birthday/anniversary hain: [{name, phone, occasion, tags}]."""
    out: list[dict[str, Any]] = []
    try:
        today = _today_mmdd()
        for cust in list_customers(client_id):
            for occ, field in (("birthday", "birthday"), ("anniversary", "anniversary")):
                if cust.get(field) == today:
                    out.append(
                        {
                            "name": str(cust.get("name") or "").strip() or "Customer",
                            "phone": str(cust.get("phone") or ""),
                            "occasion": occ,
                            "tags": cust.get("tags") or [],
                        }
                    )
    except Exception as e:
        logger.warning(f"[customer_crm] todays_occasions failed: {e}")
    return out


def all_clients_todays_occasions() -> list[dict[str, Any]]:
    """Saare active marketing clients ke aaj ke occasions:
    [{client_id, business_name, phone(client), occasions:[...]}]. Never raises."""
    out: list[dict[str, Any]] = []
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients() or []:
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue
            occ = todays_occasions(cid)
            if occ:
                out.append(
                    {
                        "client_id": cid,
                        "business_name": str(c.get("business_name") or "").strip(),
                        "niche": c.get("niche") or "general",
                        "occasions": occ,
                    }
                )
    except Exception as e:
        logger.warning(f"[customer_crm] all_clients_todays_occasions failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Wish drafting (NEVER auto-send — wa.me 1-click only)
# --------------------------------------------------------------------------- #
_WISH_TEMPLATES = {
    "birthday": (
        "🎂 Janamdin bahut bahut mubarak ho, {name} ji! 🎉 {biz} ki poori team "
        "ki taraf se dher saari shubhkamnayein. Aapka din khushiyon se bhara rahe! 🙏"
    ),
    "anniversary": (
        "💐 Shaadi ki salgirah mubarak ho, {name} ji! {biz} ki taraf se aap "
        "dono ko dher saari badhai — aapka saath yun hi bana rahe! 🎉🙏"
    ),
}


def _template_wish(name: str, biz: str, occasion: str) -> str:
    tpl = _WISH_TEMPLATES.get(occasion, _WISH_TEMPLATES["birthday"])
    return tpl.format(name=name or "ji", biz=biz or "Hamari team")


async def _llm_wish(name: str, biz: str, occasion: str, niche: str) -> str:
    """Free-LLM personalized wish — fail/empty par '' (caller template use kare)."""
    try:
        from app.voice_agent import free_ai

        occ_hi = (
            "janamdin (birthday)" if occasion == "birthday" else "shaadi ki salgirah (anniversary)"
        )
        system = (
            "Tu ek Indian local business ka friendly social-media writer hai. "
            "Customer ke liye EK chhota (max 35 shabd) warm Hinglish (Roman script) "
            f"{occ_hi} wish message likh, business ke naam ke saath, 1-2 emoji. "
            "Sirf message do — koi heading/quotes/commentary nahi."
        )
        user = f"Customer: {name}\nBusiness: {biz} ({niche.replace('_', ' ')})"
        text, _provider = await free_ai.chat(
            system, [{"role": "user", "content": user}], max_tokens=120, temperature=0.8
        )
        text = (text or "").strip().strip('"')
        if 10 < len(text) < 600:
            return text
    except Exception as e:
        logger.debug(f"[customer_crm] llm wish skip: {e}")
    return ""


def _image_url_for(occasion: str, biz: str, niche: str) -> str:
    """AI image URL (key-safe): sk_ key ho to server proxy path, warna direct URL.
    ai_image module ke builders REUSE — kabhi raise nahi."""
    prompt = (
        f"warm festive {'birthday' if occasion == 'birthday' else 'wedding anniversary'} "
        f"greeting card, flowers and celebration, from '{biz}' a {niche.replace('_', ' ')} "
        "business in India, vibrant colors, elegant, no text"
    )
    try:
        from app.marketing import ai_image

        # sk_ (secret) key → server proxy (key URL me kabhi nahi);
        # pk_/no key → direct Pollinations URL theek hai.
        try:
            if ai_image._is_secret():  # noqa: SLF001 — same-package helper
                return ai_image.proxy_path(prompt, 1024, 1024)
        except Exception:
            pass
        return ai_image.image_url(prompt, 1024, 1024)
    except Exception as e:
        logger.debug(f"[customer_crm] image url skip: {e}")
        return ""


def _wa_link(phone10: str, message: str) -> str:
    d = "".join(ch for ch in str(phone10 or "") if ch.isdigit())
    if len(d) == 10:
        d = "91" + d
    if not d:
        return ""
    return f"https://wa.me/{d}?text={quote(message)}"


def _append_draft(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_DRAFTS_PATH) or ".", exist_ok=True)
        with open(_DRAFTS_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"[customer_crm] draft write failed: {e}")


def _read_drafts(limit: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.isfile(_DRAFTS_PATH):
            with open(_DRAFTS_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        continue
    except Exception as e:
        logger.warning(f"[customer_crm] drafts read failed: {e}")
    return rows[-max(1, min(int(limit or 100), 1000)) :]


def list_wish_drafts(limit: int = 100, date: str | None = None) -> list[dict[str, Any]]:
    """Saved wish drafts (newest last). date='MM-DD' filter optional."""
    rows = _read_drafts(limit=1000)
    if date:
        rows = [r for r in rows if r.get("date") == date]
    return rows[-max(1, min(int(limit or 100), 1000)) :]


async def run_wishes(execute: bool = False) -> dict[str, Any]:
    """Aaj ke saare occasions (saare clients) ke wish DRAFTS banao.

    Har draft: Hinglish caption (free-LLM, template fallback) + AI image URL +
    wa.me 1-click prefilled link → `data/customer_wish_drafts.jsonl`.

    `execute` flag SIRF signature-compat ke liye hai — yeh function KABHI
    auto-send nahi karta (WhatsApp auto-send = number ban; policy: human
    1-click). Same-day duplicate drafts skip hote hain. Never raises.
    """
    try:
        today = _today_mmdd()
        existing = {
            (r.get("client_id"), r.get("phone"), r.get("occasion"))
            for r in _read_drafts(limit=1000)
            if r.get("date") == today
        }
        groups = all_clients_todays_occasions()
        drafts: list[dict[str, Any]] = []
        llm_used = 0
        for grp in groups:
            biz = grp.get("business_name") or "Hamari team"
            niche = str(grp.get("niche") or "general")
            cid = grp.get("client_id")
            for occ in grp.get("occasions", []):
                key = (cid, occ.get("phone"), occ.get("occasion"))
                if key in existing:
                    continue
                existing.add(key)
                name = occ.get("name") or "ji"
                occasion = occ.get("occasion") or "birthday"
                caption = ""
                if llm_used < _MAX_LLM_WISHES_PER_RUN:
                    caption = await _llm_wish(name, biz, occasion, niche)
                    if caption:
                        llm_used += 1
                if not caption:
                    caption = _template_wish(name, biz, occasion)
                rec = {
                    "date": today,
                    "client_id": cid,
                    "business_name": biz,
                    "name": name,
                    "phone": occ.get("phone") or "",
                    "occasion": occasion,
                    "caption": caption,
                    "image_url": _image_url_for(occasion, biz, niche),
                    "wa_link": _wa_link(occ.get("phone") or "", caption),
                    "status": "draft",  # NEVER auto-sent
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                _append_draft(rec)
                drafts.append(rec)
        return {
            "ok": True,
            "date": today,
            "clients_with_occasions": len(groups),
            "drafts_created": len(drafts),
            "llm_captions": llm_used,
            "drafts": drafts,
            "note": "Auto-send NAHI hota — wa_link se 1-click bhejo (ban-safe).",
        }
    except Exception as e:
        logger.warning(f"[customer_crm] run_wishes failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def run_wishes_if_enabled() -> dict[str, Any]:
    """Scheduler hook — sirf `CUSTOMER_WISHES=1` pe chalta (default OFF)."""
    flag = (os.getenv("CUSTOMER_WISHES") or "").strip().lower()
    if flag not in ("1", "true", "yes", "on"):
        return {"ok": True, "skipped": True, "reason": "CUSTOMER_WISHES flag OFF"}
    return await run_wishes(execute=False)


__all__ = [
    "add_customer",
    "import_rows",
    "list_customers",
    "todays_occasions",
    "all_clients_todays_occasions",
    "run_wishes",
    "run_wishes_if_enabled",
    "list_wish_drafts",
]
