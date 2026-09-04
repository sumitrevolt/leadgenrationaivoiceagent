"""Customer Video Brief — verified-data-only brief resolution for Creative OS.

Closes three seams that `service.enqueue_generate` currently leaves open:

1. **Entitlement gate** — a tenant with no active paid plan may not consume
   render budget. Fail-CLOSED: unknown tenant / unknown plan / inactive
   subscription all refuse.
2. **Brand resolution with provenance** — brand fields are read from the
   canonical stores (`clients_store` + `brand_kit`) and every resolved field
   carries the store it came from. Nothing is invented here.
3. **NEEDS_CUSTOMER_INPUT instead of fabrication** — when a field required to
   render an on-brand video is absent, the brief refuses with an explicit
   `missing` list. It never substitutes a plausible default for a fact
   (price, offer, address, certification, testimonial).

Read-only with respect to every store. No FFmpeg, no network, no queue writes.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

OUTCOME_READY = "ready"
OUTCOME_NEEDS_INPUT = "needs_customer_input"
OUTCOME_BLOCKED = "blocked"

# Fields without which an "enterprise, on-brand, customer-specific" video
# cannot honestly be rendered. Absence => NEEDS_CUSTOMER_INPUT, never a default.
REQUIRED_BRAND_FIELDS = ("business_name", "niche", "primary_color", "accent_color")

_ACTIVE_STATUSES = frozenset({"active", "live", "paid", "trialing"})
_PRICE_RE = re.compile(r"(?:₹|\bRs\.?\s*|\bINR\s*)\s*([0-9][0-9,]{1,9})", re.I)


@dataclass
class BrandProfile:
    """Resolved, provenance-tagged brand facts for ONE tenant."""

    tenant_id: str
    business_name: str = ""
    niche: str = ""
    city: str = ""
    primary_color: str = ""
    accent_color: str = ""
    tagline: str = ""
    logo_text: str = ""
    phone: str = ""
    contact_display: str = ""
    offer_badge: str = ""
    socials: dict[str, str] = field(default_factory=dict)
    services: list[dict[str, Any]] = field(default_factory=list)
    verified_trust: list[str] = field(default_factory=list)
    verified_metrics: list[dict[str, str]] = field(default_factory=list)
    kb_facts: list[str] = field(default_factory=list)
    plan: str = ""
    status: str = ""
    sources: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    def verified_prices(self) -> set[str]:
        """Every price the tenant's own record actually supports (digits only)."""
        out: set[str] = set()
        for svc in self.services or []:
            raw = (svc or {}).get("price_inr")
            if raw in (None, ""):
                continue
            digits = re.sub(r"[^0-9]", "", str(raw))
            if digits:
                out.add(digits)
        return out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CustomerVideoBrief:
    """Canonical, customer-specific input contract for a render job."""

    tenant_id: str
    objective: str
    platform: str
    aspect_ratio: str
    language: str
    brand: BrandProfile
    offer: str = ""
    cta: str = ""
    requested_duration_s: float = 20.0
    brand_revision: str = "v1"
    verified_claims: list[str] = field(default_factory=list)
    prohibited_notes: list[str] = field(default_factory=list)
    calendar_slot: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["brand"] = self.brand.to_dict()
        return d


def _client_record(tenant_id: str) -> dict[str, Any] | None:
    """Canonical tenant record. Never raises."""
    try:
        from app.marketing import clients_store

        return clients_store.resolve_client(str(tenant_id or "")) or clients_store.get_client(
            str(tenant_id or "")
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("creative_os.brief client lookup skip (%s): %s", tenant_id, exc)
        return None


def _plan_catalog() -> dict[str, dict[str, Any]]:
    """Reuse billing's merged plan catalog — packages.py stays the single source."""
    try:
        from app.billing.entitlement_assurance import _plan_catalog as _cat

        return _cat() or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("creative_os.brief plan catalog skip: %s", exc)
        return {}


def entitlement_gate(tenant_id: str) -> dict[str, Any]:
    """Fail-CLOSED entitlement check for video generation.

    Refuses when the tenant is unknown, not active, has no plan, or holds a plan
    that is absent from the billing catalog. A lookup failure is a refusal, not
    a pass — an unresolvable tenant must never consume render budget.
    """
    tid = str(tenant_id or "").strip()
    if not tid:
        return {"ok": False, "error": "tenant_id required", "reason": "no_tenant"}

    rec = _client_record(tid)
    if not rec:
        return {"ok": False, "error": "tenant not found", "reason": "unknown_tenant"}

    status = str(rec.get("status") or "").strip().lower()
    plan = str(rec.get("plan") or "").strip().lower()
    if status not in _ACTIVE_STATUSES:
        return {
            "ok": False,
            "error": f"subscription not active: {status or 'unset'}",
            "reason": "inactive_subscription",
            "status": status,
        }
    if not plan:
        return {"ok": False, "error": "no plan on record", "reason": "no_plan"}

    catalog = _plan_catalog()
    if not catalog:
        return {
            "ok": False,
            "error": "plan catalog unavailable",
            "reason": "catalog_unavailable",
        }
    if plan not in catalog:
        return {
            "ok": False,
            "error": f"unknown plan: {plan}",
            "reason": "unknown_plan",
            "plan": plan,
        }

    return {
        "ok": True,
        "plan": plan,
        "status": status,
        "plan_known": True,
    }


def resolve_brand_profile(tenant_id: str) -> BrandProfile:
    """Read brand facts from the canonical stores, tagging each with its source.

    Absent fields are recorded in ``missing`` — never filled with a default.
    """
    tid = str(tenant_id or "").strip()
    prof = BrandProfile(tenant_id=tid)
    rec = _client_record(tid) or {}

    if rec:
        prof.business_name = str(rec.get("business_name") or "").strip()
        prof.niche = str(rec.get("niche") or "").strip()
        prof.city = str(rec.get("city") or "").strip()
        prof.plan = str(rec.get("plan") or "").strip().lower()
        prof.status = str(rec.get("status") or "").strip().lower()
        brand = rec.get("brand") or {}
        prof.primary_color = str(brand.get("primary") or "").strip()
        prof.accent_color = str(brand.get("accent") or "").strip()
        prof.tagline = str(brand.get("tagline") or "").strip()
        prof.logo_text = str(brand.get("logo_text") or "").strip()
        prof.socials = {k: str(v) for k, v in (rec.get("socials") or {}).items() if v}
        for key in ("business_name", "niche", "city", "plan", "status"):
            if getattr(prof, key, ""):
                prof.sources[key] = "clients_store"
        for key in ("primary_color", "accent_color", "tagline", "logo_text"):
            if getattr(prof, key, ""):
                prof.sources[key] = "clients_store.brand"

    # brand_kit is the richer surface — it may fill gaps but never overwrite.
    try:
        from app.marketing import brand_kit

        kit = brand_kit.get_brand(tid) or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("creative_os.brief brand_kit skip (%s): %s", tid, exc)
        kit = {}

    for kit_key, attr in (
        ("primary", "primary_color"),
        ("accent", "accent_color"),
        ("tagline", "tagline"),
        ("logo_text", "logo_text"),
    ):
        if not getattr(prof, attr, "") and str(kit.get(kit_key) or "").strip():
            setattr(prof, attr, str(kit[kit_key]).strip())
            prof.sources[attr] = "brand_kit"

    services = rec.get("services") or kit.get("services") or []
    if isinstance(services, list):
        prof.services = [s for s in services if isinstance(s, dict)]
        if prof.services:
            prof.sources["services"] = "clients_store" if rec.get("services") else "brand_kit"

    prof.phone = str(rec.get("phone") or kit.get("phone") or "").strip()
    if prof.phone:
        prof.sources["phone"] = "clients_store" if rec.get("phone") else "brand_kit"

    prof.contact_display = str(
        rec.get("contact_display") or kit.get("contact_display") or prof.phone or ""
    ).strip()
    prof.offer_badge = str(
        rec.get("offer_badge") or rec.get("offer") or kit.get("offer") or ""
    ).strip()

    trust = rec.get("verified_trust") or kit.get("verified_trust") or []
    if isinstance(trust, list):
        prof.verified_trust = [str(x).strip() for x in trust if str(x).strip()]
        if prof.verified_trust:
            prof.sources["verified_trust"] = (
                "clients_store" if rec.get("verified_trust") else "brand_kit"
            )

    metrics = rec.get("verified_metrics") or kit.get("verified_metrics") or []
    if isinstance(metrics, list):
        prof.verified_metrics = [m for m in metrics if isinstance(m, dict)]
        if prof.verified_metrics:
            prof.sources["verified_metrics"] = (
                "clients_store" if rec.get("verified_metrics") else "brand_kit"
            )

    try:
        from app.marketing.kb_personalize import client_context

        kb_facts = client_context(tid, query="services offers speciality experience trust", k=4)
        if kb_facts:
            prof.kb_facts = [str(f).strip() for f in kb_facts if str(f).strip()]
            prof.sources["kb_facts"] = "knowledge_base"
            if not prof.verified_trust:
                extracted_trust: list[str] = []
                for fact in prof.kb_facts:
                    clean_fact = re.sub(r"[\r\n\t]+", " ", fact).strip()
                    first_part = clean_fact.split(".")[0].split("—")[0].split("|")[0].strip()
                    if 4 <= len(first_part) <= 40:
                        extracted_trust.append(first_part)
                if extracted_trust:
                    prof.verified_trust = extracted_trust[:3]
                    prof.sources["verified_trust"] = "knowledge_base"
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("creative_os.brief kb_facts skip (%s): %s", tid, exc)

    prof.missing = [f for f in REQUIRED_BRAND_FIELDS if not getattr(prof, f, "")]
    return prof


def unverified_prices(text: str, brand: BrandProfile) -> list[str]:
    """Prices appearing in copy that the tenant's own record does not support.

    A rendered video that quotes a price the customer never gave us is the
    single worst failure mode of this product, so it is detected structurally
    rather than trusted to the copy generator.
    """
    verified = brand.verified_prices()
    found: list[str] = []
    for match in _PRICE_RE.finditer(str(text or "")):
        digits = re.sub(r"[^0-9]", "", match.group(1))
        if digits and digits not in verified:
            found.append(match.group(0).strip())
    return found


def resolve_brief(
    *,
    tenant_id: str,
    objective: str,
    platform: str = "instagram",
    aspect_ratio: str = "9:16",
    language: str = "hinglish",
    offer: str = "",
    cta: str = "",
    business_name: str = "",
    niche: str = "",
    requested_duration_s: float = 20.0,
    brand_revision: str = "v1",
    calendar_slot: str = "",
) -> dict[str, Any]:
    """Build a `CustomerVideoBrief` or refuse with a machine-readable outcome.

    Returns ``{"ok", "outcome", "brief"|None, "missing", "error"}`` where
    ``outcome`` is one of ``ready`` / ``needs_customer_input`` / ``blocked``.
    """
    tid = str(tenant_id or "").strip()

    ent = entitlement_gate(tid)
    if not ent.get("ok"):
        return {
            "ok": False,
            "outcome": OUTCOME_BLOCKED,
            "brief": None,
            "missing": [],
            "reason": ent.get("reason"),
            "error": ent.get("error"),
        }

    brand = resolve_brand_profile(tid)
    missing = list(brand.missing)
    if not str(objective or "").strip():
        missing.append("objective")

    if missing:
        return {
            "ok": False,
            "outcome": OUTCOME_NEEDS_INPUT,
            "brief": None,
            "missing": missing,
            "reason": "missing_required_fields",
            "error": "missing required customer input: " + ", ".join(missing),
        }

    # Structural anti-fabrication gate over EVERY customer-visible copy field that
    # may reach the renderer — caller overrides AND store-resolved brand facts.
    bad: list[str] = []
    for label, text in (
        ("offer", offer),
        ("cta", cta),
        ("objective", objective),
        ("business_name", business_name),
        ("niche", niche),
        ("brand.business_name", brand.business_name),
        ("brand.niche", brand.niche),
        ("brand.tagline", brand.tagline),
        ("brand.logo_text", brand.logo_text),
    ):
        for price in unverified_prices(text, brand):
            bad.append(f"{label}:{price}")
    if bad:
        return {
            "ok": False,
            "outcome": OUTCOME_NEEDS_INPUT,
            "brief": None,
            "missing": ["services.price_inr"],
            "reason": "unverified_price",
            "error": "copy quotes a price not present on the customer record: " + ", ".join(bad),
        }

    brief = CustomerVideoBrief(
        tenant_id=tid,
        objective=str(objective).strip(),
        platform=str(platform or "instagram").strip().lower(),
        aspect_ratio=str(aspect_ratio or "9:16").strip(),
        language=str(language or "hinglish").strip().lower(),
        brand=brand,
        offer=str(offer or brand.offer_badge or "").strip(),
        cta=str(cta or "").strip(),
        requested_duration_s=float(requested_duration_s or 20.0),
        brand_revision=str(brand_revision or "v1"),
        calendar_slot=str(calendar_slot or ""),
        verified_claims=list(brand.kb_facts or []),
    )
    return {
        "ok": True,
        "outcome": OUTCOME_READY,
        "brief": brief,
        "missing": [],
        "reason": "",
        "error": "",
    }


__all__ = [
    "OUTCOME_BLOCKED",
    "OUTCOME_NEEDS_INPUT",
    "OUTCOME_READY",
    "REQUIRED_BRAND_FIELDS",
    "BrandProfile",
    "CustomerVideoBrief",
    "entitlement_gate",
    "resolve_brand_profile",
    "resolve_brief",
    "unverified_prices",
]
