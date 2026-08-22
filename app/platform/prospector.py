"""
Prospector — HAMARE platform ke liye Tier-1 client hunting (Rohan ka kaam).
===========================================================================

Tier-1 = businesses jo HAMARE client banenge (solar installer, real estate
agency, coaching institute, interior designer...). Google Maps scraper se
unhe dhundo, dedupe karo, personalized Hinglish WhatsApp pitch banao aur
data/prospects.jsonl me queue karo — phir /app/outreach page se user ek-ek
ko "📲 WhatsApp bhejo" karta hai.

Public API:
  - run_prospecting(limit_per_query=10) -> dict   (async; NEVER raises)
  - list_prospects(status=None, limit=100) -> list (newest first)
  - mark_prospect(pid, status) -> bool             (ready→sent/replied/client/dead)

Scraper best-effort hai: Google Maps API key na ho to playwright fallback,
wo bhi na ho to query skip ho jaati hai (count me dikhta hai) — kabhi crash
nahi. Scheduler (team_scheduler) roz 09:30 IST pe chalata hai.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _PROSPECTS_FILE() -> str:
    """Prospect JSONL store — resolved per call, never frozen at import.

    ~20MB / 18k records; whole-file rewrite on update. Bytes stay in-checkout
    until a separate host cutover — this resolver only makes the CODE follow
    LEADGEN_RUNTIME_DATA_ROOT when cutover is later activated.
    """
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="sales.prospects",
            legacy_path=Path("data") / "prospects.jsonl",
            target_segments=("sales", "prospects.jsonl"),
        )
    )


# Allowed pipeline statuses.
VALID_STATUSES = ("ready", "sent", "replied", "client", "dead")

# Google/OSM can return infrastructure or public-service entities for broad
# category queries. They are not local SMB prospects for LeadGen's marketing
# product and frequently carry railway/bank helpline numbers.
_NON_SMB_PLACE_TYPES = frozenset(
    {
        "airport",
        "bus_station",
        "government_office",
        "local_government_office",
        "police",
        "police_station",
        "post_office",
        "railway_station",
        "train_station",
        "transit_station",
    }
)


def _scraped_reject_reason(
    name: str,
    phone10: str,
    email: str,
    source: str,
    primary_type: str = "",
    types: tuple[str, ...] | list[str] = (),
    business_status: str = "",
) -> str:
    """Hard quality gate shared by Google/OSM prospect ingestion."""
    if str(business_status or "").upper() == "CLOSED_PERMANENTLY":
        return "closed_business"
    place_types = {str(t).strip().lower() for t in (types or ())}
    if str(primary_type or "").strip().lower() in _NON_SMB_PLACE_TYPES:
        return "non_smb_place_type"
    if place_types & _NON_SMB_PLACE_TYPES:
        return "non_smb_place_type"
    try:
        from app.platform.lead_harvester import ingest_reject_reason

        return ingest_reject_reason(name, phone10, email, source)
    except Exception:
        # Name safety remains fail-closed if the shared gate cannot import.
        lowered = str(name or "").lower()
        return (
            "official_or_helpline_name"
            if any(
                token in lowered
                for token in ("irctc", "indian railways", "railway station", "helpline")
            )
            else ""
        )


def is_quality_approved(record: dict[str, Any] | None) -> bool:
    """Return whether a stored prospect is safe to surface/send.

    This re-checks historical JSONL rows too, so records ingested before the
    current junk-title rules cannot leak into outreach after a deploy.
    """
    if not isinstance(record, dict):
        return False
    name = str(record.get("business_name") or record.get("name") or "").strip()
    digits = "".join(c for c in str(record.get("phone") or "") if c.isdigit())
    phone10 = digits[-10:] if len(digits) >= 10 else ""
    source_query = str(record.get("source_query") or "")
    source = (
        source_query.split(":", 1)[-1] if source_query.startswith("harvest:") else "google_maps"
    )
    return not _scraped_reject_reason(
        name,
        phone10,
        str(record.get("email") or "").strip(),
        source,
        primary_type=str(record.get("primary_type") or ""),
        types=record.get("types") or (),
        business_status=str(record.get("business_status") or ""),
    )


# --------------------------------------------------------------------------- #
# Targets — kaunse niches ke businesses dhundhne hain (env-overridable).
# Env PROSPECT_TARGETS = JSON list: [{"niche": "...", "query": "...",
# "cities": ["...", ...]}, ...]
# --------------------------------------------------------------------------- #
_DEFAULT_CITIES = ["Pune", "Mumbai", "Nagpur", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Ahmedabad"]
_DEFAULT_TARGETS: list[dict[str, Any]] = [
    {"niche": "solar_residential", "query": "solar installer", "cities": _DEFAULT_CITIES},
    {"niche": "real_estate", "query": "real estate agency", "cities": _DEFAULT_CITIES},
    {"niche": "coaching", "query": "coaching institute", "cities": _DEFAULT_CITIES},
    {"niche": "interior_designers", "query": "interior designer", "cities": _DEFAULT_CITIES},
    {"niche": "dental", "query": "dental clinic", "cities": _DEFAULT_CITIES},
    {"niche": "beauty", "query": "beauty salon", "cities": _DEFAULT_CITIES},
    {"niche": "restaurant", "query": "restaurant", "cities": _DEFAULT_CITIES},
    {"niche": "gym", "query": "gym fitness", "cities": _DEFAULT_CITIES},
]

# Niche-specific pain line for the pitch (fallback generic).
_NICHE_PAIN: dict[str, str] = {
    "solar_residential": "solar inquiries me aadhe log sirf price puch ke gayab ho jaate hain",
    "real_estate": "site-visit tak pahunchne wale serious buyers dhundna mushkil hai",
    "coaching": "admission season me har inquiry ko time pe follow-up nahi ho paata",
    "interior_designers": "naye project ke liye serious clients tak pahunchna costly hai",
}
_GENERIC_PAIN = "naye customers tak pahunchna har mahine mehenga aur slow hai"


def _targets() -> list[dict[str, Any]]:
    """PROSPECT_TARGETS env (JSON) ya defaults. Malformed env -> defaults."""
    raw = os.environ.get("PROSPECT_TARGETS", "").strip()
    if not raw:
        return _DEFAULT_TARGETS
    try:
        data = json.loads(raw)
        out: list[dict[str, Any]] = []
        for t in data if isinstance(data, list) else []:
            if not isinstance(t, dict) or not t.get("query"):
                continue
            cities = t.get("cities") or _DEFAULT_CITIES
            out.append(
                {
                    "niche": str(t.get("niche") or "general"),
                    "query": str(t["query"]),
                    "cities": [str(c) for c in cities if str(c).strip()],
                }
            )
        if out:
            return out
    except Exception as e:
        logger.warning(f"[prospector] PROSPECT_TARGETS parse failed, using defaults: {e}")
    return _DEFAULT_TARGETS


# --------------------------------------------------------------------------- #
# Phone helpers
# --------------------------------------------------------------------------- #
def _phone_digits(raw: str | None) -> str:
    """Sirf digits; +91/0 prefix normalize karke 10-digit lautao ('' = unusable)."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return ""


def _phone_type(phone10: str) -> str:
    """ADR-027 quality tag: 'mobile'/'flom'/'fixed'/'tollfree'/'invalid'/'unknown'/''.

    dial_gate.phone_quality (libphonenumber IN plan) se — FIXED_LINE cloud-IVR
    DIDs record me hi visible ho jate (dial_gate inhe promotional-dial pe waise
    bhi block karta; yeh tag dashboards/backfill/email-routing ke liye)."""
    if not phone10:
        return ""
    try:
        from app.telephony.dial_gate import phone_quality

        return phone_quality(phone10)
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------- #
# Pitch builder (template — NO LLM, instant + deterministic)
# --------------------------------------------------------------------------- #
def _niche_display(niche: str) -> str:
    """NICHES se readable naam (lazy, fallback = key prettified)."""
    try:
        from app.niches import NICHES

        cfg = NICHES.get(niche) or {}
        name = cfg.get("display_name") or cfg.get("name")
        if name:
            # Pitch ke liye short rakho — "(...)" wala suffix kaat do.
            return str(name).split("(")[0].strip()[:40]
    except Exception:
        pass
    return (niche or "business").replace("_", " ").title()


def build_pitch(business_name: str, niche: str, city: str = "") -> str:
    """Short personalized Hinglish WhatsApp pitch (3 lines)."""
    pain = _NICHE_PAIN.get(niche, _GENERIC_PAIN)
    nd = _niche_display(niche)
    return (
        f"Namaste {business_name} ji 🙏 Main Sumit, LeadGen AI se. "
        f"{nd} business me {pain} — hamara AI voice agent aapke liye "
        f"interested customers ko khud call karke QUALIFIED leads laata hai. "
        f"Shuruat me 10 leads bilkul FREE. 2-min live demo yahan suniye: "
        f"leadsgenai.in/app/test-call"
    )


def build_personalized_pitch(
    business_name: str,
    niche: str,
    city: str = "",
    rating: float | None = None,
    reviews_count: int | None = None,
    has_website: bool | None = None,
) -> str:
    """Real Google data (rating/reviews/website) se personalized Hinglish pitch.

    Diagnosis-line REAL signal pe choose hoti hai:
      - low/no reviews (<20)  -> reviews badhane ka offer
      - decent rating, no website / kam presence -> regular posts/photos line
      - no website            -> mini page + Google profile setup
    Hamesha FREE audit + 3 poster CTA pe khatam. NEVER raises (caller fallback).
    """
    try:
        nd = _niche_display(niche)
        try:
            rv = int(reviews_count) if reviews_count is not None else None
        except Exception:
            rv = None
        try:
            rt = float(rating) if rating is not None else None
        except Exception:
            rt = None

        diag: str
        if rv is not None and rv < 20:
            cnt = "ek bhi" if rv == 0 else f"sirf {rv}"
            diag = (
                f"aapke Google pe {cnt} review{'s' if rv != 1 else ''} hain — "
                f"main reviews badhane ka system de dunga"
            )
        elif rt is not None and rt > 0:
            diag = (
                f"aapki rating {rt}⭐ achhi hai par Google pe regular "
                f"posts/photos nahi dikhe — top pe aane ke liye wahi chahiye"
            )
        elif has_website is False:
            diag = (
                "aapki website bhi nahi dikhi — ek mini page + Google " "profile dono set kar dunga"
            )
        else:
            diag = (
                "Google pe aapki online presence aur strong ki ja sakti hai — "
                "regular posts, reviews aur profile sab handle kar dunga"
            )

        # website-missing ko piggyback karo (agar review/rating line bani ho).
        if has_website is False and "website" not in diag:
            diag += " (website bhi nahi dikhi — wo bhi set kar dunga)"

        return (
            f"Namaste {business_name} ji 🙏 Main Sumit, LeadGen AI se. "
            f"{nd} ke liye — {diag}. "
            f"FREE audit + 3 sample posters bhej doon? — leadsgenai.in/audit"
        )
    except Exception:
        # Kabhi raise nahi — generic pitch pe fall back.
        return build_pitch(business_name, niche, city)


def _wa_link(phone10: str, pitch: str) -> str:
    return f"https://wa.me/91{phone10}?text={urllib.parse.quote(pitch)}"


def _google_search_link(business_name: str, city: str = "") -> str:
    """Manual phone-lookup fallback jab OSM phone na de."""
    q = f"{business_name} {city} phone".strip()
    return "https://www.google.com/search?q=" + urllib.parse.quote(q)


# --------------------------------------------------------------------------- #
# FREE no-key source — OpenStreetMap Overpass API (https://overpass-api.de)
# Koi API key nahi, legal (ODbL), stdlib urllib only. Best-effort: kabhi raise
# nahi karta. Query string → OSM tags map karke city ke area me businesses.
# --------------------------------------------------------------------------- #
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_OSM_UA = "LeadGenAI/1.0 (contact: sumitrevolt23@gmail.com)"

# query keyword (lowercase substring) -> list of Overpass tag filters.
# Pehla match jeetta hai; kuch na mile to naam-search fallback.
_OSM_TAG_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (("restaurant", "cafe", "food", "dhaba"), ['amenity~"^(restaurant|cafe|fast_food)$"']),
    (
        ("salon", "spa", "beauty", "parlour", "parlor", "hairdress"),
        ['shop~"^(hairdresser|beauty)$"'],
    ),
    (("gym", "fitness"), ['leisure="fitness_centre"']),
    (("jewel",), ['shop="jewelry"']),
    (("boutique", "clothing", "fashion", "apparel", "garment"), ['shop="clothes"']),
    (("bakery", "sweet", "cake"), ['shop~"^(bakery|confectionery)$"']),
    (("real estate", "property", "realtor"), ['office="estate_agent"']),
    (("hardware", "paint"), ['shop~"^(hardware|doityourself|paint)$"']),
    (("furniture", "decor"), ['shop="furniture"']),
    # Interior designers / decorators — a DEFAULT target. No single canonical OSM
    # tag, so cover the shop- and craft-level surfaces.
    (
        ("interior", "decorator", "interior_"),
        ['shop="interior_decoration"', 'craft="interior_decoration"'],
    ),
    (("pharmacy", "medical", "chemist"), ['amenity="pharmacy"']),
    (("mobile", "electronics"), ['shop~"^(mobile_phone|electronics)$"']),
    (("hotel", "resort", "lodge"), ['tourism~"^(hotel|guest_house|motel)$"']),
    (("photograph",), ['shop="photo"', 'craft="photographer"']),
    (("automobile", "car repair", "garage", "car service"), ['shop~"^(car_repair|car)$"']),
    (
        ("kirana", "supermarket", "grocery", "general store"),
        ['shop~"^(supermarket|convenience|general)$"'],
    ),
    (("travel", "tour"), ['shop="travel_agency"', 'office="travel_agent"']),
    (("gift", "stationery"), ['shop~"^(gift|stationery)$"']),
    (("dental", "dentist"), ['amenity="dentist"', 'healthcare="dentist"']),
    (
        ("doctor", "clinic", "hospital"),
        ['amenity~"^(clinic|hospital|doctors)$"', 'healthcare~"^(clinic|hospital|doctor)$"'],
    ),
    # Solar / renewable installers — the DEFAULT first target (see _DEFAULT_TARGETS).
    # Without a mapping, "solar installer" falls to the name~ fallback which returns
    # ~0 on Indian OSM, starving the free path. craft=solar_installer is a documented
    # OSM value; shop=solar covers retail-only concerns.
    (("solar", "renewable", "energy"), ['craft="solar_installer"', 'shop="solar"']),
    # Coaching institutes / tuition centers — a DEFAULT target. OSM India doesn't
    # have one canonical tag, so cover the plausible surfaces.
    (
        ("coaching", "tuition", "education"),
        ['amenity="prep_school"', 'office="educational_institution"', 'amenity="language_school"'],
    ),
]


def _osm_filters(query: str) -> list[str]:
    """Query string ko Overpass tag-filters me map karo (fallback name-search)."""
    q = (query or "").lower()
    for keys, filters in _OSM_TAG_MAP:
        if any(k in q for k in keys):
            return filters
    # Fallback: kuch bhi match na ho to naam pe case-insensitive search.
    safe = query.replace('"', "").replace("\\", "")
    return [f'name~"{safe}",i'] if safe else []


def _osm_search(query: str, city: str, limit: int) -> list[dict[str, Any]]:
    """OpenStreetMap Overpass se businesses dhundo (NO key). Kabhi raise nahi.

    `area[name="<city>"]` ke andar node/way/relation jinme matching tags hon.
    Return: list of {business_name, phone, address, city, website}. Naam-less
    elements skip. Failure (network/parse/koi bhi) -> [] return.
    """
    out: list[dict[str, Any]] = []
    try:
        city = (city or "").strip()
        if not city:
            return out
        filters = _osm_filters(query)
        if not filters:
            return out
        cap = max(1, min(int(limit), 50))
        city_esc = city.replace('"', "").replace("\\", "")

        # Har filter ke liye node/way/relation lines banao (area-scoped).
        stmts: list[str] = []
        for f in filters:
            for elem in ("node", "way", "relation"):
                stmts.append(f"{elem}(area.searchArea)[{f}];")
        body = "".join(stmts)
        ql = (
            f"[out:json][timeout:25];"
            f'area["name"="{city_esc}"]->.searchArea;'
            f"({body});"
            f"out tags center {cap * 4};"
        )

        data = urllib.parse.urlencode({"data": ql}).encode("utf-8")
        req = urllib.request.Request(
            _OVERPASS_URL,
            data=data,
            headers={"User-Agent": _OSM_UA, "Content-Type": "application/x-www-form-urlencoded"},
        )
        # Fixed, code-owned HTTPS Overpass endpoint; no user-controlled scheme.
        with urllib.request.urlopen(req, timeout=25) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8", "replace"))

        for el in payload.get("elements", []) or []:
            tags = el.get("tags") or {}
            name = str(tags.get("name") or "").strip()
            if not name:
                continue
            phone = str(
                tags.get("phone")
                or tags.get("contact:phone")
                or tags.get("contact:mobile")
                or tags.get("mobile")
                or ""
            ).strip()
            addr = str(tags.get("addr:full") or "").strip()
            if not addr:
                parts = [
                    tags.get("addr:housenumber"),
                    tags.get("addr:street"),
                    tags.get("addr:suburb"),
                    tags.get("addr:city") or city,
                ]
                addr = ", ".join(p for p in (str(x).strip() for x in parts if x) if p)
            website = str(tags.get("website") or tags.get("contact:website") or "").strip()
            email = str(tags.get("email") or tags.get("contact:email") or "").strip()
            out.append(
                {
                    "business_name": name,
                    "phone": phone,
                    "address": addr or city,
                    "city": city,
                    "website": website,
                    "email": email,
                }
            )
            if len(out) >= cap:
                break
    except Exception as e:  # network / HTTP / JSON / koi bhi — silently skip
        logger.debug(f"[prospector] OSM search '{query}' in {city} failed: {e}")
        return []
    return out


# --------------------------------------------------------------------------- #
# jsonl persistence
# --------------------------------------------------------------------------- #
def _read_all() -> list[dict[str, Any]]:
    """Saare prospects (parse-safe; corrupt lines skip)."""
    out: list[dict[str, Any]] = []
    try:
        # Resolver at each I/O site — binding to a local unbinds the allowlist (A3).
        if not os.path.isfile(_PROSPECTS_FILE()):
            return out
        with open(_PROSPECTS_FILE(), encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[prospector] prospects.jsonl read failed: {e}")
    return out


def _persist_prospect_to_db(rec: dict[str, Any]) -> bool:
    """Best-effort: prospect ko relational `leads` table me bhi likho (jsonl ke saath).

    Transactional + dedupe-by-phone. KABHI raise nahi karta — DB down / model missing /
    FK issue ho to chup-chaap skip (jsonl hi source of truth rehta). Yeh DB ko bharta
    hai taaki dashboards ka `_build_from_db` real leads dikhaye.
    """
    phone = "".join(ch for ch in str(rec.get("phone") or "") if ch.isdigit())
    if len(phone) < 10:
        return False
    try:
        import uuid as _uuid

        from app.models.base import get_db_session
        from app.models.lead import Lead, LeadSource, LeadStatus, lead_exists_for_phone

        with get_db_session() as db:
            # Format-variant-aware dedupe (audit 2026-07-04): this path always
            # stored digits-only, but the CRM/sheet import path stores "+91..."
            # — an exact-string check missed those, doubling every business
            # that both paths independently found.
            if lead_exists_for_phone(db, phone):
                return False  # dedupe
            db.add(
                Lead(
                    id=str(rec.get("id") or _uuid.uuid4()),
                    company_name=str(rec.get("business_name") or "Unknown")[:255],
                    contact_name=str(rec.get("contact_name") or "")[:255],
                    phone=phone,
                    email=(rec.get("email") or None),
                    address=(rec.get("address") or None),
                    city=(rec.get("city") or None),
                    category=(rec.get("category") or None),
                    niche=(rec.get("niche") or None),
                    source=LeadSource.GOOGLE_MAPS,
                    status=LeadStatus.NEW,
                    website=(rec.get("website") or None),
                )
            )
            db.commit()
        return True
    except Exception as e:  # never let a DB issue break the jsonl write
        logger.debug(f"[prospector] DB lead persist skipped: {e}")
        return False


def _append(rec: dict[str, Any]) -> bool:
    try:
        # Store hygiene (2026-06-12): timestamps — bina inke staleness/review
        # measure hi nahi ho sakti thi (pipeline review finding).
        _now = datetime.utcnow().isoformat() + "Z"
        rec.setdefault("created_at", _now)
        rec.setdefault("updated_at", _now)
        os.makedirs(os.path.dirname(_PROSPECTS_FILE()) or ".", exist_ok=True)
        with open(_PROSPECTS_FILE(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        # Mirror into the relational DB too (best-effort, never blocks the jsonl write).
        try:
            _persist_prospect_to_db(rec)
        except Exception:
            pass
        # ── analytics_store.record_lead (in-memory dashboard feed) ──────────
        # Naye prospect → analytics store me push karo taaki /analytics/leads
        # real data dikha sake (DB fallback bhi hai, par in-memory = zero-lag).
        try:
            from app.api.analytics import analytics_store as _ast_p

            _ast_p.record_lead(
                {
                    "created_at": rec.get("created_at"),
                    "status": rec.get("status") or "new",
                    "lead_score": rec.get("lead_score") or 0,
                    "lead_tier": "hot" if rec.get("is_hot_lead") else None,
                    "niche": rec.get("niche") or "",
                    "city": rec.get("city") or "",
                    "source": rec.get("source") or "scrape",
                }
            )
        except Exception:
            pass
        # ── niche_database mirror ─────────────────────────────────────────────
        # Scraped prospect ko niche_database (call-queue table) me bhi sync karo.
        # Yeh async function hai — sync context me fire-and-forget via asyncio.
        # Best-effort: fail hone pe jsonl write already ho chuka, koi loss nahi.
        try:
            niche = rec.get("niche") or "general"
            client_id = rec.get("client_id") or "platform"
            if niche and niche != "general":
                import asyncio as _asyncio

                from app.platform.niche_database import bulk_import as _ndb_bulk

                _row = {
                    "phone": rec.get("phone") or "",
                    "company": rec.get("name") or rec.get("business_name") or "",
                    "contact_name": rec.get("contact_name") or rec.get("owner_name") or "",
                    "email": rec.get("email") or "",
                    "city": rec.get("city") or "",
                    "state": rec.get("state") or "",
                    "source": rec.get("source") or "scrape",
                }
                try:
                    loop = _asyncio.get_running_loop()
                    loop.create_task(_ndb_bulk([_row], niche, client_id, "scrape"))
                except RuntimeError:
                    # No running event loop (sync context) — skip, DB mirror above is enough
                    pass
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning(f"[prospector] prospects.jsonl write failed: {e}")
        return False


def list_prospects(status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Prospects newest-first; optional status filter. Kabhi raise nahi karta."""
    try:
        rows = [r for r in _read_all() if is_quality_approved(r)]
        if status:
            rows = [r for r in rows if (r.get("status") or "ready") == status]
        rows.sort(key=lambda r: str(r.get("found_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 500))]
    except Exception as e:
        logger.warning(f"[prospector] list_prospects failed: {e}")
        return []


def pending_for_outreach(limit: int = 500) -> list[dict[str, Any]]:
    """Outreach-ready prospects = status 'ready' + VALID email + abhi tak NOT emailed,
    SAARE prospects me se (NOT `list_prospects`, jiska 500-newest hard-cap reachable
    backlog ko chhupa deta tha → emailable prospects kabhi email hi nahi hote the).
    Oldest-first (FIFO — purana backlog pehle drain). KABHI raise nahi karta.

    `list_prospects` ko replace nahi karta (UI/stats wahi) — sirf cold-email send-path
    (`auto_outreach.run_email_outreach`) iska source banega.
    """
    try:
        out: list[dict[str, Any]] = []
        for r in _read_all():
            if not is_quality_approved(r):
                continue
            if (r.get("status") or "ready") != "ready":
                continue
            if r.get("emailed_at"):
                continue
            e = str(r.get("email") or "").strip()
            if "@" not in e or "." not in e.rsplit("@", 1)[-1]:
                continue
            out.append(r)
        out.sort(key=lambda r: str(r.get("found_at") or ""))  # oldest first = backlog drain
        return out[: max(1, int(limit))]
    except Exception as e:
        logger.warning(f"[prospector] pending_for_outreach failed: {e}")
        return []


def set_prospect_fields(pid: str, fields: dict[str, Any]) -> bool:
    """Ek prospect par arbitrary fields set karo (e.g. emailed_at) — poora file
    rewrite (chhota hai). status VALID_STATUSES wala constraint yahan NAHI lagta
    (auto-outreach `emailed_at` jaisa custom marker set kar sake). KABHI raise
    nahi karta. True = mila + likha; missing id / write-fail = False."""
    try:
        if not isinstance(fields, dict) or not fields:
            return False
        rows = _read_all()
        found = False
        for r in rows:
            if r.get("id") == pid:
                r.update(fields)
                r["updated_at"] = datetime.utcnow().isoformat() + "Z"
                found = True
                break
        if not found:
            return False
        os.makedirs(os.path.dirname(_PROSPECTS_FILE()) or ".", exist_ok=True)
        tmp = _PROSPECTS_FILE() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _PROSPECTS_FILE())
        return True
    except Exception as e:
        logger.warning(f"[prospector] set_prospect_fields failed: {e}")
        return False


def set_prospect_fields_bulk(updates: dict[str, dict[str, Any]]) -> int:
    """Kai prospects par fields set karo EK hi file read+write me. Per-send
    `set_prospect_fields` har baar poora file read+rewrite karta tha = O(N²)
    (25 send × ~2k rows = OOM/SIGKILL). Yeh O(N): ek read, ek atomic write.

    `updates` = {pid: {field: value, ...}}. Returns kitne prospects match+update
    hue. Empty updates ya koi match nahi = 0 (koi write nahi). KABHI raise nahi."""
    try:
        if not isinstance(updates, dict) or not updates:
            return 0
        rows = _read_all()
        now = datetime.utcnow().isoformat() + "Z"
        n = 0
        for r in rows:
            f = updates.get(r.get("id"))
            if isinstance(f, dict) and f:
                r.update(f)
                r["updated_at"] = now
                n += 1
        if n == 0:
            return 0
        os.makedirs(os.path.dirname(_PROSPECTS_FILE()) or ".", exist_ok=True)
        tmp = _PROSPECTS_FILE() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _PROSPECTS_FILE())
        return n
    except Exception as e:
        logger.warning(f"[prospector] set_prospect_fields_bulk failed: {e}")
        return 0


def mark_prospect(pid: str, status: str) -> bool:
    """Ek prospect ka status update karo (poora file rewrite — chhota file hai).

    True = mila aur update hua. Invalid status / missing id = False.
    """
    try:
        status = (status or "").strip().lower()
        if status not in VALID_STATUSES:
            return False
        rows = _read_all()
        found = False
        for r in rows:
            if r.get("id") == pid:
                r["status"] = status
                r["status_at"] = datetime.utcnow().isoformat() + "Z"
                r["updated_at"] = r["status_at"]
                found = True
                break
        if not found:
            return False
        os.makedirs(os.path.dirname(_PROSPECTS_FILE()) or ".", exist_ok=True)
        tmp = _PROSPECTS_FILE() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _PROSPECTS_FILE())
        return True
    except Exception as e:
        logger.warning(f"[prospector] mark_prospect failed: {e}")
        return False


# --------------------------------------------------------------------------- #
# Main run — scraper best-effort, dedupe by phone digits, pitch + wa_link
# --------------------------------------------------------------------------- #
async def run_prospecting(limit_per_query: int = 15) -> dict[str, Any]:
    """Targets × cities pe Google Maps scraper chalao, naye prospects queue karo.

    Returns summary dict. NEVER raises — har query apne try/except me hai,
    scraper unavailable ho to skip count badhta hai.
    """
    summary: dict[str, Any] = {
        "ok": True,
        "new": 0,
        "duplicates": 0,
        "no_phone": 0,
        "queries_run": 0,
        "queries_failed": 0,
        "queries_empty": 0,
        "queries_capped": False,
        "quality_rejected": 0,
        "by_niche": {},
        "scraper": "unavailable",
    }
    try:
        # Dedupe set: existing prospects ke phone digits.
        seen: set[str] = set()
        for r in _read_all():
            d = _phone_digits(r.get("phone"))
            if d:
                seen.add(d)
            # business+city bhi (phone-less records repeat na ho)
            seen.add(
                f"{str(r.get('business_name') or '').strip().lower()}|{str(r.get('city') or '').strip().lower()}"
            )

        # Source select: real Google Maps key ho to API path; warna FREE OSM
        # Overpass (NO key, legal, stdlib). Playwright fallback use NAHI karte —
        # wo phones nahi deta. OSM = primary free source.
        scraper = None
        use_osm = True
        try:
            from app.lead_scraper.google_maps import GoogleMapsScraper

            cand = GoogleMapsScraper()
            key = str(getattr(cand, "api_key", "") or "")
            # Placeholder key ("your-google-maps-api-key" type) = real nahi.
            if key and not any(
                t in key.lower() for t in ("your-", "your_", "placeholder", "xxx", "changeme")
            ):
                scraper = cand
                use_osm = False
                summary["scraper"] = "google_maps_api"
        except Exception as e:
            logger.debug(f"[prospector] google_maps scraper unavailable: {e}")
        if use_osm:
            summary["scraper"] = "osm_overpass"

        # Cost-safety: Google Maps Place Details lookups are billed. Cap total
        # per run so the $200/mo free credit never blows up. OSM is free → no
        # cap there. Env PROSPECT_MAX_LOOKUPS (default 60).
        try:
            max_lookups = int(os.environ.get("PROSPECT_MAX_LOOKUPS", "60"))
        except Exception:
            max_lookups = 60
        max_lookups = max(0, max_lookups)
        summary["lookups_used"] = 0
        summary["lookups_capped"] = False

        # Email-extraction budget (auto-email outreach ke liye). Har prospect
        # ki website se email scrape karna network-slow hai → per-run cap.
        # Env PROSPECT_MAX_EMAIL_FETCH (default 20). OSM path pe websites kam
        # hoti hain → mostly skip. Scraper pe `_extract_email_from_website` ho
        # tabhi try hota hai. Kabhi run ko block/raise nahi karta.
        try:
            max_email_fetch = int(os.environ.get("PROSPECT_MAX_EMAIL_FETCH", "20"))
        except Exception:
            max_email_fetch = 20
        max_email_fetch = max(0, max_email_fetch)
        summary["emails_found"] = 0
        email_fetches = 0
        _email_fn = getattr(scraper, "_extract_email_from_website", None) if scraper else None

        targets = _targets()
        pairs: list[tuple[dict[str, Any], str]] = [
            (t, city) for t in targets for city in (t.get("cities") or [])
        ]

        # One query can walk Google New -> legacy -> scraping/OSM fallback; the
        # old 12 default target/city pairs could therefore overrun Celery's
        # 9-minute soft limit and pin the single heavy worker. Keep the daily
        # harvest useful (5 x up to 10 results) but bounded by default. An
        # operator can raise this deliberately after observing provider latency.
        try:
            max_queries = int(os.environ.get("PROSPECT_MAX_QUERIES", "10"))
        except Exception:
            max_queries = 10
        max_queries = max(1, min(max_queries, 20))
        if len(pairs) > max_queries:
            pairs = pairs[:max_queries]
            summary["queries_capped"] = True

        # WALL-CLOCK BUDGET (2026-07-18: 7 'prospect' jobs dlq:dead — 6×SoftTimeLimit
        # +1×hard-600s on 2026-07-17). PROSPECT_MAX_QUERIES fanout capta hai par time
        # nahi: ek slow provider chain (Google walk + OSM 25s timeouts + email fetch)
        # phir bhi Celery ke 540s soft limit ko cross kar sakti thi → retry burn →
        # DLQ. Ab har query se PEHLE monotonic budget check — exhausted = partial
        # summary ke saath GRACEFUL return, kabhi time-limit kill nahi.
        # Env PROSPECT_TIME_BUDGET_S (default 300 = worker soft-limit 540 se ~4 min margin;
        # was 420 — still SoftTimeLimit under NICHE_ROTATION + post-scrape rescore, 2026-07-20).
        try:
            time_budget_s = float(os.environ.get("PROSPECT_TIME_BUDGET_S", "300"))
        except Exception:
            time_budget_s = 300.0
        time_budget_s = max(5.0, min(time_budget_s, 480.0))
        t_start = time.monotonic()
        summary["time_budget_exhausted"] = False

        max_per = max(1, min(int(limit_per_query), 50))
        for idx, (target, city) in enumerate(pairs):
            if time.monotonic() - t_start > time_budget_s:
                summary["time_budget_exhausted"] = True
                logger.warning(
                    f"[prospector] time budget {time_budget_s:.0f}s exhausted after "
                    f"{summary['queries_run']} queries — partial return (no soft-limit kill)"
                )
                break
            niche = target.get("niche") or "general"
            query = target.get("query") or ""
            if not query:
                summary["queries_failed"] += 1
                continue

            # Cost-safety: Maps Details budget khatam → aur API queries skip
            # (OSM free hai, uspe cap nahi).
            if not use_osm and max_lookups and summary["lookups_used"] >= max_lookups:
                summary["lookups_capped"] = True
                continue

            # Fetch from chosen source -> normalize to list of dicts with
            # keys: name, phone, address, rating, website.
            rows: list[dict[str, Any]] = []
            try:
                if use_osm:
                    # Politeness: Overpass calls ke beech 1s sleep. await (NOT time.sleep)
                    # warna pura event-loop block hota — run_prospecting async hai.
                    if idx > 0:
                        await asyncio.sleep(1)
                    # `_osm_search` uses sync urllib; keep it off the async
                    # scheduler loop so prospecting cannot block other agents.
                    for r in await asyncio.to_thread(_osm_search, query, city, max_per):
                        rows.append(
                            {
                                "name": r.get("business_name", ""),
                                "phone": r.get("phone", ""),
                                "address": r.get("address", ""),
                                "rating": None,
                                "reviews_count": None,
                                "website": r.get("website", ""),
                                "email": str(r.get("email") or "").strip(),
                            }
                        )
                else:
                    biz_list = await scraper.search_businesses(
                        query=query,
                        location=city,
                        max_results=max_per,
                    )
                    for biz in biz_list or []:
                        # Place Details lookup hua hai (scraper internally karta).
                        # Cost-safety: budget khatam ho gaya to aur fetch na ho.
                        if max_lookups and summary["lookups_used"] >= max_lookups:
                            summary["lookups_capped"] = True
                            break
                        summary["lookups_used"] += 1
                        rc = getattr(biz, "reviews_count", None)
                        rows.append(
                            {
                                "name": str(getattr(biz, "name", "") or ""),
                                "phone": getattr(biz, "phone", None),
                                "address": str(getattr(biz, "address", "") or ""),
                                "rating": getattr(biz, "rating", None),
                                "reviews_count": rc if rc is not None else 0,
                                "website": str(getattr(biz, "website", "") or ""),
                                "source_url": str(getattr(biz, "google_maps_url", "") or ""),
                                "primary_type": str(getattr(biz, "primary_type", "") or ""),
                                "types": tuple(getattr(biz, "types", ()) or ()),
                                "business_status": str(getattr(biz, "business_status", "") or ""),
                                # Scraper already may carry an email (Places details
                                # path runs _extract_email_from_website internally).
                                "email": str(getattr(biz, "email", "") or "").strip(),
                            }
                        )
                    # A configured Maps key can still be denied, quota-limited,
                    # or return an empty result. Fall back to free OSM per query
                    # so a stale key cannot silently starve prospecting.
                    if not rows:
                        if idx > 0:
                            await asyncio.sleep(1)
                        osm_rows = await asyncio.to_thread(_osm_search, query, city, max_per)
                        if osm_rows:
                            summary["scraper"] = "google_maps_api+osm_fallback"
                            for r in osm_rows:
                                rows.append(
                                    {
                                        "name": r.get("business_name", ""),
                                        "phone": r.get("phone", ""),
                                        "address": r.get("address", ""),
                                        "rating": None,
                                        "reviews_count": None,
                                        "website": r.get("website", ""),
                                        "source_url": str(r.get("source_url") or ""),
                                        "primary_type": str(r.get("primary_type") or ""),
                                        "types": tuple(r.get("types") or ()),
                                        "business_status": str(r.get("business_status") or ""),
                                        "email": str(r.get("email") or "").strip(),
                                    }
                                )
                summary["queries_run"] += 1
                if not rows:
                    summary["queries_empty"] += 1
            except Exception as e:
                summary["queries_failed"] += 1
                logger.warning(f"[prospector] query '{query}' in {city} failed: {e}")
                continue

            for biz in rows:
                try:
                    name = str(biz.get("name") or "").strip()
                    if not name:
                        continue
                    phone10 = _phone_digits(biz.get("phone"))
                    biz_key = f"{name.lower()}|{city.strip().lower()}"
                    reject = _scraped_reject_reason(
                        name,
                        phone10,
                        str(biz.get("email") or "").strip(),
                        "google_maps" if not use_osm else "osm",
                        primary_type=str(biz.get("primary_type") or ""),
                        types=biz.get("types") or (),
                        business_status=str(biz.get("business_status") or ""),
                    )
                    if reject:
                        summary.setdefault("quality_rejected", 0)
                        summary["quality_rejected"] += 1
                        continue
                    # Dedupe: phone digits (agar ho) AUR name+city dono.
                    if (phone10 and phone10 in seen) or biz_key in seen:
                        summary["duplicates"] += 1
                        continue

                    rating = biz.get("rating")
                    reviews_count = biz.get("reviews_count")
                    website = str(biz.get("website") or "").strip()
                    has_website = bool(website)

                    # Email: row me ho to wahi; warna website se best-effort
                    # scrape (budget ke andar, async scraper helper ho to).
                    # Slow/missing par chup-chaap "" — kabhi crash nahi.
                    email = str(biz.get("email") or "").strip()
                    if (
                        not email
                        and website
                        and _email_fn is not None
                        and max_email_fetch
                        and email_fetches < max_email_fetch
                        # Budget khatam → naya slow network fetch mat kholo
                        # (already-fetched rows ka local processing chalta rahe).
                        and (time.monotonic() - t_start) <= time_budget_s
                    ):
                        email_fetches += 1
                        try:
                            found = await _email_fn(website)
                            email = str(found or "").strip()
                        except Exception as e:
                            logger.debug(f"[prospector] email extract failed for {website}: {e}")
                            email = ""
                    if email:
                        summary["emails_found"] += 1

                    # Real Google data ho (rating ya reviews) to personalized
                    # pitch; warna generic (OSM path me yeh None hote hain).
                    if rating is not None or reviews_count is not None:
                        pitch = build_personalized_pitch(
                            name,
                            niche,
                            city,
                            rating=rating,
                            reviews_count=reviews_count,
                            has_website=has_website,
                        )
                    else:
                        pitch = build_pitch(name, niche, city)
                    rec: dict[str, Any] = {
                        "id": str(uuid.uuid4()),
                        "found_at": datetime.utcnow().isoformat() + "Z",
                        "business_name": name[:200],
                        "phone": ("+91" + phone10) if phone10 else "",
                        "phone_type": _phone_type(phone10),  # ADR-027 quality tag
                        "address": str(biz.get("address") or "")[:300],
                        "city": city,
                        "niche": niche,
                        "rating": rating,
                        "reviews_count": reviews_count,
                        "website": website[:300],
                        "source_url": str(biz.get("source_url") or "")[:500],
                        "has_website": has_website,
                        "email": email[:200],
                        "source_query": query,
                        "pitch": pitch,
                        # Phone ho to WA link; warna manual Google lookup link.
                        "wa_link": _wa_link(phone10, pitch) if phone10 else "",
                        "google_search_link": "" if phone10 else _google_search_link(name, city),
                        "status": "ready",
                    }
                    if not phone10:
                        summary["no_phone"] += 1
                    if _append(rec):
                        if phone10:
                            seen.add(phone10)
                        seen.add(biz_key)
                        summary["new"] += 1
                        summary["by_niche"][niche] = summary["by_niche"].get(niche, 0) + 1
                except Exception as e:
                    logger.debug(f"[prospector] record build failed: {e}")

        # Team activity — Rohan (Leads Manager). Never raises.
        try:
            from app.platform.team import log_event

            log_event(
                "rohan",
                "prospects_found",
                f"{summary['new']} naye prospects ({summary['queries_run']} queries; "
                f"{summary['duplicates']} dup, {summary['no_phone']} bina-phone)",
                status="ok" if summary["queries_failed"] == 0 else "warn",
                meta={
                    k: summary.get(k)
                    for k in (
                        "new",
                        "duplicates",
                        "no_phone",
                        "queries_run",
                        "queries_failed",
                        "queries_empty",
                        "by_niche",
                        "scraper",
                        "lookups_used",
                        "lookups_capped",
                        "emails_found",
                    )
                },
            )
        except Exception:
            pass

        # Auto-rescore — naye leads hot-lead dashboard me aayein (niche_prospector jaisa).
        if summary.get("new", 0) > 0:
            try:
                from app.platform import lead_scoring

                await lead_scoring.rescore_db(limit=500)
            except Exception:
                pass

        # Cadence auto-enroll — default prospector path bhi niche_prospector jaisa (gated CADENCE_ENGINE).
        cadence_enrolled = 0
        try:
            import os as _os

            if (
                _os.environ.get("CADENCE_ENGINE", "").strip() in ("1", "true", "yes")
                and summary.get("new", 0) > 0
            ):
                from app.marketing import cadence as _cadence

                _total_new = int(summary.get("new") or 0)
                _all = _read_all()
                _fresh = [r for r in _all[-(_total_new + 30) :] if r.get("status") == "ready"][
                    :_total_new
                ]
                if _fresh:
                    cadence_enrolled = _cadence.enroll_many(_fresh)
                    logger.debug(f"[prospector] cadence enrolled {cadence_enrolled} leads")
        except Exception as _ce:
            logger.debug(f"[prospector] cadence enroll skip: {_ce}")
        summary["cadence_enrolled"] = cadence_enrolled

        logger.info(f"[prospector] run done: {summary}")
        return summary
    except Exception as e:  # absolute guard — scheduler/API kabhi na gire
        logger.warning(f"[prospector] run_prospecting failed: {e}")
        summary["ok"] = False
        summary["error"] = str(e)
        return summary


__all__ = [
    "run_prospecting",
    "list_prospects",
    "mark_prospect",
    "set_prospect_fields",
    "build_pitch",
    "build_personalized_pitch",
    "is_quality_approved",
    "VALID_STATUSES",
]
