"""Lead Harvester — multi-source lead collection, automated loop ke liye.

Research: docs/LeadHarvester_Research_2026.md. LEGAL-FIRST design:
  - Sources sirf compliant: Places/OSM (existing prospector), Brave Search API
    (keyed) → business ki APNI website se public contacts, data.gov.in OGD
    (open license) seed names, website-enrich (email_finder + find_contacts).
  - JustDial/IndiaMART/LinkedIn/Facebook AUTO-scrape KABHI nahi (ToS/ban/IT-Act)
    — directory domains explicitly SKIP hote. Unka path = manual CSV import.
  - Polite: per-run fetch caps, timeouts, UA, sleep; anti-bot bypass NAHI.

Pipeline: collect (enabled sources) → normalize → validate (phonenumbers E.164
+ email MX) → dedupe (store phone/email) → persist (prospector._append = jsonl
+ DB mirror + pitch) → rescore. GATED loop `LEAD_HARVESTER=1` (manual API run
flag-independent). Gated sources bina key = inert skip. Kabhi raise nahi.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Per-niche asyncio locks — prevents concurrent harvests for the same niche
# from racing on _existing_keys() → _append() dedupe check.
_niche_locks: dict[str, asyncio.Lock] = {}

_RUNS = os.path.join("data", "harvest_runs.jsonl")
_FETCH_CAP = 6  # per websearch run site fetches
_HTTP_TIMEOUT = 10.0
_UA = "LeadGenAI/1.0 (business contact discovery; admin@leadsgenai.in)"

# In domains ko AUTO kabhi fetch/scrape nahi karte (ToS / ban / personal-data)
_BLOCKED_DOMAINS = (
    "justdial.com",
    "indiamart.com",
    "sulekha.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "quora.com",
    "reddit.com",
    "google.com",
    "wikipedia.org",
    "amazon.",
    "flipkart.",
    "olx.",
    "quikr.",
)

_PHONE_RE = re.compile(r"(?:\+91[\-\s]?|0)?([6-9]\d{9})")

# ── Ingest validation (2026-07-05) ───────────────────────────────────────────
# Backlog fix: websearch SERP page-titles ("Top 10 Home Loan ... 2026",
# "XYZ | Justdial") business_name ban jaate the + page ke kisi bhi 10-digit
# (bank helpline) ko phone maan lete the → junk "ready" pool → platform_dial
# IVR-disaster ka root-enabler. Gate DEFAULT ON; HARVEST_INGEST_VALIDATION=0
# = kill-switch (dial_gate test-mode jaisa default-ON precedent).
_JUNK_NAME_RE = re.compile(
    r"(?:"
    r"\b(?:top|best)\s+\d{1,3}\b"  # "Top 10 ...", "Best 5 ..."
    r"|^\d{1,3}\s+(?:best|top)\b"  # "10 Best ..."
    r"|\b(?:near me|price list|interest rates?|apply online|customer care"
    r"|toll[- ]?free|helpline|list of|how to|what is|contact numbers?"
    r"|phone numbers?)\b"
    r"|\b(?:irctc|indian railways?|railway station|train station"
    r"|government office|municipal corporation|police station|fire station)\b"
    r"|\b20\d{2}\b"  # listicle year ("... in Pune 2026")
    r"|https?://|www\."
    r"|\.(?:com|in|co|org|net)\b"  # domain in name = page title
    r"|\|"  # pipe = SERP title separator
    r")",
    re.IGNORECASE,
)
_MAX_NAME_LEN = 90  # real business names itne lambe nahi hote; page titles hote hain


def ingest_validation_enabled() -> bool:
    """Default ON. HARVEST_INGEST_VALIDATION=0 = disable (rollback switch)."""
    return os.environ.get("HARVEST_INGEST_VALIDATION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def ingest_reject_reason(name: str, phone10: str, email: str, source: str) -> str:
    """'' = accept; warna reject-reason. Pure function (unit-testable, no env).

    Rules (backlog 2026-07-05): junk-title regex sab par; websearch (unstructured
    SERP) leads ko valid mobile YA verified email chahiye. Structured sources
    (osm/opendata/GMB) ke naam real hote hain — sirf junk-regex + length check.
    """
    n = (name or "").strip()
    if not n:
        return ""  # empty-name handling existing dedupe/persist logic par chhodo
    if len(n) > _MAX_NAME_LEN:
        return "name_too_long"
    if _JUNK_NAME_RE.search(n):
        return "junk_title"
    if (source or "") == "websearch" and not phone10 and not email:
        return "websearch_no_contact"
    return ""


def enabled() -> bool:
    return os.environ.get("LEAD_HARVESTER", "0").strip().lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_run(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_RUNS) or ".", exist_ok=True)
        with open(_RUNS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _blocked(url: str) -> bool:
    u = (url or "").lower()
    return any(d in u for d in _BLOCKED_DOMAINS)


def _existing_keys() -> tuple[set[str], set[str]]:
    """Store me already-known phones (10-digit) + emails — dedupe ke liye."""
    phones: set[str] = set()
    emails: set[str] = set()
    try:
        from app.platform import prospector

        for r in prospector._read_all():
            p = re.sub(r"\D", "", str(r.get("phone") or ""))[-10:]
            if len(p) == 10:
                phones.add(p)
            e = str(r.get("email") or "").strip().lower()
            if e:
                emails.add(e)
    except Exception:
        pass
    return phones, emails


# ---------------------------------------------------------------- validate


def _valid_phone(raw: str) -> str:
    """E.164 IN mobile ya empty. phonenumbers ho to use, warna regex fallback.

    ADR-027 (council 2026-07-06): docstring hamesha se "mobile" kehta tha par
    is_mobile IGNORE hota tha — FIXED_LINE cloud-IVR DIDs (Livspace/HDFC type)
    pass ho ke "ready" prospects bante the. Ab valid-but-NON-mobile => reject
    ('' return, regex fallback me NAHI girta). Lib-absent par regex [6-9] hi
    guard hai (purana behavior)."""
    try:
        from app.lead_scraper import phone_validate

        v = phone_validate.validate_in(raw)
        if v.get("ok") and v.get("e164"):
            return str(v["e164"]) if v.get("is_mobile") else ""
    except Exception:
        pass
    m = _PHONE_RE.search(raw or "")
    return f"+91{m.group(1)}" if m else ""


async def _valid_email(email: str) -> str:
    """Syntax+MX verified email ya empty (sender-rep safe)."""
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return ""
    try:
        from app.lead_scraper import email_verify

        r = email_verify.verify(e)  # sync, {"ok", "email", "reason"}, never raises
        if isinstance(r, dict) and r.get("ok"):
            return str(r.get("email") or e)
        return ""
    except Exception:
        return e  # verifier import na ho to syntax-pass rakho (outreach apna MX-gate karta hai)


# ---------------------------------------------------------------- sources


async def _src_prospector(niche: str, city: str, limit: int) -> dict[str, Any]:
    """Primary: existing Places+OSM rotation (khud persist karta)."""
    # When nested under the daily prospect job, niche scrape already ran —
    # calling niche_prospector again multiplies wall-clock into SoftTimeLimit.
    if os.environ.get("SKIP_HARVEST_PROSPECTOR_SRC", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return {
            "source": "prospector",
            "skipped": "nested_under_prospect",
            "persisted_internally": False,
            "leads": [],
        }
    try:
        from app.platform import niche_prospector

        res = await niche_prospector.run(batch=2, limit_per_query=max(2, limit // 2))
        return {
            "source": "prospector",
            "persisted_internally": True,
            "detail": f"covered={res.get('covered', [])}",
            "leads": [],
        }
    except Exception as e:
        return {"source": "prospector", "error": str(e)[:120], "leads": []}


async def _web_results(q: str) -> tuple[str, list[dict[str, Any]]]:
    """Search results waterfall: self-hosted SearXNG (FREE, gated SEARXNG_URL) →
    Brave API (gated BRAVE_API_KEY). Returns (provider, [{title,url}]). '' = none."""
    try:
        from app.integrations import searxng

        if searxng.enabled():
            res = await searxng.search(q, count=10)
            if res:
                return "searxng", res
    except Exception:
        pass
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        return "", []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers={"User-Agent": _UA}) as client:
            r = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": q, "count": 10, "country": "IN"},
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
            )
            if r.status_code != 200:
                return "", []
            return "brave", ((r.json().get("web") or {}).get("results") or [])[:10]
    except Exception:
        return "", []


async def _src_websearch(niche: str, city: str, limit: int) -> dict[str, Any]:
    """Web search (SearXNG self-hosted FREE → Brave fallback) → business websites
    → public contacts. Directory/social domains SKIP (ToS). Bina dono = inert."""
    if not (
        os.environ.get("SEARXNG_URL", "").strip() or os.environ.get("BRAVE_API_KEY", "").strip()
    ):
        return {"source": "websearch", "skipped": "no SEARXNG_URL/BRAVE_API_KEY", "leads": []}
    leads: list[dict[str, Any]] = []
    try:
        import httpx

        q = f"{niche.replace('_', ' ')} {city} contact phone"
        provider, results = await _web_results(q)
        if not results:
            return {
                "source": "websearch",
                "error": f"no results (provider={provider or 'none'})",
                "leads": [],
            }
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers={"User-Agent": _UA}) as client:
            fetched = 0
            for item in results:
                url = str(item.get("url") or "")
                if not url or _blocked(url) or fetched >= min(_FETCH_CAP, limit):
                    continue
                fetched += 1
                try:
                    page = await client.get(url, follow_redirects=True)
                    if page.status_code != 200:
                        continue
                    from app.lead_scraper import web_extract

                    contacts = web_extract.find_contacts(page.text) or {}
                    phones = contacts.get("phones") or []
                    emails = contacts.get("emails") or []
                    if not phones and not emails:
                        m = _PHONE_RE.search(page.text)
                        phones = [m.group(0)] if m else []
                    if phones or emails:
                        leads.append(
                            {
                                "business_name": str(item.get("title") or "")[:150],
                                "phone": phones[0] if phones else "",
                                "email": emails[0] if emails else "",
                                "website": url,
                                "city": city,
                                "niche": niche,
                                "source": "websearch",
                            }
                        )
                except Exception:
                    continue
                await asyncio.sleep(0.5)  # polite
    except Exception as e:
        return {"source": "websearch", "error": str(e)[:120], "leads": leads}
    return {"source": "websearch", "provider": provider, "leads": leads}


def _rec_ci(rec: dict[str, Any], *keys: str) -> str:
    """Case-insensitive multi-key get (data.gov.in uses CamelCase EnterpriseName/District,
    other datasets use snake_case enterprise_name — be agnostic to both)."""
    low = {str(k).lower(): v for k, v in (rec or {}).items()}
    for k in keys:
        v = low.get(k.lower())
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _ogd_name(rec: dict[str, Any]) -> str:
    """Extract a business/unit name from a data.gov.in record — FIELD-NAME-AGNOSTIC.
    (Udyam = `EnterpriseName`; other MSME datasets = name_of_unit/firm_name/... .)"""
    n = _rec_ci(
        rec,
        "enterprisename",
        "enterprise_name",
        "name_of_enterprise",
        "name_of_unit",
        "unit_name",
        "firm_name",
        "company_name",
        "msme_name",
        "name",
    )
    if n:
        return n
    for k, v in (rec or {}).items():  # fuzzy fallback: any name/unit/enterprise/firm field
        if (
            any(t in str(k).lower() for t in ("name", "unit", "enterprise", "firm"))
            and isinstance(v, str)
            and v.strip()
        ):
            return v.strip()
    return ""


def _ogd_city(rec: dict[str, Any], default: str) -> str:
    """Prefer the record's own district/city over the rotation default (Udyam = `District`)."""
    return _rec_ci(rec, "city", "district", "district_name", "location", "place", "town") or default


def _ogd_activity(rec: dict[str, Any]) -> str:
    """Udyam MajorActivity / NIC text — used to classify the lead's niche."""
    return _rec_ci(rec, "majoractivity", "major_activity", "activity", "nic_name", "nic5digitcode")


def _ogd_pincode(rec: dict[str, Any]) -> str:
    return _rec_ci(rec, "pincode", "pin_code", "pin")


# Metros where the Udyam District name != the common city name (else filter returns 0).
_METRO_DISTRICT = {
    "bengaluru": "BANGALORE URBAN",
    "bangalore": "BANGALORE URBAN",
    "mumbai": "MUMBAI",
    "delhi": "NEW DELHI",
    "new delhi": "NEW DELHI",
    "hyderabad": "HYDERABAD",
    "gurugram": "GURGAON",
    "gurgaon": "GURGAON",
    "prayagraj": "ALLAHABAD",
    "vadodara": "VADODARA",
}


def _udyam_district(city: str) -> str:
    c = (city or "").strip()
    return _METRO_DISTRICT.get(c.lower(), c.upper())


async def _src_opendata(niche: str, city: str, limit: int) -> dict[str, Any]:
    """data.gov.in OGD (gated DATA_GOV_IN_API_KEY + DATA_GOV_RESOURCE_ID) —
    Udyam/MSME unit names = seed leads (no phone; enrich baad me). Open license."""
    key = os.environ.get("DATA_GOV_IN_API_KEY", "").strip()
    rid = os.environ.get("DATA_GOV_RESOURCE_ID", "").strip()
    if not key or not rid:
        return {"source": "opendata", "skipped": "no key/resource", "leads": []}
    leads: list[dict[str, Any]] = []
    try:
        import urllib.parse
        import urllib.request

        # IMPORTANT: build the query with LITERAL brackets — httpx percent-encodes
        # filters[District] to filters%5BDistrict%5D, which data.gov.in does NOT match
        # (returns 0). urllib sends the URL as-given, so the District filter actually
        # applies and pulls THAT city's units out of ~30 lakh (Udyam District = UPPERCASE).
        qs = f"api-key={key}&format=json&limit={min(limit, 20)}"
        if city.strip():
            # metro alias so e.g. Bengaluru -> BANGALORE URBAN actually matches the District
            qs += f"&filters[District]={urllib.parse.quote(_udyam_district(city))}"
        url = f"https://api.data.gov.in/resource/{rid}?{qs}"

        def _fetch() -> dict[str, Any]:
            req = urllib.request.Request(url, headers={"User-Agent": "leadgenai/1.0"})
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310  # nosec B310
                return json.loads(resp.read().decode("utf-8", "replace")) or {}

        data = await asyncio.to_thread(_fetch)
        for rec in (data.get("records") or [])[:limit]:
            name = _ogd_name(rec)
            if name:
                leads.append(
                    {
                        "business_name": name[:150],
                        "phone": "",
                        "email": "",
                        "website": "",
                        "city": _ogd_city(rec, city),
                        "pincode": _ogd_pincode(rec),
                        "major_activity": _ogd_activity(rec),
                        "niche": niche,
                        "source": "opendata",
                    }
                )
    except Exception as e:
        return {"source": "opendata", "error": str(e)[:120], "leads": leads}
    return {"source": "opendata", "leads": leads}


def _enrich_max_attempts() -> int:
    """Bounded retry per prospect (default 2). EMAIL_ENRICH_MAX_ATTEMPTS override."""
    try:
        return max(1, int(os.environ.get("EMAIL_ENRICH_MAX_ATTEMPTS", "2") or "2"))
    except Exception:
        return 2


def _enrich_row_delay_s() -> float:
    """Inter-row politeness delay. Har row ek ALAG third-party site hai (per-host
    rate ka sawaal nahi) — yeh delay hamare apne egress/DNS burst ko chhota rakhta
    hai. EMAIL_ENRICH_ROW_DELAY_S se tune (0 = off)."""
    try:
        return max(0.0, min(5.0, float(os.environ.get("EMAIL_ENRICH_ROW_DELAY_S", "0.3") or 0.3)))
    except Exception:
        return 0.3


async def enrich_missing_emails(limit: int = 8, deadline_s: float | None = None) -> dict[str, Any]:
    """Store ke website-wale prospects jinka email nahi — email_finder waterfall
    (site-extract → pattern → MX). Kabhi raise nahi.

    STALL FIX (2026-07-25): pehle yeh har run ``_read_all()`` ke HEAD se wahi
    pehli ``limit`` no-email rows dobara try karta tha — failure ka koi marker
    nahi tha, isliye scan kabhi aage badha hi nahi (prod audit: 4,137
    ready+website rows bina email, sendable backlog sirf 182). Ab har attempt
    ``email_enrich_attempts`` + ``email_enrich_last_at`` stamp karta hai (ek
    atomic bulk write), aur attempts >= EMAIL_ENRICH_MAX_ATTEMPTS (default 2)
    wali rows SKIP hoti hain — scan har run naye prospects tak pahunchta hai.

    STATE-MACHINE FIX: email milte hi ``needs_enrich``/``new`` row "ready"
    PROMOTE hoti hai (outreach sirf status='ready' padhta hai — pehle enriched
    rows black hole me rehti thi). ready/sent/replied/client/dead ka status
    KABHI touch nahi hota — sirf email field milti hai.

    ``deadline_s`` = wall-clock budget. Har row se PEHLE check hota hai, aur
    expire hone pe loop TOOT-ta hai — par jo attempts ho chuke wo phir bhi
    likhe jaate hain (progress kabhi discard nahi). Yeh Celery sweep ke liye
    zaroori hai: ek row worst-case ~20s+ le sakti hai (2 × 10s HTTP timeout),
    isliye bina deadline ke ek "chhota" batch bhi task ke soft_time_limit ko
    paar kar sakta hai — aur SoftTimeLimitExceeded us poore batch ke attempt
    markers ko gira dega, yaani wahi stall wapas.
    """
    found = 0
    tried = 0
    exhausted = 0
    deadline_hit = False
    updates: dict[str, dict[str, Any]] = {}
    t0 = time.monotonic()
    row_delay = _enrich_row_delay_s()
    try:
        from app.platform import email_finder, prospector

        max_attempts = _enrich_max_attempts()
        now = _now()
        for r in prospector._read_all():
            if tried >= limit:
                break
            if deadline_s is not None and (time.monotonic() - t0) >= deadline_s:
                deadline_hit = True
                break
            if r.get("email") or not r.get("website"):
                continue
            attempts = 0
            try:
                attempts = int(r.get("email_enrich_attempts") or 0)
            except Exception:
                attempts = 0
            if attempts >= max_attempts:
                exhausted += 1
                continue
            tried += 1
            fields: dict[str, Any] = {
                "email_enrich_attempts": attempts + 1,
                "email_enrich_last_at": now,
            }
            try:
                res = await email_finder.find(
                    r["website"], owner_name=str(r.get("business_name") or "")
                )
                best = (res.get("emails") or [None])[0] if isinstance(res, dict) else None
                email = best.get("email") if isinstance(best, dict) else best
                if email:
                    fields["email"] = str(email)[:200]
                    if (r.get("status") or "") in ("needs_enrich", "new"):
                        fields["status"] = "ready"
                    found += 1
            except Exception:
                pass  # attempt marker phir bhi likho — warna scan wahi atkega
            pid = str(r.get("id") or "")
            if pid:
                updates[pid] = fields
            if row_delay:
                await asyncio.sleep(row_delay)
        if updates:
            prospector.set_prospect_fields_bulk(updates)
    except Exception as e:
        # Best-effort flush: jo attempts ho chuke unke markers bachao, warna
        # ek transient error poore batch ko dobara-try-able chhod deta hai.
        if updates:
            try:
                from app.platform import prospector as _p

                _p.set_prospect_fields_bulk(updates)
            except Exception:
                pass
        return {
            "tried": tried,
            "found": found,
            "skipped_exhausted": exhausted,
            "deadline_hit": deadline_hit,
            "error": str(e)[:120],
        }
    return {
        "tried": tried,
        "found": found,
        "skipped_exhausted": exhausted,
        "deadline_hit": deadline_hit,
    }


async def _src_osm(niche: str, city: str, limit: int) -> dict[str, Any]:
    """FREE + keyless + ToS-clean: OpenStreetMap Overpass as a FIRST-CLASS source —
    independent of Google-Maps quota (Places fallback skips OSM when it succeeds, so
    this always-on source widens India-wide coverage). Off-loop (urllib is blocking),
    polite (25s timeout, capped). Phone-less names get email-enriched downstream."""
    leads: list[dict[str, Any]] = []
    try:
        from app.platform.prospector import _osm_search

        # niche keywords make a better Overpass tag match than the raw key
        try:
            from app.niches import NICHES

            _kws = (NICHES.get(niche) or {}).get("keywords") or []
            query = str(_kws[0] if isinstance(_kws, list) and _kws else niche.replace("_", " "))
        except Exception:
            query = niche.replace("_", " ")
        rows = await asyncio.to_thread(_osm_search, query, city, limit)
        for r in rows or []:
            nm = str(r.get("business_name") or r.get("name") or "").strip()
            if not nm:
                continue
            leads.append(
                {
                    "business_name": nm[:200],
                    "phone": str(r.get("phone") or ""),
                    "email": "",
                    "website": str(r.get("website") or ""),
                    "city": city,
                    "niche": niche,
                    "source": "osm",
                }
            )
    except Exception as e:
        return {"source": "osm", "error": str(e)[:120], "leads": leads}
    return {"source": "osm", "leads": leads}


SOURCES = {
    "prospector": _src_prospector,
    "osm": _src_osm,  # free keyless OSM Overpass — independent of Google-Maps quota
    "websearch": _src_websearch,
    "opendata": _src_opendata,
}


# ---------------------------------------------------------------- pipeline


async def run_harvest(
    niche: str = "", city: str = "", limit: int = 10, sources: list[str] | None = None
) -> dict[str, Any]:
    """Multi-source harvest: collect → validate → dedupe → persist → rescore.
    Gated sources bina key inert. Kabhi raise nahi."""
    try:
        if not niche or not city:
            from app.marketing.channel_experiments import _pick_niche_city

            n2, c2 = _pick_niche_city()
            niche = niche or n2
            city = city or c2

        keys = [s for s in (sources or list(SOURCES.keys())) if s in SOURCES]
        results = await asyncio.gather(
            *(SOURCES[s](niche, city, limit) for s in keys), return_exceptions=True
        )

        new = 0
        skipped = 0
        junk_skipped = 0
        per_source: dict[str, Any] = {}
        _validate = ingest_validation_enabled()
        from app.platform import prospector

        # Per-niche lock: dedupe+persist under lock so concurrent harvests
        # for the same niche don't insert duplicates (M3 fix).
        async with _niche_locks.setdefault(niche, asyncio.Lock()):
            known_phones, known_emails = _existing_keys()
            for res in results:
                if isinstance(res, Exception):
                    continue
                src = res.get("source", "?")
                per_source[src] = {k: v for k, v in res.items() if k != "leads"}
                src_new = 0
                for lead in res.get("leads") or []:
                    phone = _valid_phone(str(lead.get("phone") or ""))
                    email = await _valid_email(str(lead.get("email") or ""))
                    p10 = phone[-10:] if phone else ""
                    if (
                        (p10 and p10 in known_phones)
                        or (email and email in known_emails)
                        or (not p10 and not email and not lead.get("business_name"))
                    ):
                        skipped += 1
                        continue
                    name = str(lead.get("business_name") or "Unknown")[:200]
                    # Ingest gate (2026-07-05): SERP-junk titles / contact-less
                    # websearch rows "ready" pool me kabhi na aayein.
                    if _validate:
                        _rej = ingest_reject_reason(name, p10, email, str(lead.get("source") or ""))
                        if _rej:
                            junk_skipped += 1
                            per_source[src]["junk"] = int(per_source[src].get("junk") or 0) + 1
                            logger.debug(
                                f"[harvester] ingest reject ({_rej}): {name[:60]!r} src={src}"
                            )
                            continue
                    rec = {
                        "id": str(uuid.uuid4()),
                        "found_at": _now(),
                        "business_name": name,
                        "phone": phone,
                        "address": "",
                        "city": city,
                        "niche": niche,
                        "rating": None,
                        "reviews_count": None,
                        "website": str(lead.get("website") or "")[:300],
                        "has_website": bool(lead.get("website")),
                        "email": email,
                        "source_query": f"harvest:{lead.get('source', '?')}",
                        "pitch": prospector.build_pitch(name, niche, city),
                        "wa_link": "",
                        "google_search_link": "",
                        "status": "ready" if (p10 or email) else "needs_enrich",
                    }
                    if prospector._append(rec):
                        new += 1
                        src_new += 1
                        if p10:
                            known_phones.add(p10)
                        if email:
                            known_emails.add(email)
                per_source[src]["new"] = src_new

        enr = await enrich_missing_emails(limit=6)

        try:
            from app.platform import lead_scoring

            await lead_scoring.rescore_db(limit=200)
        except Exception:
            pass

        # Cadence auto-enroll — naye harvested leads ko omnichannel sequence me daalo.
        # Gated CADENCE_ENGINE=1 (inert agar off — cadence khud guard karta hai).
        cadence_enrolled = 0
        try:
            import os as _os

            if _os.environ.get("CADENCE_ENGINE", "").strip() in ("1", "true", "yes") and new > 0:
                from app.marketing import cadence
                from app.platform import prospector as _p

                # prospects.jsonl se last N+10 rows padho, naye niche/city/ready wale chuno
                _all = _p._read_all()  # full jsonl, sorted by insertion
                _recent = [
                    r
                    for r in _all[-(new + 20) :]
                    if r.get("niche") == niche
                    and r.get("city") == city
                    and r.get("status") == "ready"
                ][:new]
                if _recent:
                    cadence_enrolled = cadence.enroll_many(_recent)  # returns int
                    logger.debug(f"[harvester] cadence auto-enrolled {cadence_enrolled} leads")
        except Exception as _cad_e:
            logger.debug(f"[harvester] cadence enroll skip: {_cad_e}")

        summary = {
            "ok": True,
            "niche": niche,
            "city": city,
            "sources": per_source,
            "new_leads": new,
            "deduped": skipped,
            "junk_skipped": junk_skipped,
            "enrich": enr,
            "cadence_enrolled": cadence_enrolled,
            "at": _now(),
        }
        _append_run(summary)
        try:
            from app.platform import team

            team.log_event(
                "dev",
                "lead_harvest",
                f"{niche}/{city}: +{new} naye leads (dedup {skipped}, enrich {enr.get('found', 0)}, cadence {cadence_enrolled})",
            )
        except Exception:
            pass
        return summary
    except Exception as e:
        logger.warning(f"[harvester] run failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def run_loop_sweep() -> dict[str, Any]:
    """Loop hook (gated LEAD_HARVESTER) — daily prospect job / self_improve se.

    GTM_TARGETING=1: systematically work through the City x Niche coverage matrix
    (least-recently-covered first), N pairs/run within the API budget — so over time
    every city x niche gets covered "one by one". Else: single rotation pick (legacy)."""
    if not enabled():
        return {"enabled": False}
    # Udyam-PRIMARY pipeline (gated UDYAM_PIPELINE) — runs alongside the harvest in the
    # daily sweep: data.gov.in Udyam seeds -> Maps + website enrich. Result merged in.
    _udyam: dict[str, Any] | None = None
    try:
        from app.platform import udyam_pipeline

        if udyam_pipeline.enabled():
            from app.platform.niche_prospector import city_rotation

            _udyam = {"new": 0, "cities": []}
            for _c in (city_rotation() or [])[:2]:
                _ur = await udyam_pipeline.run(limit=15, city=_c)
                _udyam["new"] += int((_ur or {}).get("new") or 0)
                _udyam["cities"].append(
                    {"city": _c, "new": _ur.get("new"), "seeds": _ur.get("seeds")}
                )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[harvester] udyam sweep skipped: %s", e)
    try:
        from app.platform import gtm_targeting

        if gtm_targeting.enabled():
            import time

            try:
                n_pairs = int(os.environ.get("GTM_PAIRS_PER_RUN", "6") or "6")
            except Exception:
                n_pairs = 6
            # Hard cap when nested under Celery prospect (SoftTimeLimit margin).
            try:
                max_pairs = int(os.environ.get("HARVEST_LOOP_MAX_PAIRS", "2") or "2")
            except Exception:
                max_pairs = 2
            n_pairs = max(1, min(n_pairs, max(1, max_pairs)))
            pairs = gtm_targeting.next_targets(max(1, n_pairs))
            if pairs:
                out: dict[str, Any] = {"enabled": True, "mode": "gtm_matrix", "new": 0, "pairs": []}
                for p in pairs:
                    r = await run_harvest(niche=p["niche"], city=p["city"])
                    _new = int((r or {}).get("new") or 0)
                    out["new"] += _new
                    out["pairs"].append({"niche": p["niche"], "city": p["city"], "new": _new})
                    gtm_targeting.mark_covered(p, yield_count=_new, ts=time.time())
                if _udyam is not None:
                    out["udyam"] = _udyam
                return out
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[harvester] gtm matrix sweep skipped: %s", e)
    _h = await run_harvest()
    if _udyam is not None and isinstance(_h, dict):
        _h["udyam"] = _udyam
    return _h


def recent_runs(limit: int = 15) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_RUNS):
            with open(_RUNS, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows[-limit:][::-1]


def source_status() -> dict[str, Any]:
    """Kaunse sources armed hain (keys present) — ops visibility."""
    return {
        "enabled_loop": enabled(),
        "prospector": bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()) or "osm-fallback",
        "websearch": bool(
            os.environ.get("SEARXNG_URL", "").strip() or os.environ.get("BRAVE_API_KEY", "").strip()
        ),
        "opendata": bool(os.environ.get("DATA_GOV_IN_API_KEY", "").strip())
        and bool(os.environ.get("DATA_GOV_RESOURCE_ID", "").strip()),
        "blocked_domains_policy": list(_BLOCKED_DOMAINS[:6]) + ["..."],
    }


__all__ = [
    "run_harvest",
    "run_loop_sweep",
    "enrich_missing_emails",
    "recent_runs",
    "source_status",
    "enabled",
    "ingest_reject_reason",
    "ingest_validation_enabled",
    "SOURCES",
]
