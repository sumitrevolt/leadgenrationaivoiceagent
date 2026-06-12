"""
Niche Prospect Database — AI Voice Agent call infrastructure.
=============================================================

Har niche ke AI voice call ke liye 3 cheezein chahiye:
  1. PROSPECT DATABASE  — jinhe call karna hai (phone, name, niche-specific data)
  2. CALL SCHEMA        — AI agent ko call se pehle kya context chahiye + kya collect karna hai
  3. CALL QUEUE         — kaun-sa prospect next call karna hai (priority order)

Architecture:
  - Core storage: existing `leads` Postgres table (Lead model, qualified_data JSON field)
  - Per-niche schemas: NICHE_CALL_SCHEMA dict — AI agent reads this before dialing
  - Call queue: smart ordering (score DESC, call_attempts ASC, next_call_at first)
  - Bulk import: CSV/JSON rows → Lead records (dedupe by phone)
  - Post-call update: outcome + niche_data + schedule next action

Supported niches: all 25 voice-product niches from niches.py
Kabhi raise nahi karta. All functions defensive.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# NICHE CALL SCHEMAS
# ---------------------------------------------------------------------------
# Har niche ke liye:
#   pre_call_fields : AI agent ko call se PEHLE kya data import karna chahiye
#   collect_during  : Call ke DAURAN AI kya collect karta hai (qualification_data keys)
#   script_context  : TelecallerBrain ke liye niche-specific context hints
#   disqualifiers   : Ye sunta hai to lead drop karo (DND signal)
# ---------------------------------------------------------------------------

NICHE_CALL_SCHEMA: dict[str, dict] = {

    # ---- S-TIER ----
    "studying_abroad": {
        "display": "Study Abroad Consultants",
        "pre_call_fields": [
            {"key": "target_country",  "label": "Target country",       "type": "text",   "required": False},
            {"key": "degree_level",    "label": "Degree (UG/PG/PhD)",   "type": "select", "options": ["UG", "PG", "PhD", "Diploma", "Unknown"]},
            {"key": "intake_year",     "label": "Intake year",          "type": "text",   "required": False},
            {"key": "student_budget",  "label": "Budget range (INR)",   "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "target_country",  "question": "Kaunse country me padhna chahte ho?"},
            {"key": "budget_range",    "question": "Budget kitna hai — 20 lakh se upar ya neeche?"},
            {"key": "intake_year",     "question": "Kab jaana plan hai — 2025 ya 2026?"},
            {"key": "ielts_done",      "question": "IELTS/TOEFL ho gaya hai ya abhi karna hai?"},
        ],
        "script_context": "Study abroad consultant ke liye call — student ya parent identify karo, budget + country + intake confirm karo, counseling appointment book karo.",
        "disqualifiers": ["nahi chahiye", "done ho gaya", "pehle se admission"],
    },

    "home_loans": {
        "display": "Home Loans & LAP (DSA)",
        "pre_call_fields": [
            {"key": "loan_type",        "label": "Loan type (HL/LAP/BL)",    "type": "select", "options": ["Home Loan", "LAP", "Business Loan", "Unknown"]},
            {"key": "loan_amount_lakh", "label": "Loan amount needed (₹L)",  "type": "number", "required": False},
            {"key": "property_city",    "label": "Property city",            "type": "text",   "required": False},
            {"key": "employment_type",  "label": "Salaried / Self-employed", "type": "select", "options": ["Salaried", "Self-employed", "Business", "Unknown"]},
        ],
        "collect_during": [
            {"key": "loan_amount",      "question": "Kitna loan chahiye approximately?"},
            {"key": "property_type",    "question": "Property ready-possession hai ya under-construction?"},
            {"key": "monthly_income",   "question": "Monthly income approximate — 50k se upar hai?"},
            {"key": "existing_emi",     "question": "Koi existing EMI chal rahi hai kya?"},
        ],
        "script_context": "DSA/loan agent ke liye call — loan requirement confirm karo, property detail lelo, eligibility check ke liye callback book karo.",
        "disqualifiers": ["pehle se liya", "nahi chahiye abhi", "wrong number"],
    },

    "solar_commercial": {
        "display": "Solar Energy (Commercial B2B)",
        "pre_call_fields": [
            {"key": "property_type",    "label": "Property type",          "type": "select", "options": ["Factory", "Warehouse", "Office", "Showroom", "Farm", "Other"]},
            {"key": "monthly_bill_inr", "label": "Monthly electricity bill (₹)", "type": "number", "required": False},
            {"key": "roof_area_sqft",   "label": "Roof area (sq ft approx)", "type": "number", "required": False},
            {"key": "city",             "label": "City",                   "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "monthly_bill",     "question": "Monthly electricity bill kitna aata hai approximately?"},
            {"key": "roof_owned",       "question": "Roof aapka khud ka hai ya leased?"},
            {"key": "sanctioned_load",  "question": "Sanctioned load kitna hai — 10 kW se upar?"},
            {"key": "decision_maker",   "question": "Aap hi decision lenge ya koi aur partner bhi hain?"},
        ],
        "script_context": "Commercial solar B2B call — factory/warehouse owner, bill savings angle, subsidy angle, site visit book karo.",
        "disqualifiers": ["rented jagah", "already installed", "nahi chahiye"],
    },

    "insurance": {
        "display": "Insurance (Life & Health)",
        "pre_call_fields": [
            {"key": "insurance_type",   "label": "Insurance type",    "type": "select", "options": ["Life", "Health", "Term", "ULIP", "Vehicle", "Unknown"]},
            {"key": "age",              "label": "Age (approx)",      "type": "number", "required": False},
            {"key": "sum_assured_lakh", "label": "Coverage needed (₹L)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "coverage_type",    "question": "Life insurance chahiye ya health?"},
            {"key": "current_coverage", "question": "Abhi koi policy hai? Kitne ka coverage hai?"},
            {"key": "annual_premium",   "question": "Annual premium budget kya hai?"},
            {"key": "dependents",       "question": "Family members kitne hain — spouse, children?"},
        ],
        "script_context": "Insurance lead call — existing coverage gap samjhao, tax benefit angle, free review offer karo, policy recommendation appointment book karo.",
        "disqualifiers": ["agent hun khud", "nahi chahiye", "already hai sab"],
    },

    "coaching": {
        "display": "Coaching & Test Prep",
        "pre_call_fields": [
            {"key": "exam_target",   "label": "Target exam (JEE/NEET/UPSC/etc)", "type": "text",   "required": False},
            {"key": "student_class", "label": "Student class/year",              "type": "text",   "required": False},
            {"key": "city",          "label": "City",                            "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "exam_target",    "question": "Kaunsi exam ki taiyari kar rahe ho?"},
            {"key": "current_status", "question": "Pehle attempt hai ya repeat?"},
            {"key": "weak_subjects",  "question": "Kaunse subject me help chahiye?"},
            {"key": "start_date",     "question": "Coaching kab se join karna hai?"},
        ],
        "script_context": "Coaching institute call — exam + class confirm karo, demo class / counseling book karo, scholarship angle.",
        "disqualifiers": ["already joined", "nahi deni exam", "done ho gaya"],
    },

    "hospital_appointments": {
        "display": "Hospital / Clinic Appointments",
        "pre_call_fields": [
            {"key": "speciality",    "label": "Department/Speciality",    "type": "text",   "required": False},
            {"key": "patient_name",  "label": "Patient name",             "type": "text",   "required": False},
            {"key": "preferred_date","label": "Preferred date",           "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "speciality",     "question": "Kaunse doctor ya department se appointment chahiye?"},
            {"key": "symptom_brief",  "question": "Kya problem hai briefly — doctor ko batane ke liye?"},
            {"key": "preferred_time", "question": "Subah ya shaam — kab aana comfortable hai?"},
            {"key": "first_visit",    "question": "Pehli baar aa rahe ho ya follow-up hai?"},
        ],
        "script_context": "Hospital appointment booking call — speciality confirm karo, slot offer karo, confirmation SMS send karo.",
        "disqualifiers": ["already booked", "emergency nahi", "wrong number"],
    },

    # ---- A-TIER ----
    "dental_implants": {
        "display": "Dental / Implant Clinics",
        "pre_call_fields": [
            {"key": "treatment_type",   "label": "Treatment type",        "type": "select", "options": ["Implant", "Braces", "Whitening", "RCT", "General", "Unknown"]},
            {"key": "teeth_count",      "label": "Missing teeth (if implant)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "treatment_needed", "question": "Kaunsa treatment chahiye — implant, braces, ya general checkup?"},
            {"key": "pain_level",       "question": "Abhi koi pain hai ya scheduled checkup hai?"},
            {"key": "last_visit",       "question": "Last dental visit kab tha?"},
            {"key": "budget_ok",        "question": "Treatment budget 15,000 se upar comfortable hai?"},
        ],
        "script_context": "Dental clinic call — treatment type identify karo, pain urgency note karo, free consultation book karo.",
        "disqualifiers": ["already done", "wrong number"],
    },

    "hair_transplant": {
        "display": "Hair Transplant Clinics",
        "pre_call_fields": [
            {"key": "hair_loss_stage", "label": "Hair loss stage (1-7)", "type": "select", "options": ["1-2 (early)", "3-4 (moderate)", "5-7 (advanced)", "Unknown"]},
            {"key": "age_range",       "label": "Age range",            "type": "select", "options": ["18-25", "26-35", "36-45", "46+", "Unknown"]},
        ],
        "collect_during": [
            {"key": "hair_loss_area",  "question": "Konsa area zyada affected hai — crown, front, ya poora?"},
            {"key": "previous_treatment", "question": "Pehle koi treatment try kiya — minoxidil ya PRP?"},
            {"key": "budget_range",    "question": "Budget 60,000 to 1,50,000 ke beech comfortable hai?"},
            {"key": "consultation_ok", "question": "Free consultation ke liye aa sakte ho next week?"},
        ],
        "script_context": "Hair transplant clinic call — hair loss stage assess karo, budget qualify karo, free consultation appointment book karo.",
        "disqualifiers": ["already done", "nahi chahiye", "wrong number"],
    },

    "ivf_clinics": {
        "display": "IVF / Fertility Clinics",
        "pre_call_fields": [
            {"key": "treatment_stage", "label": "Treatment stage",   "type": "select", "options": ["First consultation", "Repeat IVF", "IUI", "Other", "Unknown"]},
            {"key": "age_female",      "label": "Female partner age", "type": "number", "required": False},
            {"key": "city",            "label": "City",               "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "trying_since",    "question": "Kitne samay se try kar rahe ho?"},
            {"key": "prev_attempts",   "question": "Pehle koi treatment hua hai — IUI ya IVF?"},
            {"key": "doctor_referral", "question": "Kisi doctor ne refer kiya hai ya khud research kar rahe ho?"},
            {"key": "city_preference", "question": "Kaunse city me treatment prefer karoge?"},
        ],
        "script_context": "IVF clinic call — sensitive call, empathetic tone rakho, treatment stage identify karo, free doctor consultation book karo.",
        "disqualifiers": ["pregnant hain already", "wrong number", "nahi chahiye"],
    },

    "immigration": {
        "display": "Immigration & Visa Consultants",
        "pre_call_fields": [
            {"key": "destination",     "label": "Destination country", "type": "text",   "required": False},
            {"key": "visa_type",       "label": "Visa type",           "type": "select", "options": ["PR", "Work Permit", "Student", "Visitor", "Business", "Unknown"]},
            {"key": "education",       "label": "Education level",     "type": "select", "options": ["10th/12th", "Graduate", "Post-Graduate", "PhD", "Unknown"]},
        ],
        "collect_during": [
            {"key": "destination",     "question": "Kaunse country me jaana hai — Canada, Australia, ya koi aur?"},
            {"key": "purpose",         "question": "PR ke liye ja rahe ho ya work permit?"},
            {"key": "language_score",  "question": "IELTS ya PTE score hai? Kitna?"},
            {"key": "budget_ok",       "question": "Consulting fee 50,000 se upar comfortable hai?"},
        ],
        "script_context": "Immigration consultant call — destination + visa type confirm karo, eligibility assess karo, free assessment book karo.",
        "disqualifiers": ["already applied", "already migrated", "wrong number"],
    },

    "modular_kitchen": {
        "display": "Modular Kitchen & Interiors",
        "pre_call_fields": [
            {"key": "project_type",  "label": "Project type",       "type": "select", "options": ["Modular Kitchen", "Full Interior", "Wardrobe", "False Ceiling", "Other"]},
            {"key": "flat_size",     "label": "Flat size (sq ft)",  "type": "number", "required": False},
            {"key": "possession",    "label": "Possession status",  "type": "select", "options": ["Ready", "3 months", "6 months", "1 year+", "Unknown"]},
        ],
        "collect_during": [
            {"key": "project_scope", "question": "Sirf kitchen chahiye ya full home interior?"},
            {"key": "budget_range",  "question": "Budget kya hai — 1.5 lakh se 3 lakh, ya upar?"},
            {"key": "possession_date", "question": "Possession kab ho raha hai?"},
            {"key": "site_visit_ok", "question": "Site visit ke liye kab comfortable ho aage week?"},
        ],
        "script_context": "Modular kitchen/interior design call — scope confirm karo, budget qualify karo, site visit schedule karo.",
        "disqualifiers": ["already done", "rented hai", "nahi chahiye"],
    },

    "finance_advisory": {
        "display": "Financial Advisory / Wealth Management",
        "pre_call_fields": [
            {"key": "advisory_type",   "label": "Advisory type",      "type": "select", "options": ["Mutual Funds", "Tax Planning", "Portfolio Review", "Retirement", "Wealth Mgmt", "Unknown"]},
            {"key": "investment_amount","label": "Investment amount (₹L)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "current_investments", "question": "Abhi kahan invest kiya hua hai — FD, MF, stocks?"},
            {"key": "investment_goal",    "question": "Goal kya hai — retirement, child education, ya house?"},
            {"key": "risk_appetite",      "question": "Risk lena comfortable hai ya safe returns prefer karte ho?"},
            {"key": "annual_income",      "question": "Annual income approximately 10 lakh se upar hai?"},
        ],
        "script_context": "Financial advisor call — investment goal + risk profile identify karo, free portfolio review offer karo.",
        "disqualifiers": ["advisor hun khud", "nahi chahiye", "wrong number"],
    },

    "ca_legal": {
        "display": "CA / Accounting Firms",
        "pre_call_fields": [
            {"key": "service_needed", "label": "Service needed",     "type": "select", "options": ["ITR Filing", "GST", "Company Registration", "Audit", "Bookkeeping", "Unknown"]},
            {"key": "business_type",  "label": "Business type",     "type": "select", "options": ["Sole Proprietor", "Pvt Ltd", "Partnership", "Individual", "Unknown"]},
            {"key": "turnover_cr",    "label": "Annual turnover (₹Cr)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "service_type",   "question": "Kaunsi service chahiye — ITR, GST, ya company registration?"},
            {"key": "current_ca",     "question": "Abhi koi CA hai? Kyun change karna hai?"},
            {"key": "filing_deadline","question": "Koi urgent deadline hai — GST return ya ITR?"},
            {"key": "company_size",   "question": "Kitne employees hain approximately?"},
        ],
        "script_context": "CA firm call — service type confirm karo, current pain point identify karo, free consultation offer karo.",
        "disqualifiers": ["CA hun khud", "nahi chahiye", "wrong number"],
    },

    "edtech_creators": {
        "display": "Edtech / Online Course Creators",
        "pre_call_fields": [
            {"key": "course_topic",   "label": "Course topic",         "type": "text",   "required": False},
            {"key": "platform",       "label": "Current platform",     "type": "select", "options": ["Udemy", "Teachable", "Own website", "None", "Other"]},
            {"key": "student_count",  "label": "Approx students",      "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "course_topic",   "question": "Kaunsa subject padhate ho — technology, finance, ya kuch aur?"},
            {"key": "revenue_target", "question": "Monthly revenue target kya hai — 1 lakh se upar?"},
            {"key": "pain_point",     "question": "Sabse bada challenge kya hai — leads, sales, ya content?"},
            {"key": "platform_used",  "question": "Abhi kaunsa platform use karte ho?"},
        ],
        "script_context": "Edtech creator call — course + platform identify karo, lead generation pain point target karo, demo book karo.",
        "disqualifiers": ["nahi chahiye", "already sorted", "wrong number"],
    },

    # ---- B-TIER ----
    "hvac_commercial": {
        "display": "HVAC / Commercial AC",
        "pre_call_fields": [
            {"key": "facility_type",  "label": "Facility type",       "type": "select", "options": ["Office", "Hotel", "Hospital", "Factory", "Mall", "Other"]},
            {"key": "ton_estimate",   "label": "Tonnage required (TR)", "type": "number", "required": False},
            {"key": "project_stage",  "label": "Project stage",       "type": "select", "options": ["New installation", "Replacement", "Service contract", "Unknown"]},
        ],
        "collect_during": [
            {"key": "facility_size",  "question": "Facility kitne area ki hai — 5,000 sq ft se upar?"},
            {"key": "project_timeline", "question": "Installation kab chahiye?"},
            {"key": "budget_range",   "question": "Budget 5 lakh se upar hai?"},
            {"key": "decision_maker", "question": "Aap hi final decision lenge?"},
        ],
        "script_context": "Commercial HVAC call — facility type + size identify karo, project timeline qualify karo, site visit book karo.",
        "disqualifiers": ["residential hai", "nahi chahiye", "wrong number"],
    },

    "real_estate_commercial": {
        "display": "Commercial Real Estate",
        "pre_call_fields": [
            {"key": "property_type",  "label": "Property type",       "type": "select", "options": ["Office Space", "Shop", "Warehouse", "Plot", "Showroom", "Unknown"]},
            {"key": "budget_cr",      "label": "Budget (₹Cr)",        "type": "number", "required": False},
            {"key": "area_sqft",      "label": "Area required (sq ft)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "purpose",        "question": "Office ke liye chahiye ya investment?"},
            {"key": "location_pref",  "question": "Kaunsa area prefer karte ho?"},
            {"key": "budget_range",   "question": "Budget 50 lakh se upar hai?"},
            {"key": "timeline",       "question": "Kab tak finalize karna hai?"},
        ],
        "script_context": "Commercial real estate call — purpose + budget qualify karo, location preference le, site tour schedule karo.",
        "disqualifiers": ["residential chahiye", "nahi chahiye", "wrong number"],
    },

    "cloud_kitchen": {
        "display": "Cloud Kitchen / Restaurant",
        "pre_call_fields": [
            {"key": "kitchen_type",  "label": "Type",               "type": "select", "options": ["Cloud Kitchen", "Restaurant", "QSR", "Catering", "Other"]},
            {"key": "cuisine",       "label": "Cuisine type",       "type": "text",   "required": False},
            {"key": "monthly_orders","label": "Monthly orders (approx)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "platform",      "question": "Zomato/Swiggy pe already listed ho?"},
            {"key": "pain_point",    "question": "Sabse bada problem — orders, delivery, ya marketing?"},
            {"key": "expansion_plan","question": "New location open karne ka plan hai?"},
            {"key": "revenue_target","question": "Monthly revenue target kya hai?"},
        ],
        "script_context": "Cloud kitchen call — platform + monthly orders identify karo, growth pain point target karo, demo call book karo.",
        "disqualifiers": ["band ho gaya", "wrong number", "nahi chahiye"],
    },

    "event_management": {
        "display": "Event Management",
        "pre_call_fields": [
            {"key": "event_type",    "label": "Event type",          "type": "select", "options": ["Wedding", "Corporate", "Birthday", "Exhibition", "Conference", "Other"]},
            {"key": "budget_lakh",   "label": "Budget (₹L)",         "type": "number", "required": False},
            {"key": "event_date",    "label": "Event date (approx)", "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "event_size",    "question": "Kitne guests expected hain?"},
            {"key": "venue_decided", "question": "Venue decide ho gaya hai ya wo bhi chahiye?"},
            {"key": "budget_range",  "question": "Budget 2 lakh se upar hai?"},
            {"key": "timeline",      "question": "Event kab hai — next 3 months me?"},
        ],
        "script_context": "Event management call — event type + date + budget identify karo, requirement details le, site visit/meeting book karo.",
        "disqualifiers": ["already booked", "nahi chahiye", "wrong number"],
    },

    "skin_dermatology": {
        "display": "Skin / Dermatology Clinics",
        "pre_call_fields": [
            {"key": "treatment_type","label": "Treatment type",      "type": "select", "options": ["Acne/Scar", "Laser", "Anti-aging", "Pigmentation", "Hair Removal", "General Checkup", "Unknown"]},
        ],
        "collect_during": [
            {"key": "main_concern",  "question": "Kya concern hai — acne, dark spots, ya kuch aur?"},
            {"key": "prev_treatment","question": "Pehle koi treatment liya hai iske liye?"},
            {"key": "budget_ok",     "question": "Treatment budget 5,000 se upar comfortable hai?"},
            {"key": "consultation_ok","question": "Free consultation ke liye kab aa sakte ho?"},
        ],
        "script_context": "Dermatology clinic call — skin concern identify karo, urgency note karo, free consultation book karo.",
        "disqualifiers": ["wrong number", "nahi chahiye"],
    },

    "ayurveda_wellness": {
        "display": "Ayurveda / Wellness Centers",
        "pre_call_fields": [
            {"key": "treatment_goal","label": "Goal",                "type": "select", "options": ["Weight loss", "Stress/Anxiety", "Chronic condition", "Detox", "General wellness", "Unknown"]},
        ],
        "collect_during": [
            {"key": "health_concern","question": "Kaunsi health problem ke liye treatment chahiye?"},
            {"key": "duration",      "question": "Yeh problem kitne time se hai?"},
            {"key": "preferred_mode","question": "Center pe aana prefer karte ho ya home visits?"},
            {"key": "budget_range",  "question": "Monthly wellness budget 3,000 se upar hai?"},
        ],
        "script_context": "Ayurveda/wellness call — health concern identify karo, duration assess karo, free consultation ya trial session book karo.",
        "disqualifiers": ["wrong number", "nahi chahiye"],
    },

    "ecommerce_d2c": {
        "display": "E-commerce / D2C Brands",
        "pre_call_fields": [
            {"key": "product_category","label": "Product category",  "type": "text",   "required": False},
            {"key": "monthly_revenue", "label": "Monthly revenue (₹L)", "type": "number", "required": False},
            {"key": "platform",        "label": "Platform",          "type": "select", "options": ["Amazon", "Flipkart", "Own website", "Instagram", "Multiple", "Unknown"]},
        ],
        "collect_during": [
            {"key": "pain_point",    "question": "Sabse bada challenge kya hai — traffic, conversion, ya returns?"},
            {"key": "ad_spend",      "question": "Monthly ad spend kitna hai?"},
            {"key": "growth_target", "question": "Next 6 months ka revenue target kya hai?"},
            {"key": "team_size",     "question": "Team kitni badi hai?"},
        ],
        "script_context": "E-commerce brand call — pain point identify karo, current metrics le, growth strategy call book karo.",
        "disqualifiers": ["band ho gaya", "nahi chahiye", "wrong number"],
    },

    "solar_residential": {
        "display": "Solar Energy (Residential)",
        "pre_call_fields": [
            {"key": "property_type",    "label": "Property type",          "type": "select", "options": ["Independent house", "Villa", "Apartment", "Unknown"]},
            {"key": "monthly_bill_inr", "label": "Monthly electricity bill (₹)", "type": "number", "required": False},
            {"key": "city",             "label": "City",                   "type": "text",   "required": False},
        ],
        "collect_during": [
            {"key": "monthly_bill",     "question": "Monthly bijli bill kitna aata hai?"},
            {"key": "roof_owned",       "question": "Apna makan hai — roof use kar sakte hain?"},
            {"key": "kw_estimate",      "question": "2 kW ya 5 kW system chahiye?"},
            {"key": "subsidy_aware",    "question": "PM Surya Ghar subsidy ke baare me pata hai?"},
        ],
        "script_context": "Residential solar call — bill savings angle, PM Surya Ghar subsidy angle, site survey book karo.",
        "disqualifiers": ["already installed", "rented hai", "nahi chahiye"],
    },

    "travel_packages": {
        "display": "Travel & Tourism",
        "pre_call_fields": [
            {"key": "destination",   "label": "Destination",        "type": "text",   "required": False},
            {"key": "travel_type",   "label": "Travel type",        "type": "select", "options": ["Honeymoon", "Family", "Corporate", "Adventure", "Religious", "Unknown"]},
            {"key": "budget_lakh",   "label": "Budget (₹L per person)", "type": "number", "required": False},
        ],
        "collect_during": [
            {"key": "destination",   "question": "Kahan jaana plan hai — domestic ya international?"},
            {"key": "travel_dates",  "question": "Kab jaana plan hai approximately?"},
            {"key": "group_size",    "question": "Kitne log hain?"},
            {"key": "budget_range",  "question": "Per person budget 20,000 se upar hai?"},
        ],
        "script_context": "Travel agency call — destination + dates + group size qualify karo, personalized itinerary offer karo, booking call book karo.",
        "disqualifiers": ["already booked", "nahi chahiye", "wrong number"],
    },

    "upskilling": {
        "display": "Upskilling / Professional Courses",
        "pre_call_fields": [
            {"key": "course_type",  "label": "Course type",         "type": "select", "options": ["Tech (Data/AI/Dev)", "MBA/Management", "Finance (CFA/CA)", "Digital Marketing", "Other"]},
            {"key": "current_job",  "label": "Currently employed?", "type": "select", "options": ["Yes", "No", "Fresher", "Unknown"]},
        ],
        "collect_during": [
            {"key": "goal",         "question": "Course kyun karna hai — job change, promotion, ya skill upgrade?"},
            {"key": "current_role", "question": "Abhi kya kaam karte ho?"},
            {"key": "start_timeline","question": "Kab se start karna hai?"},
            {"key": "budget_ok",    "question": "Course fee 30,000 se upar comfortable hai?"},
        ],
        "script_context": "Upskilling institute call — career goal identify karo, current skill gap note karo, demo/counseling session book karo.",
        "disqualifiers": ["already enrolled", "nahi chahiye", "wrong number"],
    },
}

# Fallback schema for any niche not explicitly defined
_DEFAULT_SCHEMA: dict = {
    "pre_call_fields": [
        {"key": "contact_name", "label": "Contact name",    "type": "text",   "required": False},
        {"key": "city",         "label": "City",            "type": "text",   "required": False},
        {"key": "notes",        "label": "Notes",           "type": "textarea", "required": False},
    ],
    "collect_during": [
        {"key": "requirement",  "question": "Aapki requirement kya hai?"},
        {"key": "budget",       "question": "Budget approximately kya hai?"},
        {"key": "timeline",     "question": "Kab tak chahiye?"},
    ],
    "script_context": "Generic prospect call — requirement + timeline + budget identify karo, next step book karo.",
    "disqualifiers": ["wrong number", "nahi chahiye"],
}


def get_niche_schema(niche_key: str) -> dict:
    """Niche ka call schema — AI agent reads before dialing. Fallback to default."""
    base = NICHE_CALL_SCHEMA.get((niche_key or "").strip().lower(), _DEFAULT_SCHEMA)
    from app.niches import NICHES
    niche_cfg = NICHES.get((niche_key or "").strip().lower(), {})
    return {
        "niche": niche_key,
        "display": base.get("display") or niche_cfg.get("name", niche_key),
        "pre_call_fields": base.get("pre_call_fields", []),
        "collect_during": base.get("collect_during", []),
        "script_context": base.get("script_context", ""),
        "disqualifiers": base.get("disqualifiers", []),
        "qualification_questions": niche_cfg.get("qualification_questions", []),
        "pitch_hook": niche_cfg.get("pitch_hook", ""),
        "band": niche_cfg.get("lead_band", "A"),
    }


# ---------------------------------------------------------------------------
# CALL QUEUE LOGIC
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def call_queue_next(client_id: str, niche: str, limit: int = 10) -> list[dict]:
    """Get next prospects to call for a given client+niche.

    Priority:
      1. Scheduled callbacks (next_call_at <= now, status=callback)
      2. Hot leads not yet called (is_hot_lead=True, call_attempts=0)
      3. New leads by score (lead_score DESC)
      4. Attempted leads (call_attempts > 0, status=contacted, score DESC)

    Returns list of dicts with lead data + niche schema context.
    Kabhi raise nahi karta.
    """
    try:
        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus

        results: list[dict] = []
        async with get_async_session() as session:
            from sqlalchemy import and_, or_, select

            now = _now_utc()
            cid = (client_id or "").strip()
            n = (niche or "").strip().lower()

            base_filter = and_(
                Lead.assigned_to == cid,
                Lead.niche == n,
                Lead.status.notin_([
                    LeadStatus.DND,
                    LeadStatus.WRONG_NUMBER,
                    LeadStatus.NOT_INTERESTED,
                    LeadStatus.CONVERTED,
                    LeadStatus.LOST,
                ]),
            )

            # Priority 1: callbacks due
            cb_q = (
                select(Lead)
                .where(and_(base_filter, Lead.status == LeadStatus.CALLBACK, Lead.next_call_at <= now))
                .order_by(Lead.next_call_at.asc())
                .limit(limit)
            )
            cb_res = await session.execute(cb_q)
            for lead in cb_res.scalars():
                results.append(_lead_to_call_dict(lead))

            remaining = limit - len(results)
            if remaining <= 0:
                return results

            # Priority 2 + 3: new leads (hot first, then by score)
            new_q = (
                select(Lead)
                .where(and_(base_filter, Lead.status == LeadStatus.NEW))
                .order_by(Lead.is_hot_lead.desc(), Lead.lead_score.desc(), Lead.created_at.asc())
                .limit(remaining)
            )
            new_res = await session.execute(new_q)
            for lead in new_res.scalars():
                results.append(_lead_to_call_dict(lead))

            remaining = limit - len(results)
            if remaining > 0:
                # Priority 4: contacted (retry) — max 3 attempts
                retry_q = (
                    select(Lead)
                    .where(and_(
                        base_filter,
                        Lead.status == LeadStatus.CONTACTED,
                        Lead.call_attempts < 3,
                    ))
                    .order_by(Lead.lead_score.desc(), Lead.call_attempts.asc())
                    .limit(remaining)
                )
                retry_res = await session.execute(retry_q)
                for lead in retry_res.scalars():
                    results.append(_lead_to_call_dict(lead))

        return results
    except Exception as e:
        logger.warning(f"call_queue_next error: {e}")
        return []


def _lead_to_call_dict(lead: Any) -> dict:
    """Lead ORM object -> call queue item dict."""
    try:
        qual = json.loads(lead.qualification_data or "{}") if lead.qualification_data else {}
    except Exception:
        qual = {}
    return {
        "id": lead.id,
        "company_name": lead.company_name,
        "contact_name": lead.contact_name,
        "phone": lead.phone,
        "email": lead.email,
        "city": lead.city,
        "niche": lead.niche,
        "lead_score": lead.lead_score,
        "is_hot_lead": lead.is_hot_lead,
        "status": lead.status.value if lead.status else None,
        "call_attempts": lead.call_attempts,
        "last_called_at": lead.last_called_at.isoformat() if lead.last_called_at else None,
        "next_call_at": lead.next_call_at.isoformat() if lead.next_call_at else None,
        "notes": lead.notes,
        "qualification_data": qual,
        "niche_context": get_niche_schema(lead.niche or ""),
    }


async def update_after_call(
    lead_id: str,
    outcome: str,          # qualified | callback | not_interested | wrong_number | dnd | voicemail
    notes: str = "",
    niche_data: dict | None = None,
    callback_hours: int = 24,
) -> dict:
    """Post-call update — status + niche_data + schedule next action.

    outcome:
      qualified       -> status=QUALIFIED, is_hot_lead=True, score+=20
      callback        -> status=CALLBACK, next_call_at=+callback_hours
      not_interested  -> status=NOT_INTERESTED
      wrong_number    -> status=WRONG_NUMBER
      dnd             -> status=DND, tag dnd
      voicemail       -> status stays CONTACTED, call_attempts++, retry next day
    """
    try:
        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus

        async with get_async_session() as session:
            result = await session.get(Lead, lead_id)
            if not result:
                return {"ok": False, "error": "lead not found"}

            lead = result
            lead.mark_called()

            if niche_data:
                existing = lead.get_qualification_data()
                existing.update(niche_data)
                lead.set_qualification_data(existing)

            if notes:
                lead.notes = f"{lead.notes or ''}\n[{_now_utc().strftime('%Y-%m-%d %H:%M')} UTC] {notes}".strip()

            outcome_l = (outcome or "").strip().lower()
            if outcome_l == "qualified":
                lead.status = LeadStatus.QUALIFIED
                lead.is_hot_lead = True
                lead.update_score(min(100, lead.lead_score + 20))
            elif outcome_l == "callback":
                lead.status = LeadStatus.CALLBACK
                lead.next_call_at = _now_utc() + timedelta(hours=max(1, callback_hours))
            elif outcome_l == "not_interested":
                lead.mark_not_interested(notes)
            elif outcome_l == "wrong_number":
                lead.status = LeadStatus.WRONG_NUMBER
            elif outcome_l == "dnd":
                lead.mark_dnd()
            elif outcome_l == "voicemail":
                lead.status = LeadStatus.CONTACTED
                lead.next_call_at = _now_utc() + timedelta(hours=24)
            # default: CONTACTED (mark_called already set)

            await session.commit()
            return {"ok": True, "lead_id": lead_id, "status": lead.status.value, "score": lead.lead_score}
    except Exception as e:
        logger.warning(f"update_after_call error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# BULK IMPORT
# ---------------------------------------------------------------------------

async def bulk_import(
    rows: list[dict],
    niche: str,
    client_id: str,
    source: str = "import",
) -> dict:
    """Bulk import prospects for a niche → Lead records (dedupe by phone).

    row keys (flexible, alias-mapped):
      phone/Phone/mobile/Mobile  →  phone
      name/Name/company/Company/business/Business  →  company_name
      contact/contact_name/owner  →  contact_name
      email/Email  →  email
      city/City    →  city
      state/State  →  state
      + any extra key goes into qualification_data (niche-specific)

    Returns {inserted, skipped, errors}.
    """
    from app.models.base import get_async_session
    from app.models.lead import Lead, LeadSource, LeadStatus

    inserted = 0
    skipped = 0
    errors = 0
    n = (niche or "").strip().lower()
    cid = (client_id or "").strip()

    _PHONE_KEYS = {"phone", "Phone", "mobile", "Mobile", "contact_number", "ContactNumber", "ph"}
    _NAME_KEYS  = {"company", "Company", "business", "Business", "name", "Name", "shop", "Shop"}
    _CONTACT_KEYS = {"contact_name", "contact", "owner", "Owner", "person"}
    _EMAIL_KEYS = {"email", "Email", "e-mail"}
    _CITY_KEYS  = {"city", "City", "location", "Location"}

    try:
        src_enum = LeadSource[source.upper()] if source.upper() in LeadSource.__members__ else LeadSource.IMPORT
    except Exception:
        src_enum = LeadSource.IMPORT

    async with get_async_session() as session:
        for row in rows:
            try:
                # --- extract phone ---
                phone = ""
                for k in _PHONE_KEYS:
                    if row.get(k):
                        phone = str(row[k]).strip()
                        break
                if not phone:
                    errors += 1
                    continue

                # clean phone
                digits = "".join(c for c in phone if c.isdigit())
                if len(digits) < 10:
                    errors += 1
                    continue
                if len(digits) == 10:
                    phone = "+91" + digits
                elif len(digits) == 12 and digits.startswith("91"):
                    phone = "+" + digits
                elif not phone.startswith("+"):
                    phone = "+91" + digits[-10:]

                # --- dedupe by phone + client ---
                from sqlalchemy import and_, select
                exists = await session.execute(
                    select(Lead.id).where(and_(Lead.phone == phone, Lead.assigned_to == cid)).limit(1)
                )
                if exists.scalar():
                    skipped += 1
                    continue

                # --- extract other fields ---
                company = ""
                for k in _NAME_KEYS:
                    if row.get(k):
                        company = str(row[k]).strip()
                        break
                if not company:
                    company = phone  # fallback

                contact = ""
                for k in _CONTACT_KEYS:
                    if row.get(k):
                        contact = str(row[k]).strip()
                        break

                email = ""
                for k in _EMAIL_KEYS:
                    if row.get(k):
                        email = str(row[k]).strip()
                        break

                city = ""
                for k in _CITY_KEYS:
                    if row.get(k):
                        city = str(row[k]).strip()
                        break

                # remaining keys → qualification_data
                used = _PHONE_KEYS | _NAME_KEYS | _CONTACT_KEYS | _EMAIL_KEYS | _CITY_KEYS | {"state", "State"}
                niche_data = {k: v for k, v in row.items() if k not in used and v not in (None, "")}

                lead = Lead(
                    id=str(uuid.uuid4()),
                    company_name=company,
                    contact_name=contact or None,
                    phone=phone,
                    email=email or None,
                    city=city or None,
                    state=(row.get("state") or row.get("State") or ""),
                    niche=n,
                    category=n,
                    assigned_to=cid,
                    source=src_enum,
                    status=LeadStatus.NEW,
                    qualification_data=json.dumps(niche_data) if niche_data else None,
                )
                session.add(lead)
                inserted += 1

            except Exception as row_err:
                logger.debug(f"bulk_import row error: {row_err}")
                errors += 1

        try:
            await session.commit()
        except Exception as ce:
            logger.warning(f"bulk_import commit error: {ce}")
            return {"inserted": 0, "skipped": skipped, "errors": errors + inserted, "error": str(ce)}

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


# ---------------------------------------------------------------------------
# STATS
# ---------------------------------------------------------------------------

async def niche_stats(client_id: str, niche: str | None = None) -> dict:
    """Per-niche prospect stats for a client. Kabhi raise nahi."""
    try:
        from app.models.base import get_async_session
        from app.models.lead import Lead, LeadStatus
        from sqlalchemy import and_, func, select

        cid = (client_id or "").strip()
        async with get_async_session() as session:
            q = select(
                Lead.niche,
                Lead.status,
                func.count(Lead.id).label("cnt"),
                func.avg(Lead.lead_score).label("avg_score"),
            ).where(Lead.assigned_to == cid)
            if niche:
                q = q.where(Lead.niche == niche.strip().lower())
            q = q.group_by(Lead.niche, Lead.status)

            rows = await session.execute(q)
            out: dict[str, dict] = {}
            for row in rows:
                n_key = row.niche or "unknown"
                if n_key not in out:
                    out[n_key] = {"niche": n_key, "total": 0, "by_status": {}, "avg_score": 0, "callable": 0}
                status_val = row.status.value if row.status else "unknown"
                out[n_key]["by_status"][status_val] = row.cnt
                out[n_key]["total"] += row.cnt
                out[n_key]["avg_score"] = round(row.avg_score or 0, 1)
                if status_val in ("new", "contacted", "callback"):
                    out[n_key]["callable"] += row.cnt

            return {"niches": list(out.values()), "client_id": cid}
    except Exception as e:
        logger.warning(f"niche_stats error: {e}")
        return {"niches": [], "error": str(e)}
