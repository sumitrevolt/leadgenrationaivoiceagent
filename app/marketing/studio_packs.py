"""
Studio packs — pure-logic (zero-LLM, zero-network, never-raise) generators for
the Customer AI Marketing Studio. Each returns a uniform shape:

    {"sections": [{"title": str, "items": [str, ...]}, ...], ...extra}

so the frontend can render ALL of them with one generic formatter. Niche-aware
where cheap; always non-empty. These power the structural growth-OS features
(#43,46,47,49,50,61,64,66,67,69,70,72,74,77,88,90) that don't need an external
API or an LLM call.
"""

from __future__ import annotations

import html as _html
import json as _json


def _label(niche: str) -> str:
    return (niche or "business").replace("_", " ").strip().title() or "Business"


def _sec(title: str, items: list[str]) -> dict:
    return {"title": title, "items": [str(i) for i in items if str(i).strip()]}


def business_description(business_name: str, niche: str, city: str = "") -> dict:
    biz = (business_name or "Aapka Business").strip()
    lbl = _label(niche)
    loc = f" {city}".rstrip()
    where = f" {city} me" if city else ""
    return {"sections": [
        _sec("Short bio (Insta/GBP)", [
            f"{biz} — {lbl}{where}. Quality service, sahi daam, time pe delivery. 📞 Call/WhatsApp karein.",
            f"{lbl} ka bharosemand naam{where} — {biz}. Aaj hi enquiry karein!",
        ]),
        _sec("Long description (website/GBP)", [
            f"{biz} ek trusted {lbl.lower()} service hai{where}. Humara focus hai customer ki "
            f"satisfaction — fast response, transparent pricing aur reliable kaam. Naye ho ya purane "
            f"customer, har kaam ko poori dhyan se karte hain. Aaj hi humse judein.",
        ]),
        _sec("Tagline ideas", [
            f"{lbl} ki tension? {biz} hai na!",
            "Sahi kaam, sahi daam, time pe.",
            "Aapka bharosa, hamari zimmedari.",
        ]),
    ]}


def brand_palette(niche: str) -> dict:
    palettes = {
        "salon": ["#D6336C primary", "#F8C291 accent", "Font: Poppins / Playfair"],
        "restaurant": ["#E8590C primary", "#FFD43B accent", "Font: Poppins / Lobster"],
        "dentist": ["#1C7ED6 primary", "#63E6BE accent", "Font: Inter / Nunito"],
        "gym": ["#212529 primary", "#F03E3E accent", "Font: Oswald / Montserrat"],
        "real_estate": ["#0B7285 primary", "#FFA94D accent", "Font: Inter / Merriweather"],
    }
    key = (niche or "").strip().lower()
    pal = palettes.get(key, ["#4263EB primary", "#15AABF accent", "Font: Inter / Poppins"])
    return {"sections": [
        _sec("Suggested brand colors", pal),
        _sec("Usage tips", [
            "Primary color = headings + buttons (CTA).",
            "Accent = highlights/offers only (10% area).",
            "Background white/light rakho — text readable rahe.",
            "Ek hi font-pair har jagah use karo (consistency = trust).",
        ]),
    ]}


def customer_avatar(niche: str, city: str = "") -> dict:
    lbl = _label(niche)
    loc = city or "aapke area"
    return {"sections": [
        _sec("Ideal customer profile", [
            f"Location: {loc} + 5-10 km radius",
            "Age: 25-45 (decision-maker)",
            f"Need: {lbl.lower()} ki reliable, value-for-money service",
            "Where they search: Google 'near me', Instagram, WhatsApp groups",
        ]),
        _sec("Unke dard (pain points)", [
            "Pichli jagah se kharab experience / over-charging",
            "Time pe response na milna",
            "Quality ka bharosa nahi",
        ]),
        _sec("Aapka hook", [
            "Fast WhatsApp reply + transparent rate",
            "Reviews/photos se proof dikhao",
            "First-time customer offer do",
        ]),
    ]}


def seasonal_offers(niche: str) -> dict:
    lbl = _label(niche)
    return {"sections": [
        _sec("Winter (Nov-Jan)", [f"{lbl} winter-special package", "Year-end / New Year offer", "Wedding-season combo"]),
        _sec("Summer (Mar-Jun)", ["Summer care offer", "Beat-the-heat discount", "Holiday/vacation combo"]),
        _sec("Monsoon (Jul-Sep)", ["Monsoon-ready service", "Rainy-day home-service offer", "Festival pre-booking"]),
        _sec("Festive (Oct-Nov)", ["Diwali/Dussehra mega offer", "Festive gift card", "Bulk/family package"]),
    ]}


def local_event_campaign(niche: str, city: str = "") -> dict:
    loc = city or "aapke sheher"
    return {"sections": [
        _sec("Local event tie-in ideas", [
            f"{loc} ke local fair/mela me stall ya banner",
            "School/college events ke aas-paas targeted offer",
            "Local cricket/sports match day special",
            "Society/RWA events me sponsorship ya flyer",
        ]),
        _sec("Post angle", [
            f"'{loc} ke logon ke liye special' — local pride hook",
            "Local landmark ka mention (relatable lagta hai)",
            "Local language/slang ka thoda tadka",
        ]),
    ]}


def case_study(business_name: str, niche: str) -> dict:
    biz = (business_name or "Aapka Business").strip()
    lbl = _label(niche)
    return {"sections": [
        _sec("Case study structure (fill karo)", [
            "Customer kaun tha (bina naam ke bhi chalega): ____",
            "Problem kya thi: ____",
            f"{biz} ne kya kiya: ____",
            "Result (number/photo ke saath): ____",
        ]),
        _sec("Ready template", [
            f"Ek customer {lbl.lower()} problem leke aaye the. {biz} ne unhe sahi solution diya — "
            f"fast, affordable aur bharose ke saath. Aaj wo khush hain aur dobara aate hain. "
            f"Aapko bhi aisa result chahiye? Aaj WhatsApp karein! 🙌",
        ]),
    ]}


def grid_planner(niche: str) -> dict:
    lbl = _label(niche)
    return {"sections": [
        _sec("9-grid Instagram plan (3x3)", [
            "1. Intro/About post", "2. Service highlight", "3. Customer review",
            "4. Before/After ya result", f"5. {lbl} tip/educational", "6. Offer/CTA",
            "7. Team/behind-the-scenes", "8. Festival/trend post", "9. Another review/UGC",
        ]),
        _sec("Visual tip", [
            "Ek color theme rakho (brand colors) — grid clean dikhe.",
            "Alternate: photo → quote → photo pattern.",
        ]),
    ]}


def highlights(niche: str) -> dict:
    return {"sections": [
        _sec("Instagram Story Highlights (banao)", [
            "⭐ Reviews", "🛠 Services", "💰 Offers", "📍 Location/Timing",
            "📸 Work/Gallery", "❓ FAQs", "📞 Contact",
        ]),
        _sec("Tip", ["Har highlight ka ek clean cover icon banao (brand color).",
                     "Reviews + Offers highlight sabse zyada tap hote hain."]),
    ]}


def voiceover_script(business_name: str, niche: str, offer: str = "") -> dict:
    biz = (business_name or "Aapka Business").strip()
    lbl = _label(niche)
    off = (offer or "special offer").strip()
    return {"sections": [
        _sec("15-sec Hinglish voiceover", [
            f"Namaste! {lbl} ki tension? {biz} hai na. "
            f"Quality service, sahi daam, time pe kaam. Abhi {off} chal raha hai — "
            f"call ya WhatsApp karo, aaj hi! {biz}.",
        ]),
        _sec("Delivery tip", [
            "Pehli line energetic bolo (hook).",
            "Number/offer slow + clear bolo.",
            "Last me business naam confident bolo.",
        ]),
    ]}


def youtube_metadata(business_name: str, niche: str, topic: str = "") -> dict:
    biz = (business_name or "Aapka Business").strip()
    lbl = _label(niche)
    tp = (topic or f"{lbl} tips").strip()
    return {"sections": [
        _sec("Title options", [
            f"{tp} | {biz}",
            f"{lbl} {tp} — jo koi nahi batata!",
            f"Best {lbl} {tp} (2026) | {biz}",
        ]),
        _sec("Description", [
            f"Is video me {biz} aapko {tp} ke baare me batata hai. {lbl} ki best service ke liye "
            f"call/WhatsApp karein. Like + Subscribe zaroor karein!",
        ]),
        _sec("Tags", [", ".join([lbl.lower(), tp.lower(), f"{lbl.lower()} near me",
                                  "hinglish", "small business", biz.lower()])]),
    ]}


def faq_page(business_name: str, niche: str) -> dict:
    biz = (business_name or "Aapka Business").strip()
    lbl = _label(niche)
    return {"sections": [
        _sec("Common FAQs (website pe daalo)", [
            f"Q: {biz} kya service deta hai?  A: {lbl} ki full service — quality + sahi daam.",
            "Q: Rate kya hai?  A: Service pe depend karta — WhatsApp karein, exact quote denge.",
            "Q: Timing kya hai?  A: Subah 9 se shaam 7 (call anytime).",
            "Q: Booking kaise?  A: WhatsApp ya call — 2 min me confirm.",
            "Q: Payment options?  A: Cash / UPI / online — sab chalega.",
        ]),
    ]}


def schema_markup(business_name: str, niche: str, city: str = "", phone: str = "") -> dict:
    biz = (business_name or "Aapka Business").strip()
    data = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": biz,
        "description": f"{_label(niche)} service" + (f" in {city}" if city else ""),
        "areaServed": city or "India",
        "telephone": phone or "",
        "priceRange": "₹₹",
    }
    js = _json.dumps(data, ensure_ascii=False, indent=2)
    return {"sections": [
        _sec("LocalBusiness JSON-LD (website <head> me daalo)", [js]),
        _sec("Kaise lagayein", [
            "Ye code apni website ke <head> section me <script type=\"application/ld+json\"> ke andar paste karo.",
            "Google ko aapka business clearly samajh aata = local search me upar.",
        ]),
    ]}


def conversion_tracking(niche: str) -> dict:
    return {"sections": [
        _sec("Conversion tracking setup (checklist)", [
            "☐ Google Analytics (GA4) website pe lagao",
            "☐ Har 'Call' / 'WhatsApp' button pe click-event track karo",
            "☐ Form submit ko conversion mark karo",
            "☐ Google Ads chalate ho to conversion tag lagao",
            "☐ UTM links use karo (kaunsa post/ad laaya track ho)",
        ]),
        _sec("Kyun zaroori", ["Pata chalega kaunsa channel asli leads laata — wahin paisa lagao."]),
    ]}


def lost_lead_reason(niche: str) -> dict:
    return {"sections": [
        _sec("Lead convert kyun nahi hua — common reasons", [
            "Late reply (2 min se zyada) → lead thanda ho gaya",
            "Price clear nahi bataya → confusion",
            "Follow-up nahi kiya (1 message me chhod diya)",
            "Trust nahi bana (reviews/photos nahi dikhaye)",
            "Galat time pe contact kiya",
        ]),
        _sec("Fix", [
            "Har lead ko 2 min me reply (speed-to-lead).",
            "Day 1/3/7 follow-up sequence chalao.",
            "Reviews + before/after dikhao.",
        ]),
    ]}


def complaint_recovery(business_name: str) -> dict:
    biz = (business_name or "Hamari team").strip()
    return {"sections": [
        _sec("Angry customer recovery flow", [
            "1. Turant respond karo (der = aur gussa).",
            "2. Sun lo + sorry bolo (defend mat karo pehle).",
            "3. Solution offer karo (refund/redo/discount).",
            "4. Personally follow-up karo ki theek hua.",
            "5. Theek hone pe politely review update request.",
        ]),
        _sec("Ready reply", [
            f"Namaste 🙏 {biz} ki taraf se sorry — aapko dikkat hui. Main personally ise theek "
            f"karwata hoon. Bas 2 min me aapse baat karta hoon, sahi solution denge.",
        ]),
    ]}


def ugc_request(business_name: str) -> dict:
    biz = (business_name or "Hamari team").strip()
    return {"sections": [
        _sec("Customer se photo/video maangne ke messages", [
            f"Namaste! 🙏 {biz} ki service achhi lagi ho to ek chhota photo/video bhej dijiye — "
            f"hum aapko feature karenge (aur aapko surprise gift!) 🎁",
            f"Aapka 10-sec video testimonial dusron ki bahut madad karega — bhej denge? {biz} 🙌",
        ]),
        _sec("Tip", ["UGC (customer ke real photo/video) sabse zyada trust banata — incentive do (discount/feature)."]),
    ]}


__all__ = [
    "business_description", "brand_palette", "customer_avatar", "seasonal_offers",
    "local_event_campaign", "case_study", "grid_planner", "highlights",
    "voiceover_script", "youtube_metadata", "faq_page", "schema_markup",
    "conversion_tracking", "lost_lead_reason", "complaint_recovery", "ugc_request",
]
