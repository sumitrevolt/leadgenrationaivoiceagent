"""Marketing request models — Pydantic schemas for app/api/marketing.py endpoints.

Extracted from app/api/marketing.py (2026-06-20 refactor) to separate data from routes.
Re-imported by marketing.py so endpoint refs and external imports keep working.
"""

from pydantic import BaseModel, Field


class PostRequest(BaseModel):
    """Social post generation request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=80)
    offer: str = Field("", max_length=200)
    language: str = Field("hinglish", max_length=30)


class CalendarRequest(BaseModel):
    """Content calendar request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    days: int = Field(7, ge=1, le=30)


class AuditScoreRequest(BaseModel):
    """GBP audit answers: {question_id: option_index}."""

    answers: dict[str, int] = Field(default_factory=dict)


class ReviewReplyRequest(BaseModel):
    """Review reply generation request."""

    review_text: str = Field(..., min_length=1, max_length=2000)
    rating: float | None = Field(None, ge=0, le=5)
    business_name: str = Field("", max_length=120)
    tone: str = Field("professional", max_length=40)


class FestivalPostsRequest(BaseModel):
    """Festival posts request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    days: int = Field(45, ge=1, le=730)


class PosterRequest(BaseModel):
    """SVG poster generation request (brand colors optional — brand_kit se)."""

    template_id: str = Field(..., min_length=1, max_length=60)
    business_name: str = Field(..., min_length=1, max_length=120)
    tagline: str = Field("", max_length=160)
    offer: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    festival: str = Field("", max_length=80)
    client_id: str = Field("", max_length=64)  # set => saved brand auto-apply
    brand_primary: str = Field("", max_length=10)  # #RRGGBB
    brand_accent: str = Field("", max_length=10)  # #RRGGBB


class WhatsAppPackRequest(BaseModel):
    """WhatsApp broadcast pack request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    occasion: str = Field("", max_length=80)
    offer: str = Field("", max_length=200)


class CompetitorRequest(BaseModel):
    """Competitor comparison request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    competitor_notes: str = Field(..., min_length=1, max_length=4000)


class ReviewKitRequest(BaseModel):
    """Review-collection kit request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    place_query: str = Field("", max_length=200)


class ReactivationCustomer(BaseModel):
    """Ek purana customer (win-back ke liye)."""

    name: str = Field("", max_length=80)
    phone: str = Field("", max_length=20)
    last_visit: str = Field("", max_length=40)
    note: str = Field("", max_length=200)


class ReactivationRequest(BaseModel):
    """Database-reactivation campaign request (cap 50 customers)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    offer: str = Field("", max_length=200)
    customers: list[ReactivationCustomer] = Field(default_factory=list, max_length=50)


class DripRequest(BaseModel):
    """WhatsApp nurture sequence request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    lead_type: str = Field("new_inquiry", max_length=30)


class UPIQRRequest(BaseModel):
    """UPI QR Code poster request."""

    vpa: str = Field(..., min_length=3, max_length=120)
    business_name: str = Field(..., min_length=1, max_length=120)
    amount: float = Field(0.0, ge=0.0, le=100000.0)
    brand_primary: str = Field("", max_length=10)
    brand_accent: str = Field("", max_length=10)


class MissedCallRequest(BaseModel):
    """Missed call auto-reply request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    callback_url: str = Field("", max_length=200)


class BrandColors(BaseModel):
    """Brand colors (#RRGGBB; invalid => ignore)."""

    primary: str = Field("", max_length=10)
    accent: str = Field("", max_length=10)


class BrandRequest(BaseModel):
    """Per-client brand profile."""

    business_name: str = Field("", max_length=120)
    tagline: str = Field("", max_length=160)
    phone: str = Field("", max_length=40)
    colors: BrandColors = Field(default_factory=BrandColors)
    tone: str = Field("", max_length=40)
    logo_text: str = Field("", max_length=40)


class CrmCustomer(BaseModel):
    """CRM-lite customer row."""

    name: str = Field("", max_length=80)
    phone: str = Field(..., min_length=5, max_length=20)
    birthday: str = Field("", max_length=20)  # YYYY-MM-DD ya MM-DD
    anniversary: str = Field("", max_length=20)  # YYYY-MM-DD ya MM-DD
    tags: list[str] = Field(default_factory=list, max_length=10)


class CrmCustomersRequest(BaseModel):
    """CRM customers add request."""

    customers: list[CrmCustomer] = Field(default_factory=list, max_length=500)


class UpiKitRequest(BaseModel):
    """UPI payment kit request (vpa = naam@bank)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    vpa: str = Field(..., min_length=3, max_length=100)
    amount: float | None = Field(None, ge=0, le=10_000_000)
    note: str = Field("", max_length=100)


class CatalogItem(BaseModel):
    """Catalog ka ek item (price string flexible: '249' / '₹249')."""

    name: str = Field(..., min_length=1, max_length=80)
    price: str = Field("", max_length=20)
    desc: str = Field("", max_length=160)


class CatalogRequest(BaseModel):
    """Price-list catalog request (12 se zyada items trim ho jaate hain)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    items: list[CatalogItem] = Field(default_factory=list, max_length=24)
    style: str = Field("price_list", max_length=30)


class AdsPackRequest(BaseModel):
    """Google RSA + Meta ads copy request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    offer: str = Field("", max_length=200)
    city: str = Field("", max_length=80)


class ReelsRequest(BaseModel):
    """Reels scripts request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    topic: str = Field("", max_length=120)
    n: int = Field(3, ge=1, le=6)


class GbpTextsRequest(BaseModel):
    """GBP description + services + posts request."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    services: list[str] = Field(default_factory=list, max_length=12)


class ContentPackRequest(BaseModel):
    """Monthly client content pack request (client_id => saved brand auto-apply)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    client_id: str = Field("", max_length=64)
    offer: str = Field("", max_length=200)
    phone: str = Field("", max_length=40)


class BlogRunRequest(BaseModel):
    """Programmatic SEO blog — kitne naye articles publish karne hain."""

    n: int = Field(3, ge=1, le=25)


class ReferralRequest(BaseModel):
    """Refer & Earn kit request (brand colors optional — card gradient)."""

    business_name: str = Field(..., min_length=1, max_length=120)
    reward: str = Field("10% off", max_length=80)
    referrer_name: str = Field("", max_length=80)
    brand_primary: str = Field("", max_length=10)  # #RRGGBB
    brand_accent: str = Field("", max_length=10)  # #RRGGBB


class EvergreenRequest(BaseModel):
    """Evergreen recycle request (client_id path se aata hai)."""

    business_name: str = Field("", max_length=120)
    niche: str = Field("", max_length=80)
