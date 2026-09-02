"""
Lead Model
Database model for leads with comprehensive tracking
"""

import enum
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship, validates

from app.models.base import Base


def _enum_values(enum_cls):
    """values_callable for SQLAlchemy Enum columns so the DB stores the enum's
    .value (e.g. "qualified") not its .name (e.g. "QUALIFIED") — VARCHAR-backed,
    not a Postgres native-ENUM type (native_enum=False). Matches app/models/
    payment.py's pattern (production audit 2026-07-01, F-DB4: retrofitted after
    confirming via alembic/versions/010_enum_columns_to_varchar.py that existing
    columns already store .value post-migration, so this is consistent not a
    behavior change)."""
    return [member.value for member in enum_cls]


class LeadStatus(enum.Enum):
    """Lead status enum"""

    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    APPOINTMENT = "appointment"
    CALLBACK = "callback"
    NOT_INTERESTED = "not_interested"
    WRONG_NUMBER = "wrong_number"
    DND = "dnd"
    CONVERTED = "converted"
    LOST = "lost"


class LeadSource(enum.Enum):
    """Lead source enum"""

    GOOGLE_MAPS = "google_maps"
    INDIAMART = "indiamart"
    JUSTDIAL = "justdial"
    LINKEDIN = "linkedin"
    MANUAL = "manual"
    IMPORT = "import"
    WEBSITE = "website"
    REFERRAL = "referral"


class LeadStatusHistory(Base):
    """Audit trail of Lead.status transitions — who/what changed a lead and when.

    Forward-only (no backfill of pre-existing rows): populated by
    Lead._record_transition(), called from every status-mutating method below.
    """

    __tablename__ = "lead_status_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(String(36), ForeignKey("leads.id"), nullable=False, index=True)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    changed_by = Column(String(100), nullable=True)  # e.g. "system:mark_called", agent name
    changed_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<LeadStatusHistory {self.lead_id}: {self.old_status}->{self.new_status}>"


class Lead(Base):
    """Lead database model"""

    __tablename__ = "leads"

    # Add table indexes for common queries
    __table_args__ = (
        Index("ix_leads_status_score", "status", "lead_score"),
        Index("ix_leads_city_niche", "city", "niche"),
        Index("ix_leads_next_call", "next_call_at", "status"),
        Index("ix_leads_campaign_status", "campaign_id", "status"),
    )

    id = Column(String(36), primary_key=True)

    # Company information
    company_name = Column(String(255), nullable=False, index=True)
    website = Column(String(500))
    industry = Column(String(100))
    employee_count = Column(String(50))

    # Contact information
    contact_name = Column(String(255))
    # Uniqueness NOT declared here (unique=True would apply on every fresh
    # create_all()-based test DB, and many tests share a placeholder phone
    # across unrelated Lead rows in the same DB). DB-level enforcement lives
    # in alembic/versions/009_leads_phone_unique_if_clean.py instead — applies
    # only in migration-managed envs (staging/prod), and only once existing
    # data has no duplicates. App-level dedup-by-phone (the actual guarantee
    # today) is in app/api/public_site.py, app/platform/prospector.py, and
    # app/tasks/sync.py.
    phone = Column(String(20), nullable=False, index=True)
    email = Column(String(255))
    designation = Column(String(100))

    # Location
    address = Column(Text)
    city = Column(String(100), index=True)
    state = Column(String(100))
    country = Column(String(100), default="India")
    pincode = Column(String(10))

    # Categorization
    category = Column(String(100), index=True)
    niche = Column(String(50), index=True)
    tags = Column(Text)  # JSON array

    # Lead scoring
    lead_score = Column(Integer, default=0, index=True)
    is_hot_lead = Column(Boolean, default=False, index=True)

    # Qualification data (JSON)
    qualification_data = Column(Text)

    # Pipeline batch provenance (2026-07-08) — WHY this score, persisted not
    # just computed on demand; which prospector.py batch produced this lead.
    score_reason = Column(Text)
    source_batch_id = Column(
        String(36), ForeignKey("lead_pipeline_batches.id"), nullable=True, index=True
    )

    # Status tracking
    status = Column(
        Enum(LeadStatus, native_enum=False, values_callable=_enum_values),
        default=LeadStatus.NEW,
        index=True,
    )
    source = Column(
        Enum(LeadSource, native_enum=False, values_callable=_enum_values),
        default=LeadSource.MANUAL,
    )

    # Verification
    verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)

    # Assignment
    assigned_to = Column(String(36), ForeignKey("clients.id"))
    campaign_id = Column(String(36), ForeignKey("campaigns.id"))

    # Call tracking
    call_attempts = Column(Integer, default=0)
    last_called_at = Column(DateTime)
    next_call_at = Column(DateTime)
    preferred_call_time = Column(String(50))

    # Notes
    notes = Column(Text)

    # Appointment details
    appointment_date = Column(DateTime)
    appointment_notes = Column(Text)

    # CRM sync
    hubspot_id = Column(String(100))
    zoho_id = Column(String(100))
    sheets_row = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    call_logs = relationship("CallLog", back_populates="lead")
    campaign = relationship("Campaign", back_populates="leads")

    def __repr__(self) -> str:
        return f"<Lead {self.company_name} ({self.phone})>"

    @validates("phone")
    def validate_phone(self, key: str, phone: str) -> str:
        """Validate phone number format"""
        if phone:
            # Remove spaces and common separators
            cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            # Basic validation - should have at least 10 digits
            digits = "".join(c for c in cleaned if c.isdigit())
            if len(digits) < 10:
                raise ValueError("Phone number must have at least 10 digits")
        return phone

    @validates("email")
    def validate_email(self, key: str, email: str | None) -> str | None:
        """Basic email validation"""
        if email and "@" not in email:
            raise ValueError("Invalid email format")
        return email.lower() if email else None

    @validates("lead_score")
    def validate_score(self, key: str, score: int) -> int:
        """Ensure score is within valid range"""
        if score < 0:
            return 0
        if score > 100:
            return 100
        return score

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "company_name": self.company_name,
            "contact_name": self.contact_name,
            "phone": self.phone,
            "email": self.email,
            "website": self.website,
            "city": self.city,
            "state": self.state,
            "category": self.category,
            "niche": self.niche,
            "lead_score": self.lead_score,
            "is_hot_lead": self.is_hot_lead,
            "status": self.status.value if self.status else None,
            "source": self.source.value if self.source else None,
            "verified": self.verified,
            "call_attempts": self.call_attempts,
            "last_called_at": self.last_called_at.isoformat() if self.last_called_at else None,
            "next_call_at": self.next_call_at.isoformat() if self.next_call_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_tags(self) -> list[str]:
        """Get tags as a list"""
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except json.JSONDecodeError:
            return []

    def set_tags(self, tags: list[str]) -> None:
        """Set tags from a list"""
        self.tags = json.dumps(tags) if tags else None
        self.updated_at = datetime.utcnow()

    def add_tag(self, tag: str) -> None:
        """Add a single tag"""
        tags = self.get_tags()
        if tag not in tags:
            tags.append(tag)
            self.set_tags(tags)

    def remove_tag(self, tag: str) -> None:
        """Remove a single tag"""
        tags = self.get_tags()
        if tag in tags:
            tags.remove(tag)
            self.set_tags(tags)

    def get_qualification_data(self) -> dict[str, Any]:
        """Get qualification data as dict"""
        if not self.qualification_data:
            return {}
        try:
            return json.loads(self.qualification_data)
        except json.JSONDecodeError:
            return {}

    def set_qualification_data(self, data: dict[str, Any]) -> None:
        """Set qualification data"""
        self.qualification_data = json.dumps(data) if data else None
        self.updated_at = datetime.utcnow()

    def update_qualification(self, key: str, value: Any) -> None:
        """Update a single qualification field"""
        data = self.get_qualification_data()
        data[key] = value
        self.set_qualification_data(data)

    def update_score(self, new_score: int, reason: str | None = None) -> None:
        """Update lead score and hot lead flag. `reason` (optional, e.g. from
        lead_scoring.score_components()) is persisted so admin/reporting can
        see WHY a lead is hot, not just the number. Threshold centralized in
        settings.lead_hot_threshold (2026-07-08 — previously hardcoded 70 here
        while lead_scoring.py's own env default was 60; both now read the
        same setting, see docs/superpowers/specs/2026-07-08-lead-gen-pipeline-automation-design.md).
        """
        from app.config import settings

        self.lead_score = max(0, min(100, new_score))  # Clamp between 0-100
        self.is_hot_lead = self.lead_score >= settings.lead_hot_threshold
        if reason is not None:
            self.score_reason = reason[:2000]
        self.updated_at = datetime.utcnow()

    def calculate_score(self) -> int:
        """
        Calculate lead score based on various factors
        Returns score between 0-100
        """
        score = 0

        # Verification bonus
        if self.verified:
            score += 10
        if self.phone_verified:
            score += 10
        if self.email_verified:
            score += 5

        # Contact info completeness
        if self.contact_name:
            score += 10
        if self.email:
            score += 10
        if self.designation:
            score += 5
        if self.website:
            score += 5

        # Qualification data
        qual_data = self.get_qualification_data()
        if qual_data.get("is_decision_maker"):
            score += 15
        if qual_data.get("budget_range"):
            score += 10
        if qual_data.get("timeline"):
            score += 5
        if qual_data.get("interest_level") == "high":
            score += 15
        elif qual_data.get("interest_level") == "medium":
            score += 5

        return min(100, score)

    def _record_transition(self, old_status: "LeadStatus | None", changed_by: str) -> None:
        """Best-effort audit row for a status change. Never raises — a session-less
        or detached Lead (e.g. in a unit test) just skips the write."""
        try:
            from sqlalchemy.orm import object_session

            sess = object_session(self)
            if sess is None:
                return
            old_val = getattr(old_status, "value", old_status)
            new_val = getattr(self.status, "value", self.status)
            if old_val == new_val:
                return
            sess.add(
                LeadStatusHistory(
                    lead_id=self.id,
                    old_status=old_val,
                    new_status=new_val,
                    changed_by=changed_by,
                )
            )
        except Exception:
            pass

    def mark_called(self) -> None:
        """Mark lead as called"""
        old_status = self.status
        self.call_attempts += 1
        self.last_called_at = datetime.utcnow()
        if self.status == LeadStatus.NEW:
            self.status = LeadStatus.CONTACTED
        self.updated_at = datetime.utcnow()
        self._record_transition(old_status, "system:mark_called")

    def mark_contacted(self, changed_by: str = "outreach") -> None:
        """Promote NEW -> CONTACTED when we make an outbound touch (email/cadence/
        WhatsApp/SMS) - the non-call sibling of mark_called().

        Unlike mark_called() this does NOT touch call_attempts / last_called_at:
        an email outreach is not a phone call. Forward-only and never downgrades -
        if the lead is already past NEW (CONTACTED, QUALIFIED, NOT_INTERESTED, ...)
        it is left untouched and NO history row is written. Reuses
        _record_transition() so lead_status_history stays the single audit
        mechanism (no parallel writer)."""
        if self.status != LeadStatus.NEW:
            return
        old_status = self.status
        self.status = LeadStatus.CONTACTED
        self.updated_at = datetime.utcnow()
        self._record_transition(old_status, changed_by)

    def schedule_callback(self, callback_time: datetime, notes: str | None = None) -> None:
        """Schedule a callback for this lead"""
        old_status = self.status
        self.status = LeadStatus.CALLBACK
        self.next_call_at = callback_time
        if notes:
            self.notes = f"{self.notes or ''}\n[Callback scheduled: {callback_time.isoformat()}] {notes}".strip()
        self.updated_at = datetime.utcnow()
        self._record_transition(old_status, "system:schedule_callback")

    def schedule_appointment(self, appointment_time: datetime, notes: str | None = None) -> None:
        """Schedule an appointment for this lead"""
        old_status = self.status
        self.status = LeadStatus.APPOINTMENT
        self.appointment_date = appointment_time
        if notes:
            self.appointment_notes = notes
        self.is_hot_lead = True
        self.update_score(max(self.lead_score, 80))
        self.updated_at = datetime.utcnow()
        self._record_transition(old_status, "system:schedule_appointment")

    def mark_not_interested(self, reason: str | None = None) -> None:
        """Mark lead as not interested"""
        old_status = self.status
        self.status = LeadStatus.NOT_INTERESTED
        if reason:
            self.notes = f"{self.notes or ''}\n[Not interested: {datetime.utcnow().isoformat()}] {reason}".strip()
        self.updated_at = datetime.utcnow()
        self._record_transition(old_status, "system:mark_not_interested")

    def mark_dnd(self) -> None:
        """Mark lead as Do Not Disturb"""
        old_status = self.status
        self.status = LeadStatus.DND
        self.add_tag("dnd")
        self.updated_at = datetime.utcnow()
        self._record_transition(old_status, "system:mark_dnd")

    def can_be_called(self) -> bool:
        """Check if lead can be called"""
        # Cannot call if DND or wrong number
        if self.status in [LeadStatus.DND, LeadStatus.WRONG_NUMBER]:
            return False

        # Cannot call if already converted or lost
        if self.status in [LeadStatus.CONVERTED, LeadStatus.LOST]:
            return False

        # Cannot call if not interested (unless explicitly re-activated)
        if self.status == LeadStatus.NOT_INTERESTED:
            return False
        return True


def phone_format_variants(phone: str) -> list[str]:
    """All plausible raw storage formats for the SAME Indian number.

    Root cause (2026-07-04 dialer-sprint audit): three separate ingestion paths
    (scraping.py, sync.py, prospector.py) each dedupe with an EXACT-STRING
    ``Lead.phone == candidate`` check. Every path normalizes its OWN candidate
    before comparing, but none accounts for the DB already holding the SAME
    number in a DIFFERENT raw format from another path (prospector.py stores
    digits-only "919967993679", the CRM/sheet import path stores "+919967993679")
    — so the exact-match silently misses it and the same business gets
    inserted twice. Returns every format variant worth matching against;
    callers do ``Lead.phone.in_(phone_format_variants(candidate))``.
    Never raises — unparseable input just yields an empty list (no match).
    """
    import re

    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) < 10:
        return []
    suffix = digits[-10:]
    return [suffix, "91" + suffix, "+91" + suffix, "0" + suffix]


def lead_exists_for_phone(db, phone: str) -> bool:
    """True if a Lead with this phone (any known raw-format variant) already
    exists. Sync-session helper — use directly with ``db.query(...)`` sessions
    (scraping.py/sync.py/prospector.py all use the sync ``get_db_session``).
    Never raises; unparseable phone -> False (caller's own len-check already
    guards this in practice, kept defensive here too)."""
    variants = phone_format_variants(phone)
    if not variants:
        return False
    try:
        return db.query(Lead.id).filter(Lead.phone.in_(variants)).first() is not None
    except Exception:
        return False
