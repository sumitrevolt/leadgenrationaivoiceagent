"""
Lead Model
Database model for leads with comprehensive tracking
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
import json
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, ForeignKey, Enum, Index
from sqlalchemy.orm import relationship, validates
import enum

from app.models.base import Base


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


class Lead(Base):
    """Lead database model"""
    __tablename__ = "leads"
    
    # Add table indexes for common queries
    __table_args__ = (
        Index('ix_leads_status_score', 'status', 'lead_score'),
        Index('ix_leads_city_niche', 'city', 'niche'),
        Index('ix_leads_next_call', 'next_call_at', 'status'),
        Index('ix_leads_campaign_status', 'campaign_id', 'status'),
    )
    
    id = Column(String(36), primary_key=True)
    
    # Company information
    company_name = Column(String(255), nullable=False, index=True)
    website = Column(String(500))
    industry = Column(String(100))
    employee_count = Column(String(50))
    
    # Contact information
    contact_name = Column(String(255))
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
    
    # Status tracking
    status = Column(Enum(LeadStatus), default=LeadStatus.NEW, index=True)
    source = Column(Enum(LeadSource), default=LeadSource.MANUAL)
    
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
    
    @validates('phone')
    def validate_phone(self, key: str, phone: str) -> str:
        """Validate phone number format"""
        if phone:
            # Remove spaces and common separators
            cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            # Basic validation - should have at least 10 digits
            digits = ''.join(c for c in cleaned if c.isdigit())
            if len(digits) < 10:
                raise ValueError("Phone number must have at least 10 digits")
        return phone
    
    @validates('email')
    def validate_email(self, key: str, email: Optional[str]) -> Optional[str]:
        """Basic email validation"""
        if email and '@' not in email:
            raise ValueError("Invalid email format")
        return email.lower() if email else None
    
    @validates('lead_score')
    def validate_score(self, key: str, score: int) -> int:
        """Ensure score is within valid range"""
        if score < 0:
            return 0
        if score > 100:
            return 100
        return score
    
    def to_dict(self) -> Dict[str, Any]:
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
    
    def get_tags(self) -> List[str]:
        """Get tags as a list"""
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except json.JSONDecodeError:
            return []
    
    def set_tags(self, tags: List[str]) -> None:
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
    
    def get_qualification_data(self) -> Dict[str, Any]:
        """Get qualification data as dict"""
        if not self.qualification_data:
            return {}
        try:
            return json.loads(self.qualification_data)
        except json.JSONDecodeError:
            return {}
    
    def set_qualification_data(self, data: Dict[str, Any]) -> None:
        """Set qualification data"""
        self.qualification_data = json.dumps(data) if data else None
        self.updated_at = datetime.utcnow()
    
    def update_qualification(self, key: str, value: Any) -> None:
        """Update a single qualification field"""
        data = self.get_qualification_data()
        data[key] = value
        self.set_qualification_data(data)
    
    def update_score(self, new_score: int) -> None:
        """Update lead score and hot lead flag"""
        self.lead_score = max(0, min(100, new_score))  # Clamp between 0-100
        self.is_hot_lead = self.lead_score >= 70
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
    
    def mark_called(self) -> None:
        """Mark lead as called"""
        self.call_attempts += 1
        self.last_called_at = datetime.utcnow()
        if self.status == LeadStatus.NEW:
            self.status = LeadStatus.CONTACTED
        self.updated_at = datetime.utcnow()
    
    def schedule_callback(self, callback_time: datetime, notes: Optional[str] = None) -> None:
        """Schedule a callback for this lead"""
        self.status = LeadStatus.CALLBACK
        self.next_call_at = callback_time
        if notes:
            self.notes = f"{self.notes or ''}\n[Callback scheduled: {callback_time.isoformat()}] {notes}".strip()
        self.updated_at = datetime.utcnow()
    
    def schedule_appointment(self, appointment_time: datetime, notes: Optional[str] = None) -> None:
        """Schedule an appointment for this lead"""
        self.status = LeadStatus.APPOINTMENT
        self.appointment_date = appointment_time
        if notes:
            self.appointment_notes = notes
        self.is_hot_lead = True
        self.update_score(max(self.lead_score, 80))
        self.updated_at = datetime.utcnow()
    
    def mark_not_interested(self, reason: Optional[str] = None) -> None:
        """Mark lead as not interested"""
        self.status = LeadStatus.NOT_INTERESTED
        if reason:
            self.notes = f"{self.notes or ''}\n[Not interested: {datetime.utcnow().isoformat()}] {reason}".strip()
        self.updated_at = datetime.utcnow()
    
    def mark_dnd(self) -> None:
        """Mark lead as Do Not Disturb"""
        self.status = LeadStatus.DND
        self.add_tag("dnd")
        self.updated_at = datetime.utcnow()
    
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
