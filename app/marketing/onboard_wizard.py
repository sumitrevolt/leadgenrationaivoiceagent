"""Onboarding wizard — business-type → niche template → auto-setup.

Interactive onboarding ka core: admin ya customer "Salon", "Restaurant", "Clinic"
chunta hai → wizard us business type ke liye READY niche template resolve karta
hai (niche key + kya auto-setup hoga) aur 1-click apply karta hai.

Design:
  - Pure-data catalog (BUSINESS_TYPES): business-type → niche key + display meta.
    Niche ka content (script, KB pack, palette) pahle se NICHES / NICHE_SCRIPTS /
    niche_knowledge_data / client_snapshots me hai — yeh unhe 1-click wizard me
    bind karta hai. Koi naya heavy data nahi.
  - apply_auto_setup(): client_snapshots.apply_niche_to_client (mini-site palette,
    journeys, festival schedule) + niche_knowledge facts → client record. Best-effort,
    never raises. Flag-gated: ONBOARD_WIZARD_APPLY (default OFF, opt-in).
  - Import-safe: koi module-level heavy import nahi.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --------------------------------------------------------------------------- #
# Business-type catalog — salon / restaurant / clinic / gym / more
# --------------------------------------------------------------------------- #
# "business type" = aam Indian business category ek non-tech owner pehchanta hai.
# Har entry niche key resolve karti hai jo NICHES/NICHE_SCRIPTS me existing hai.
# auto_setup_fields = wizard UI me dikhane wala checklist (kya set up hoga).

BUSINESS_TYPES: list[dict[str, Any]] = [
    {
        "id": "salon",
        "label": "Salon / Beauty Parlour",
        "emoji": "💇‍♀️",
        "niche": "salon_spa",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Before-after reels + offers ka content pack",
            "Google reviews / 'salon near me' optimization",
            "Voice agent: appointment booking script",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "restaurant",
        "label": "Restaurant / Cafe",
        "emoji": "🍽️",
        "niche": "restaurant_cafe",
        "products": ["marketing"],
        "auto_setup_fields": [
            "Menu posts + festival offer posters",
            "Google Business Profile + review collection",
            "WhatsApp orders / reservation follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "clinic",
        "label": "Clinic / Doctor",
        "emoji": "🏥",
        "niche": "hospital_appointments",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Health tips + doctor intro content pack",
            "Appointment booking voice agent script",
            "Google reviews + 'clinic near me' ranking",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "dental",
        "label": "Dental Clinic",
        "emoji": "🦷",
        "niche": "dental_implants",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Dental offer posts (implants, cleaning)",
            "Appointment booking voice agent script",
            "Google reviews + 'dentist near me' ranking",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "gym",
        "label": "Gym / Fitness Studio",
        "emoji": "💪",
        "niche": "gym_fitness",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Transformation reels + joining offers",
            "Google reviews + 'gym near me' ranking",
            "Voice agent: membership enquiry script",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "real_estate",
        "label": "Real Estate / Property",
        "emoji": "🏠",
        "niche": "real_estate_luxury",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Property posts + site visit offers",
            "Voice agent: site-visit booking script",
            "Google reviews + project keywords",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "coaching",
        "label": "Coaching / Tuition",
        "emoji": "📚",
        "niche": "coaching",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Course + result-based content pack",
            "Voice agent: admission enquiry script",
            "Google reviews + 'coaching near me'",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "solar",
        "label": "Solar Installer",
        "emoji": "☀️",
        "niche": "solar_residential",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Subsidy + before-after solar posts",
            "Voice agent: roof survey booking script",
            "Google reviews + solar keywords",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "auto_service",
        "label": "Car / Auto Service",
        "emoji": "🚗",
        "niche": "automobile_service",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Service offer posters + before-after",
            "Google reviews + 'car service near me'",
            "WhatsApp booking / reminder follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "boutique",
        "label": "Boutique / Fashion",
        "emoji": "👗",
        "niche": "boutique_fashion",
        "products": ["marketing"],
        "auto_setup_fields": [
            "New collection posts + reels",
            "WhatsApp orders / repeat customers",
            "Festival + wedding season offers",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "bakery",
        "label": "Bakery / Sweets",
        "emoji": "🎂",
        "niche": "bakery_sweets",
        "products": ["marketing"],
        "auto_setup_fields": [
            "Cake/dessert reels + festival posters",
            "Google reviews + 'cake shop near me'",
            "Birthday / custom order offers",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "tiffin",
        "label": "Tiffin / Home Food Service",
        "emoji": "🍱",
        "niche": "tiffin_service",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Menu posts + weekly offers",
            "Google reviews + 'tiffin near me' ranking",
            "WhatsApp order flow + monthly subscription follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "salon-men",
        "label": "Men's Salon / Barber",
        "emoji": "💈",
        "niche": "gents_salon",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Before-after reels + beard/haircut styling posts",
            "Google reviews + 'salon near me' ranking",
            "WhatsApp booking + reminder follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "tuition",
        "label": "Tuition Classes",
        "emoji": "📝",
        "niche": "tuition_classes",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Result posts + admission offers",
            "Google reviews + 'tuition near me' ranking",
            "Admission inquiry auto follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "play-school",
        "label": "Play School / Preschool",
        "emoji": "🧸",
        "niche": "play_school",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Campus photos + activities posts",
            "Parent reviews + 'play school near me' ranking",
            "Admission season campaign + inquiry follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "pharmacy",
        "label": "Pharmacy / Medical Store",
        "emoji": "💊",
        "niche": "pharmacy_medical",
        "products": ["marketing"],
        "auto_setup_fields": [
            "Health + offer posts",
            "Google reviews + 'pharmacy near me'",
            "WhatsApp refill / reminder follow-up",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "travel",
        "label": "Travel Agency",
        "emoji": "✈️",
        "niche": "travel_agency",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Package posts + seasonal offers",
            "Voice agent: enquiry qualification script",
            "Google reviews + destination keywords",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "jewellery",
        "label": "Jewellery Store",
        "emoji": "💍",
        "niche": "jewellery_store",
        "products": ["marketing"],
        "auto_setup_fields": [
            "Collection posts + festive offers",
            "Google reviews + 'jewellery shop near me'",
            "Wedding season campaign schedule",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "laundry",
        "label": "Laundry / Dry-Clean",
        "emoji": "🧺",
        "niche": "laundry_dryclean",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Home-pickup offers + festival dry-clean posters",
            "Google reviews + 'laundry near me' ranking",
            "Voice agent: pickup/enquiry script",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "electronics-repair",
        "label": "Mobile / Electronics Repair",
        "emoji": "📱",
        "niche": "electronics_repair",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "Repair offer posters + doorstep service posts",
            "Google reviews + 'mobile repair near me' ranking",
            "Voice agent: repair enquiry script",
            "Mini-site palette + festival schedule",
        ],
    },
    {
        "id": "general",
        "label": "Other Business",
        "emoji": "🏪",
        "niche": "general",
        "products": ["marketing", "voice"],
        "auto_setup_fields": [
            "General marketing content pack",
            "Generic voice agent script",
            "Google Business Profile setup",
            "Mini-site palette + festival schedule",
        ],
    },
]

# Business-type id → niche key (fast lookup, avoid double scan)
_BY_ID: dict[str, str] = {b["id"]: b["niche"] for b in BUSINESS_TYPES}


def get_business_types() -> list[dict[str, Any]]:
    """Wizard UI ke liye business-type list (pure data)."""
    return [dict(b) for b in BUSINESS_TYPES]


def resolve_niche(business_type: str) -> str:
    """Business-type id → niche key. Unknown → 'general'."""
    return _BY_ID.get(str(business_type or "").strip().lower(), "general")


def get_template_preview(business_type: str) -> dict[str, Any]:
    """Business type ke liye wizard preview: niche + auto-setup fields + script lookup."""
    bt = str(business_type or "").strip().lower()
    entry = next((b for b in BUSINESS_TYPES if b["id"] == bt), None)
    niche = resolve_niche(bt)
    preview: dict[str, Any] = {
        "business_type": bt,
        "niche": niche,
        "label": (entry or {}).get("label", "Other Business"),
        "emoji": (entry or {}).get("emoji", "🏪"),
        "products": (entry or {}).get("products", ["marketing", "voice"]),
        "auto_setup_fields": (entry or {}).get("auto_setup_fields", []),
        "has_voice_script": _has_niche_script(niche),
        "has_knowledge_pack": _has_niche_knowledge(niche),
        "has_niche_catalog": _has_niche_catalog(niche),
    }
    return preview


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _has_niche_script(niche: str) -> bool:
    try:
        from app.voice_agent.niche_scripts_data import NICHE_SCRIPTS

        return niche in NICHE_SCRIPTS
    except Exception:
        return False


def _has_niche_knowledge(niche: str) -> bool:
    try:
        from app.niche_knowledge_data import NICHE_KNOWLEDGE

        return niche in NICHE_KNOWLEDGE
    except Exception:
        return False


def _has_niche_catalog(niche: str) -> bool:
    try:
        from app.niches import NICHES

        return niche in NICHES
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Voice script preview — done-for-you setup step 3
# --------------------------------------------------------------------------- #


def get_script_preview(
    business_type: str,
    *,
    business_name: str = "",
    services: str = "",
    offer: str = "",
) -> dict[str, Any]:
    """Niche script ka live preview — editable opening ke liye base.

    Returns: {"ok", "niche", "has_script", "opening", "suggested_opening",
    "discovery": [...], "closing", "objection_types": [...]}. Kabhi raise nahi.

    - ``opening`` = niche script ka asli opening (placeholders filled).
    - ``suggested_opening`` = services/offer se personalized opening (jo wizard UI
      pre-fill karega; user edit kar sakta hai).
    """
    try:
        bt = str(business_type or "").strip().lower()
        niche = resolve_niche(bt)
        biz = (business_name or "aapka business").strip()
        svc = (services or "").strip()
        off = (offer or "").strip()

        out: dict[str, Any] = {
            "ok": True,
            "niche": niche,
            "has_script": _has_niche_script(niche),
            "opening": "",
            "suggested_opening": "",
            "discovery": [],
            "closing": "",
            "objection_types": [],
        }

        try:
            from app.voice_agent.niche_scripts import get_script

            script = get_script(niche)
            opening = str(script.get("opening") or "").strip()
            if opening:
                opening = (
                    opening.replace("[Company]", biz)
                    .replace("[Name]", "Swara")
                    .replace("[Project]", "hamare project")
                    .replace("[project]", "hamare project")
                    .replace("raha hoon", "rahi hoon")
                )
                out["opening"] = opening
            out["discovery"] = [str(q) for q in (script.get("discovery") or [])[:4]]
            out["closing"] = str(script.get("closing") or "").strip()
            out["objection_types"] = list((script.get("objections") or {}).keys())
        except Exception as exc:
            out["ok"] = False
            out["error"] = f"script lookup: {exc}"[:160]

        # Personalized suggested opening (services/offer aware).
        if svc or off:
            tail = f" — {off}" if off else ""
            out["suggested_opening"] = (
                f"Namaste, main Swara bol rahi hoon {biz} ki taraf se. "
                f"Hum {svc or 'apni services'} ke baare me baat karna chahte hain{tail}. "
                "Do minute baat kar sakti hoon?"
            )
        elif out["opening"]:
            out["suggested_opening"] = out["opening"]

        return out
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "niche": resolve_niche(business_type), "error": str(exc)[:160]}


# --------------------------------------------------------------------------- #
# Auto-setup apply — niche template client pe lagao
# --------------------------------------------------------------------------- #


def apply_auto_setup(
    client_id: str,
    business_type: str,
    *,
    niche_override: str = "",
    business_name: str = "",
    services: str = "",
    offer: str = "",
    opening_line: str = "",
) -> dict[str, Any]:
    """Business-type wizard auto-setup: niche resolve → niche snapshot apply +
    KB facts seed + services/offer/custom opening persist. Best-effort, never
    raises. Gated ONBOARD_WIZARD_APPLY.

    Reuses existing infra:
      - client_snapshots.apply_niche_to_client (palette, journeys, festivals)
      - niche_knowledge_data (facts/benefits) → client record "wizard_knowledge"
      - NICHES catalog meta (offer/tagline/services) — already inside snapshot
      - ``opening_line`` → client record ``wizard_setup.opening_line`` (voice agent
        isko live calls me use karta hai, agar set ho)

    Returns {"ok": bool, "business_type", "niche", "applied": [...], "error"?}.
    """
    out: dict[str, Any] = {
        "ok": False,
        "business_type": business_type,
        "niche": "",
        "applied": [],
    }
    cid = str(client_id or "").strip()
    if not cid:
        out["error"] = "client_id required"
        return out
    if not _flag("ONBOARD_WIZARD_APPLY"):
        out["error"] = "ONBOARD_WIZARD_APPLY disabled"
        return out

    niche = str(niche_override or "").strip().lower() or resolve_niche(business_type)
    out["niche"] = niche

    try:
        from app.platform import client_snapshots

        snap = client_snapshots.apply_niche_to_client(cid, niche)
        if snap.get("ok"):
            out["applied"].append("niche_snapshot")
        else:
            out["snapshot_warning"] = str(snap.get("error") or "niche snapshot failed")[:160]
    except Exception as exc:
        out["snapshot_warning"] = f"snapshot exception: {exc}"[:160]

    try:
        from app.niche_knowledge_data import NICHE_KNOWLEDGE

        pack = NICHE_KNOWLEDGE.get(niche) or {}
        facts = [str(f) for f in (pack.get("facts") or [])[:4]]
        benefits = [str(b) for b in (pack.get("benefits") or [])[:4]]
        if facts or benefits:
            kb_note = {
                "source": "onboard_wizard",
                "business_type": business_type,
                "niche": niche,
                "facts": facts,
                "benefits": benefits,
                "scripted": _has_niche_script(niche),
            }
            # Persist wizard knowledge onto the client record (best-effort).
            _persist_client_knowledge(cid, kb_note)
            out["applied"].append("knowledge_seed")
    except Exception as exc:
        out["knowledge_warning"] = f"knowledge seed exception: {exc}"[:160]

    # Services / offer / custom opening → client record (voice agent runtime reads
    # ``wizard_setup.opening_line``; services/offer niche content me use honge).
    svc = (services or "").strip()
    off = (offer or "").strip()
    opn = (opening_line or "").strip()
    if svc or off or opn:
        try:
            _persist_setup_fields(
                cid,
                business_name=(business_name or "").strip(),
                services=svc,
                offer=off,
                opening_line=opn,
                business_type=business_type,
                niche=niche,
            )
            out["applied"].append("services_offer_opening")
        except Exception as exc:
            out["fields_warning"] = f"setup fields persist: {exc}"[:160]

    out["ok"] = bool(out["applied"])
    return out


def _persist_client_knowledge(client_id: str, note: dict[str, Any]) -> None:
    """Client record pe wizard setup note lagao. Best-effort, never raises."""
    try:
        from app.marketing import clients_store

        rec = clients_store.get_client(client_id) or {}
        wizard = dict(rec.get("wizard_setup") or {})
        wizard["last_auto_setup"] = note
        # NOTE: update_client(cid, **fields) hai — positional dict TypeError deta
        # hai (silent swallow, 2026-08-17 E2E catch). Isliye ** unpack zaroori.
        clients_store.update_client(client_id, **{"wizard_setup": wizard})
    except Exception as exc:
        logger.debug("[onboard_wizard] persist knowledge skip: %s", exc)


def _persist_setup_fields(
    client_id: str,
    *,
    business_name: str = "",
    services: str = "",
    offer: str = "",
    opening_line: str = "",
    business_type: str = "",
    niche: str = "",
) -> None:
    """Client record pe services/offer/custom opening persist karo. Best-effort."""
    try:
        from app.marketing import clients_store

        fields: dict[str, Any] = {"wizard_setup": {"opening_line": opening_line or ""}}
        if services:
            fields["services"] = services
        if offer:
            fields["offer"] = offer
        wizard = None
        rec = clients_store.get_client(client_id) or {}
        if rec:
            wizard = dict(rec.get("wizard_setup") or {})
        if wizard is not None:
            wizard["opening_line"] = opening_line or ""
            wizard["business_type"] = business_type
            wizard["niche"] = niche
            if services:
                wizard["services"] = services
            if offer:
                wizard["offer"] = offer
            fields["wizard_setup"] = wizard
        # update_client(cid, **fields) — positional dict TypeError dega (E2E 2026-08-17).
        clients_store.update_client(client_id, **fields)
    except Exception as exc:
        logger.debug("[onboard_wizard] persist setup fields skip: %s", exc)


__all__ = [
    "BUSINESS_TYPES",
    "get_business_types",
    "resolve_niche",
    "get_template_preview",
    "get_script_preview",
    "apply_auto_setup",
]
