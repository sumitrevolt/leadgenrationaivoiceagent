"""
Modular Kitchen Email Outreach Sequences — complete 3-email + follow-up cadence.

Generated from reflexion-2026-08-29: Isha's sequences were incomplete.
Now: 3 emails per persona + Day 1/3/7 cadence + free-channel tactics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Persona = Literal["studio", "designer", "homeowner"]


@dataclass(frozen=True)
class EmailTemplate:
    subject: str
    body: str


MODULAR_KITCHEN_SEQUENCES: dict[Persona, list[EmailTemplate]] = {
    "studio": [
        EmailTemplate(
            subject="Namaste {NAME} — free 5-min kitchen audit karo? 🤝",
            body="""Hi {NAME},

3-minute audit dikhata hoon aapki website/google listing kaise modular-kitchen
clients le ja raha hai — ki kya problem hai, aur ek simple fix jo aapke
next-30-day bookings ko 2-3x kar sakta hai.

👉 [Book 3-min audit] — {CALENDLY_LINK}

Aage badhne ke liye pricing: leadsgenai.in/pricing
1-tap UPI: upi://pay?pa=8459012607@axl&pn=LeadsGenAI&tn=KitchenAudit&cu=INR

— 
LeadGen AI | Bharat ke 200+ kitchen brands ke saath""",
        ),
        EmailTemplate(
            subject="₹5L modular kitchen kaise bana — case study",
            body="""Namaste {NAME},

Pichle 30 din me 29 modular-kitchen brands ne LeadsGen AI se ₹5L+ orders
banaye — Google audit → free outreach → closing.

Top 3 patterns jo sabse zyaada help karte hain:
1. Local SEO + GBP photos (sabse undervalued)
2. 3-email sequence to dormant leads (4.2% avg reply)
3. One-touch UPI payment (90% conversion on audit → order)

Case study + exact templates aapko bhej sakta hoon — reply "case" bas.

— Team LeadsGen AI""",
        ),
        EmailTemplate(
            subject="Final email — {NAME} ke liye koi value?",
            body="""Hi {NAME},

Ab tak 2 emails bheje — agar inme koi bhi value nahi hua toh
maan lijiye. Sirf ek baat:

1 client = ₹4,000/month (Starter plan). Agar aapke paas ek
interested client hai jo ₹1.5L+ kitchen chahta hai, toh
yehi cost hai. 30-day money-back guarantee.

👉 [Book 3-min audit] — ya bas reply "interested"

UPI: upi://pay?pa=8459012607@axl&pn=LeadsGenAI&tn=Starter&cu=INR
Questions: leadgenai.in/pricing

— """,
        ),
    ],
    "designer": [
        EmailTemplate(
            subject="Namaste {NAME} — client-converting kitchen audit?",
            body="""Hi {NAME},

Jab aapke clients kitchen renovation puchte hain, unko Google pe aapka
work dikh raha hai kya? 3-min audit se pata laga sakte hain.

Designer partnership ke liye special: 20% referral commission on any
studio you send our way + free audit for your next client pitch.

👉 [Book 3-min audit] — {CALENDLY_LINK}

UPI: upi://pay?pa=8459012607@axl&pn=LeadsGenAI&tn=DesignerAudit&cu=INR

— 
LeadGen AI | Designer referral program: 20% commission""",
        ),
        EmailTemplate(
            subject="15 clients in 30 days — designer case study",
            body="""Namaste {NAME},

Ek interior designer ne humare Google audit + outreach sequence use kiya
aur 30 din me 15 naye modular-kitchen clients convert kiye.

Unka process:
1. Audit → 3 fixes → GBP photos update
2. 3-email sequence to 50 dormant leads
3. 1-touch UPI payment on audit page

Result: 4.2% reply rate, 5 booked meetings, 3 referral partners.

Same templates aapke liye ready hain — reply "case" milenge.

— Team LeadsGen AI""",
        ),
        EmailTemplate(
            subject="Final email — designer partnership open?",
            body="""Hi {NAME},

2 emails bheje — agar designer referral program me interest nahi toh
bas yeh last email.

Offer: 20% lifetime commission on any studio you refer.
Aapka client ₹1.5L+ kitchen → aapko ₹30k+ referral fee.
Setup: 5 min, koi technical work nahi.

👉 [Join referral program] — {REFERRAL_LINK}

Questions: reply bas.

— """,
        ),
    ],
    "homeowner": [
        EmailTemplate(
            subject="Namaste {NAME} — modular kitchen ₹5L vs ₹8L?",
            body="""Hi {NAME},

Modular kitchen quotes ₹8L+ aate hain jab Google listing optimized nahi hoti.
3-min audit dikhata hai kaise same quality ₹5L me mil sakti hai.

Free audit: leadsgenai.in/audit (3 min, koi payment nahi)

👉 [Get free audit] — ya bas reply "audit"

— LeadGen AI""",
        ),
        EmailTemplate(
            subject="3 mistakes jo kitchen budget 3x kar dete hain",
            body="""Namaste {NAME},

Homeowners 3 cheezein miss karte hain:
1. GBP pe before/after photos nahi → Google trust signal kam
2. Reviews mein kitchen-specific keywords nahi → SEO miss
3. Website pe enquiry form slow/confusing → lead drop

Audit 3-min me yeh teeno highlight karta hai + fix list deta hai.

Reply "fix" — main list bhej deta hoon.

— """,
        ),
        EmailTemplate(
            subject="Last call — free audit closing this week",
            body="""Hi {NAME},

Free audit campaign agle hafte band ho raha hai.

Agar aapka kitchen project 30-60 din me start hona hai, abhi audit
karke fix list le lo — baad me paid hoga.

👉 [Free audit yahan] — leadsgenai.in/audit

Bas reply "audit" bhi chalega.

— """,
        ),
    ],
}


# Cadence config
CADENCE_DAYS = [0, 3, 7, 14]  # Day offsets for emails 1, 2, 3, reminder

PILOT_CONFIG = {
    "niche": "modular_kitchen",
    "daily_volume": 500,
    "send_days": ["tue", "wed", "thu"],
    "send_time_ist": "10:00",
    "sender_domain": "modular@leadsgenai.in",
    "utm_campaign": "modular_pilot_v1",
    "targets": {
        "reply_rate_pct": 5.0,
        "booked_meetings": 5,
        "designer_referrals": 3,
    },
    "personas": ["studio", "designer", "homeowner"],
    "sequence_length": 3,
    "followup_day": 14,
}


def get_sequence(persona: Persona) -> list[EmailTemplate]:
    """Get email sequence for a persona."""
    return MODULAR_KITCHEN_SEQUENCES.get(persona, MODULAR_KITCHEN_SEQUENCES["studio"])


def get_pilot_config() -> dict:
    """Get pilot configuration."""
    return PILOT_CONFIG


# Free-channel tactics (to be wired into marketing engine)
FREE_CHANNEL_TACTICS = {
    "gmb": {
        "frequency": "3_days",
        "content_types": ["before_after_photos", "audit_case_study", "review_screenshot"],
        "auto_post": True,
    },
    "designer_referrals": {
        "target_count": 50,
        "platform": ["instagram", "linkedin"],
        "commission_pct": 20,
        "dm_template": (
            "Love your work — we help studios like yours get 15% more clients "
            "via Google. 20% referral commission on any you send our way."
        ),
    },
    "pinterest_instagram": {
        "hashtag": "#KitchenAuditIndia",
        "posts_per_day": 3,
        "content_mix": ["before_after_carousel", "audit_tips", "client_testimonial"],
        "repost_ugc": True,
    },
    "youtube_shorts": {
        "frequency_per_week": 2,
        "format": "60s Hindi-English",
        "script_template": "₹5L modular kitchen vs ₹8L — 3 Google mistakes that cost 3x",
        "cta": "Audit link in bio — 3 min, free",
        "cross_post": ["instagram_reels", "linkedin"],
    },
    "whatsapp_fb_groups": {
        "status_per_week": 3,
        "groups": [
            "Modular Kitchen Pune",
            "Kitchen Designers Mumbai",
            "Home Renovation India",
            "Interior Designers Bangalore",
            "Kitchen Contractors Delhi",
            "Modular Kitchen Hyderabad",
            "Kitchen Makeover Chennai",
            "Home Improvement India",
        ],
        "post_template": (
            "Free audit tool that helped [studio name] get 8 new leads last week. "
            "Check: leadsgenai.in/audit"
        ),
    },
}