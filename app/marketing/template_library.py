"""Curated template library — AdBanao-style ready prompts (niche × occasion).

Studio gallery ke liye; har template ek proven image-gen prompt + caption-seed.
Pure data, no deps. `list_templates(niche, occasion)` filter karta."""

from __future__ import annotations

_T = [
    # (id, title, niche, occasion, prompt)
    (
        "dw-jewel",
        "Diwali Jewellery Glow",
        "jewellery_store",
        "diwali",
        "luxurious Diwali jewellery poster, golden diyas, sparkling necklace on maroon silk, festive rangoli border, space for offer text, premium Indian aesthetic",
    ),
    (
        "dw-solar",
        "Diwali Solar Savings",
        "solar",
        "diwali",
        "Diwali themed solar panel rooftop poster, diyas + fairy lights, bright savings theme, Indian home, festive orange-gold palette, text space top",
    ),
    (
        "dw-generic",
        "Diwali Sale Burst",
        "general",
        "diwali",
        "vibrant Diwali sale poster, firecracker burst, diyas, gift boxes, bold discount badge space, festive Indian colors",
    ),
    (
        "hl-gym",
        "New Year Fitness",
        "gym",
        "new_year",
        "energetic gym poster, fit Indian people training, neon highlights, new year transformation theme, bold typography space",
    ),
    (
        "sm-cafe",
        "Cafe Monsoon Combo",
        "cafe",
        "monsoon",
        "cozy cafe poster, steaming chai + pakora by rainy window, warm lighting, monsoon combo offer space, Indian street-style",
    ),
    (
        "sm-salon",
        "Salon Festive Makeover",
        "salon",
        "festive",
        "elegant salon poster, Indian bride makeup glam, soft gold bokeh, festive makeover package text space",
    ),
    (
        "rs-clinic",
        "Clinic Health Checkup",
        "clinic",
        "general",
        "clean medical clinic poster, friendly Indian doctor, calm blue palette, full-body checkup offer layout, trust badges space",
    ),
    (
        "rs-dental",
        "Dental Smile Offer",
        "dental_clinic",
        "general",
        "bright dental clinic poster, perfect smile closeup, mint-blue clean design, family dental offer space",
    ),
    (
        "re-prop",
        "Property Launch",
        "real_estate",
        "launch",
        "premium real-estate poster, modern Indian apartment tower at dusk, golden light, launch price banner space, skyline",
    ),
    (
        "ed-coach",
        "Admission Open",
        "coaching_institute",
        "admission",
        "coaching institute admission poster, confident Indian students, books + success arrows, bold ADMISSION OPEN space, energetic blue-orange",
    ),
    (
        "ag-tractor",
        "Kisan Offer",
        "agriculture_equipment",
        "harvest",
        "Indian farm equipment poster, tractor in green field sunrise, kisan harvest offer theme, earthy colors, dealer text space",
    ),
    (
        "au-service",
        "Car Service Camp",
        "car_service",
        "general",
        "auto service camp poster, gleaming car on lift, tools, mechanic, free-checkup banner space, red-black pro palette",
    ),
    (
        "ho-room",
        "Weekend Stay Deal",
        "hotel",
        "weekend",
        "boutique hotel poster, cozy deluxe room warm lights, hill view window, weekend staycation deal space",
    ),
    (
        "fd-sweet",
        "Mithai Special",
        "sweet_shop",
        "festive",
        "Indian sweet shop poster, kaju katli + ladoo platter closeup, marigold garland, festive special price space",
    ),
    (
        "cl-boutique",
        "Wedding Collection",
        "boutique",
        "wedding",
        "designer boutique poster, embroidered lehenga on mannequin, royal backdrop, wedding collection text space, jewel tones",
    ),
    (
        "el-shop",
        "Electronics Mega Sale",
        "electronics_store",
        "sale",
        "electronics mega sale poster, TV + fridge + phone collage, lightning bolt energy, EMI badge space, blue-yellow retail style",
    ),
    (
        "pl-plumber",
        "Emergency Service",
        "plumber",
        "general",
        "trusty plumber service poster, smiling Indian plumber with wrench, 30-min response badge, clean utility blue design",
    ),
    (
        "tr-travel",
        "Holiday Package",
        "travel_agency",
        "holiday",
        "travel agency poster, Indian family at scenic Himachal mountains, suitcase + plane motif, package price burst space",
    ),
    (
        "ev-decor",
        "Event Decor Showcase",
        "event_management",
        "wedding",
        "wedding event decor poster, grand mandap floral arch, fairy lights, elegant gold-ivory palette, booking CTA space",
    ),
    (
        "ny-generic",
        "New Year Offer",
        "general",
        "new_year",
        "celebratory New Year sale poster, fireworks over city, champagne gold + midnight blue, big % space",
    ),
    (
        "hi-holi",
        "Holi Color Blast",
        "general",
        "holi",
        "Holi festival poster, colorful gulal powder explosion, joyful celebration, white base with rainbow splashes, offer space",
    ),
    (
        "id-eid",
        "Eid Mubarak Special",
        "general",
        "eid",
        "elegant Eid poster, crescent moon + lantern, emerald-gold palette, festive feast spread, greeting + offer space",
    ),
    (
        "rk-rakhi",
        "Rakhi Gifts",
        "general",
        "raksha_bandhan",
        "Raksha Bandhan poster, decorated rakhi + gift boxes + sweets, warm sibling theme, pastel festive design, offer space",
    ),
    (
        "in-independence",
        "Freedom Sale",
        "general",
        "independence_day",
        "Independence Day sale poster, tricolor theme tasteful, kite motifs, 15 August badge, patriotic clean design",
    ),
]


def list_templates(niche: str = "", occasion: str = "", limit: int = 50) -> dict:
    niche = (niche or "").strip().lower()
    occasion = (occasion or "").strip().lower()
    out = []
    for tid, title, n, occ, prompt in _T:
        if niche and n not in (niche, "general"):
            continue
        if occasion and occasion not in occ:
            continue
        out.append({"id": tid, "title": title, "niche": n, "occasion": occ, "prompt": prompt})
    return {"templates": out[: max(1, limit)], "total": len(out)}
