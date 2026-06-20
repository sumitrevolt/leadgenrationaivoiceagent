"""Per-niche call-data schema — the NICHE_CALL_SCHEMA dict (qualification fields per niche).

Extracted from app/platform/niche_database.py (2026-06-20 refactor) — pure data, re-exported.
"""

NICHE_CALL_SCHEMA: dict[str, dict] = {
    # ---- S-TIER ----
    "studying_abroad": {
        "display": "Study Abroad Consultants",
        "pre_call_fields": [
            {"key": "target_country", "label": "Target country", "type": "text", "required": False},
            {
                "key": "degree_level",
                "label": "Degree (UG/PG/PhD)",
                "type": "select",
                "options": ["UG", "PG", "PhD", "Diploma", "Unknown"],
            },
            {"key": "intake_year", "label": "Intake year", "type": "text", "required": False},
            {
                "key": "student_budget",
                "label": "Budget range (INR)",
                "type": "text",
                "required": False,
            },
        ],
        "collect_during": [
            {"key": "target_country", "question": "Kaunse country me padhna chahte ho?"},
            {"key": "budget_range", "question": "Budget kitna hai — 20 lakh se upar ya neeche?"},
            {"key": "intake_year", "question": "Kab jaana plan hai — 2025 ya 2026?"},
            {"key": "ielts_done", "question": "IELTS/TOEFL ho gaya hai ya abhi karna hai?"},
        ],
        "script_context": "Study abroad consultant ke liye call — student ya parent identify karo, budget + country + intake confirm karo, counseling appointment book karo.",
        "disqualifiers": ["nahi chahiye", "done ho gaya", "pehle se admission"],
    },
    "home_loans": {
        "display": "Home Loans & LAP (DSA)",
        "pre_call_fields": [
            {
                "key": "loan_type",
                "label": "Loan type (HL/LAP/BL)",
                "type": "select",
                "options": ["Home Loan", "LAP", "Business Loan", "Unknown"],
            },
            {
                "key": "loan_amount_lakh",
                "label": "Loan amount needed (₹L)",
                "type": "number",
                "required": False,
            },
            {"key": "property_city", "label": "Property city", "type": "text", "required": False},
            {
                "key": "employment_type",
                "label": "Salaried / Self-employed",
                "type": "select",
                "options": ["Salaried", "Self-employed", "Business", "Unknown"],
            },
        ],
        "collect_during": [
            {"key": "loan_amount", "question": "Kitna loan chahiye approximately?"},
            {
                "key": "property_type",
                "question": "Property ready-possession hai ya under-construction?",
            },
            {"key": "monthly_income", "question": "Monthly income approximate — 50k se upar hai?"},
            {"key": "existing_emi", "question": "Koi existing EMI chal rahi hai kya?"},
        ],
        "script_context": "DSA/loan agent ke liye call — loan requirement confirm karo, property detail lelo, eligibility check ke liye callback book karo.",
        "disqualifiers": ["pehle se liya", "nahi chahiye abhi", "wrong number"],
    },
    "solar_commercial": {
        "display": "Solar Energy (Commercial B2B)",
        "pre_call_fields": [
            {
                "key": "property_type",
                "label": "Property type",
                "type": "select",
                "options": ["Factory", "Warehouse", "Office", "Showroom", "Farm", "Other"],
            },
            {
                "key": "monthly_bill_inr",
                "label": "Monthly electricity bill (₹)",
                "type": "number",
                "required": False,
            },
            {
                "key": "roof_area_sqft",
                "label": "Roof area (sq ft approx)",
                "type": "number",
                "required": False,
            },
            {"key": "city", "label": "City", "type": "text", "required": False},
        ],
        "collect_during": [
            {
                "key": "monthly_bill",
                "question": "Monthly electricity bill kitna aata hai approximately?",
            },
            {"key": "roof_owned", "question": "Roof aapka khud ka hai ya leased?"},
            {"key": "sanctioned_load", "question": "Sanctioned load kitna hai — 10 kW se upar?"},
            {
                "key": "decision_maker",
                "question": "Aap hi decision lenge ya koi aur partner bhi hain?",
            },
        ],
        "script_context": "Commercial solar B2B call — factory/warehouse owner, bill savings angle, subsidy angle, site visit book karo.",
        "disqualifiers": ["rented jagah", "already installed", "nahi chahiye"],
    },
    "insurance": {
        "display": "Insurance (Life & Health)",
        "pre_call_fields": [
            {
                "key": "insurance_type",
                "label": "Insurance type",
                "type": "select",
                "options": ["Life", "Health", "Term", "ULIP", "Vehicle", "Unknown"],
            },
            {"key": "age", "label": "Age (approx)", "type": "number", "required": False},
            {
                "key": "sum_assured_lakh",
                "label": "Coverage needed (₹L)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {"key": "coverage_type", "question": "Life insurance chahiye ya health?"},
            {"key": "current_coverage", "question": "Abhi koi policy hai? Kitne ka coverage hai?"},
            {"key": "annual_premium", "question": "Annual premium budget kya hai?"},
            {"key": "dependents", "question": "Family members kitne hain — spouse, children?"},
        ],
        "script_context": "Insurance lead call — existing coverage gap samjhao, tax benefit angle, free review offer karo, policy recommendation appointment book karo.",
        "disqualifiers": ["agent hun khud", "nahi chahiye", "already hai sab"],
    },
    "coaching": {
        "display": "Coaching & Test Prep",
        "pre_call_fields": [
            {
                "key": "exam_target",
                "label": "Target exam (JEE/NEET/UPSC/etc)",
                "type": "text",
                "required": False,
            },
            {
                "key": "student_class",
                "label": "Student class/year",
                "type": "text",
                "required": False,
            },
            {"key": "city", "label": "City", "type": "text", "required": False},
        ],
        "collect_during": [
            {"key": "exam_target", "question": "Kaunsi exam ki taiyari kar rahe ho?"},
            {"key": "current_status", "question": "Pehle attempt hai ya repeat?"},
            {"key": "weak_subjects", "question": "Kaunse subject me help chahiye?"},
            {"key": "start_date", "question": "Coaching kab se join karna hai?"},
        ],
        "script_context": "Coaching institute call — exam + class confirm karo, demo class / counseling book karo, scholarship angle.",
        "disqualifiers": ["already joined", "nahi deni exam", "done ho gaya"],
    },
    "hospital_appointments": {
        "display": "Hospital / Clinic Appointments",
        "pre_call_fields": [
            {
                "key": "speciality",
                "label": "Department/Speciality",
                "type": "text",
                "required": False,
            },
            {"key": "patient_name", "label": "Patient name", "type": "text", "required": False},
            {"key": "preferred_date", "label": "Preferred date", "type": "text", "required": False},
        ],
        "collect_during": [
            {
                "key": "speciality",
                "question": "Kaunse doctor ya department se appointment chahiye?",
            },
            {
                "key": "symptom_brief",
                "question": "Kya problem hai briefly — doctor ko batane ke liye?",
            },
            {"key": "preferred_time", "question": "Subah ya shaam — kab aana comfortable hai?"},
            {"key": "first_visit", "question": "Pehli baar aa rahe ho ya follow-up hai?"},
        ],
        "script_context": "Hospital appointment booking call — speciality confirm karo, slot offer karo, confirmation SMS send karo.",
        "disqualifiers": ["already booked", "emergency nahi", "wrong number"],
    },
    # ---- A-TIER ----
    "dental_implants": {
        "display": "Dental / Implant Clinics",
        "pre_call_fields": [
            {
                "key": "treatment_type",
                "label": "Treatment type",
                "type": "select",
                "options": ["Implant", "Braces", "Whitening", "RCT", "General", "Unknown"],
            },
            {
                "key": "teeth_count",
                "label": "Missing teeth (if implant)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {
                "key": "treatment_needed",
                "question": "Kaunsa treatment chahiye — implant, braces, ya general checkup?",
            },
            {"key": "pain_level", "question": "Abhi koi pain hai ya scheduled checkup hai?"},
            {"key": "last_visit", "question": "Last dental visit kab tha?"},
            {"key": "budget_ok", "question": "Treatment budget 15,000 se upar comfortable hai?"},
        ],
        "script_context": "Dental clinic call — treatment type identify karo, pain urgency note karo, free consultation book karo.",
        "disqualifiers": ["already done", "wrong number"],
    },
    "hair_transplant": {
        "display": "Hair Transplant Clinics",
        "pre_call_fields": [
            {
                "key": "hair_loss_stage",
                "label": "Hair loss stage (1-7)",
                "type": "select",
                "options": ["1-2 (early)", "3-4 (moderate)", "5-7 (advanced)", "Unknown"],
            },
            {
                "key": "age_range",
                "label": "Age range",
                "type": "select",
                "options": ["18-25", "26-35", "36-45", "46+", "Unknown"],
            },
        ],
        "collect_during": [
            {
                "key": "hair_loss_area",
                "question": "Konsa area zyada affected hai — crown, front, ya poora?",
            },
            {
                "key": "previous_treatment",
                "question": "Pehle koi treatment try kiya — minoxidil ya PRP?",
            },
            {
                "key": "budget_range",
                "question": "Budget 60,000 to 1,50,000 ke beech comfortable hai?",
            },
            {
                "key": "consultation_ok",
                "question": "Free consultation ke liye aa sakte ho next week?",
            },
        ],
        "script_context": "Hair transplant clinic call — hair loss stage assess karo, budget qualify karo, free consultation appointment book karo.",
        "disqualifiers": ["already done", "nahi chahiye", "wrong number"],
    },
    "ivf_clinics": {
        "display": "IVF / Fertility Clinics",
        "pre_call_fields": [
            {
                "key": "treatment_stage",
                "label": "Treatment stage",
                "type": "select",
                "options": ["First consultation", "Repeat IVF", "IUI", "Other", "Unknown"],
            },
            {
                "key": "age_female",
                "label": "Female partner age",
                "type": "number",
                "required": False,
            },
            {"key": "city", "label": "City", "type": "text", "required": False},
        ],
        "collect_during": [
            {"key": "trying_since", "question": "Kitne samay se try kar rahe ho?"},
            {"key": "prev_attempts", "question": "Pehle koi treatment hua hai — IUI ya IVF?"},
            {
                "key": "doctor_referral",
                "question": "Kisi doctor ne refer kiya hai ya khud research kar rahe ho?",
            },
            {"key": "city_preference", "question": "Kaunse city me treatment prefer karoge?"},
        ],
        "script_context": "IVF clinic call — sensitive call, empathetic tone rakho, treatment stage identify karo, free doctor consultation book karo.",
        "disqualifiers": ["pregnant hain already", "wrong number", "nahi chahiye"],
    },
    "immigration": {
        "display": "Immigration & Visa Consultants",
        "pre_call_fields": [
            {
                "key": "destination",
                "label": "Destination country",
                "type": "text",
                "required": False,
            },
            {
                "key": "visa_type",
                "label": "Visa type",
                "type": "select",
                "options": ["PR", "Work Permit", "Student", "Visitor", "Business", "Unknown"],
            },
            {
                "key": "education",
                "label": "Education level",
                "type": "select",
                "options": ["10th/12th", "Graduate", "Post-Graduate", "PhD", "Unknown"],
            },
        ],
        "collect_during": [
            {
                "key": "destination",
                "question": "Kaunse country me jaana hai — Canada, Australia, ya koi aur?",
            },
            {"key": "purpose", "question": "PR ke liye ja rahe ho ya work permit?"},
            {"key": "language_score", "question": "IELTS ya PTE score hai? Kitna?"},
            {"key": "budget_ok", "question": "Consulting fee 50,000 se upar comfortable hai?"},
        ],
        "script_context": "Immigration consultant call — destination + visa type confirm karo, eligibility assess karo, free assessment book karo.",
        "disqualifiers": ["already applied", "already migrated", "wrong number"],
    },
    "modular_kitchen": {
        "display": "Modular Kitchen & Interiors",
        "pre_call_fields": [
            {
                "key": "project_type",
                "label": "Project type",
                "type": "select",
                "options": [
                    "Modular Kitchen",
                    "Full Interior",
                    "Wardrobe",
                    "False Ceiling",
                    "Other",
                ],
            },
            {"key": "flat_size", "label": "Flat size (sq ft)", "type": "number", "required": False},
            {
                "key": "possession",
                "label": "Possession status",
                "type": "select",
                "options": ["Ready", "3 months", "6 months", "1 year+", "Unknown"],
            },
        ],
        "collect_during": [
            {"key": "project_scope", "question": "Sirf kitchen chahiye ya full home interior?"},
            {"key": "budget_range", "question": "Budget kya hai — 1.5 lakh se 3 lakh, ya upar?"},
            {"key": "possession_date", "question": "Possession kab ho raha hai?"},
            {
                "key": "site_visit_ok",
                "question": "Site visit ke liye kab comfortable ho aage week?",
            },
        ],
        "script_context": "Modular kitchen/interior design call — scope confirm karo, budget qualify karo, site visit schedule karo.",
        "disqualifiers": ["already done", "rented hai", "nahi chahiye"],
    },
    "finance_advisory": {
        "display": "Financial Advisory / Wealth Management",
        "pre_call_fields": [
            {
                "key": "advisory_type",
                "label": "Advisory type",
                "type": "select",
                "options": [
                    "Mutual Funds",
                    "Tax Planning",
                    "Portfolio Review",
                    "Retirement",
                    "Wealth Mgmt",
                    "Unknown",
                ],
            },
            {
                "key": "investment_amount",
                "label": "Investment amount (₹L)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {
                "key": "current_investments",
                "question": "Abhi kahan invest kiya hua hai — FD, MF, stocks?",
            },
            {
                "key": "investment_goal",
                "question": "Goal kya hai — retirement, child education, ya house?",
            },
            {
                "key": "risk_appetite",
                "question": "Risk lena comfortable hai ya safe returns prefer karte ho?",
            },
            {
                "key": "annual_income",
                "question": "Annual income approximately 10 lakh se upar hai?",
            },
        ],
        "script_context": "Financial advisor call — investment goal + risk profile identify karo, free portfolio review offer karo.",
        "disqualifiers": ["advisor hun khud", "nahi chahiye", "wrong number"],
    },
    "ca_legal": {
        "display": "CA / Accounting Firms",
        "pre_call_fields": [
            {
                "key": "service_needed",
                "label": "Service needed",
                "type": "select",
                "options": [
                    "ITR Filing",
                    "GST",
                    "Company Registration",
                    "Audit",
                    "Bookkeeping",
                    "Unknown",
                ],
            },
            {
                "key": "business_type",
                "label": "Business type",
                "type": "select",
                "options": ["Sole Proprietor", "Pvt Ltd", "Partnership", "Individual", "Unknown"],
            },
            {
                "key": "turnover_cr",
                "label": "Annual turnover (₹Cr)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {
                "key": "service_type",
                "question": "Kaunsi service chahiye — ITR, GST, ya company registration?",
            },
            {"key": "current_ca", "question": "Abhi koi CA hai? Kyun change karna hai?"},
            {"key": "filing_deadline", "question": "Koi urgent deadline hai — GST return ya ITR?"},
            {"key": "company_size", "question": "Kitne employees hain approximately?"},
        ],
        "script_context": "CA firm call — service type confirm karo, current pain point identify karo, free consultation offer karo.",
        "disqualifiers": ["CA hun khud", "nahi chahiye", "wrong number"],
    },
    "edtech_creators": {
        "display": "Edtech / Online Course Creators",
        "pre_call_fields": [
            {"key": "course_topic", "label": "Course topic", "type": "text", "required": False},
            {
                "key": "platform",
                "label": "Current platform",
                "type": "select",
                "options": ["Udemy", "Teachable", "Own website", "None", "Other"],
            },
            {
                "key": "student_count",
                "label": "Approx students",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {
                "key": "course_topic",
                "question": "Kaunsa subject padhate ho — technology, finance, ya kuch aur?",
            },
            {
                "key": "revenue_target",
                "question": "Monthly revenue target kya hai — 1 lakh se upar?",
            },
            {
                "key": "pain_point",
                "question": "Sabse bada challenge kya hai — leads, sales, ya content?",
            },
            {"key": "platform_used", "question": "Abhi kaunsa platform use karte ho?"},
        ],
        "script_context": "Edtech creator call — course + platform identify karo, lead generation pain point target karo, demo book karo.",
        "disqualifiers": ["nahi chahiye", "already sorted", "wrong number"],
    },
    # ---- B-TIER ----
    "hvac_commercial": {
        "display": "HVAC / Commercial AC",
        "pre_call_fields": [
            {
                "key": "facility_type",
                "label": "Facility type",
                "type": "select",
                "options": ["Office", "Hotel", "Hospital", "Factory", "Mall", "Other"],
            },
            {
                "key": "ton_estimate",
                "label": "Tonnage required (TR)",
                "type": "number",
                "required": False,
            },
            {
                "key": "project_stage",
                "label": "Project stage",
                "type": "select",
                "options": ["New installation", "Replacement", "Service contract", "Unknown"],
            },
        ],
        "collect_during": [
            {
                "key": "facility_size",
                "question": "Facility kitne area ki hai — 5,000 sq ft se upar?",
            },
            {"key": "project_timeline", "question": "Installation kab chahiye?"},
            {"key": "budget_range", "question": "Budget 5 lakh se upar hai?"},
            {"key": "decision_maker", "question": "Aap hi final decision lenge?"},
        ],
        "script_context": "Commercial HVAC call — facility type + size identify karo, project timeline qualify karo, site visit book karo.",
        "disqualifiers": ["residential hai", "nahi chahiye", "wrong number"],
    },
    "real_estate_commercial": {
        "display": "Commercial Real Estate",
        "pre_call_fields": [
            {
                "key": "property_type",
                "label": "Property type",
                "type": "select",
                "options": ["Office Space", "Shop", "Warehouse", "Plot", "Showroom", "Unknown"],
            },
            {"key": "budget_cr", "label": "Budget (₹Cr)", "type": "number", "required": False},
            {
                "key": "area_sqft",
                "label": "Area required (sq ft)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {"key": "purpose", "question": "Office ke liye chahiye ya investment?"},
            {"key": "location_pref", "question": "Kaunsa area prefer karte ho?"},
            {"key": "budget_range", "question": "Budget 50 lakh se upar hai?"},
            {"key": "timeline", "question": "Kab tak finalize karna hai?"},
        ],
        "script_context": "Commercial real estate call — purpose + budget qualify karo, location preference le, site tour schedule karo.",
        "disqualifiers": ["residential chahiye", "nahi chahiye", "wrong number"],
    },
    "cloud_kitchen": {
        "display": "Cloud Kitchen / Restaurant",
        "pre_call_fields": [
            {
                "key": "kitchen_type",
                "label": "Type",
                "type": "select",
                "options": ["Cloud Kitchen", "Restaurant", "QSR", "Catering", "Other"],
            },
            {"key": "cuisine", "label": "Cuisine type", "type": "text", "required": False},
            {
                "key": "monthly_orders",
                "label": "Monthly orders (approx)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {"key": "platform", "question": "Zomato/Swiggy pe already listed ho?"},
            {
                "key": "pain_point",
                "question": "Sabse bada problem — orders, delivery, ya marketing?",
            },
            {"key": "expansion_plan", "question": "New location open karne ka plan hai?"},
            {"key": "revenue_target", "question": "Monthly revenue target kya hai?"},
        ],
        "script_context": "Cloud kitchen call — platform + monthly orders identify karo, growth pain point target karo, demo call book karo.",
        "disqualifiers": ["band ho gaya", "wrong number", "nahi chahiye"],
    },
    "event_management": {
        "display": "Event Management",
        "pre_call_fields": [
            {
                "key": "event_type",
                "label": "Event type",
                "type": "select",
                "options": [
                    "Wedding",
                    "Corporate",
                    "Birthday",
                    "Exhibition",
                    "Conference",
                    "Other",
                ],
            },
            {"key": "budget_lakh", "label": "Budget (₹L)", "type": "number", "required": False},
            {
                "key": "event_date",
                "label": "Event date (approx)",
                "type": "text",
                "required": False,
            },
        ],
        "collect_during": [
            {"key": "event_size", "question": "Kitne guests expected hain?"},
            {"key": "venue_decided", "question": "Venue decide ho gaya hai ya wo bhi chahiye?"},
            {"key": "budget_range", "question": "Budget 2 lakh se upar hai?"},
            {"key": "timeline", "question": "Event kab hai — next 3 months me?"},
        ],
        "script_context": "Event management call — event type + date + budget identify karo, requirement details le, site visit/meeting book karo.",
        "disqualifiers": ["already booked", "nahi chahiye", "wrong number"],
    },
    "skin_dermatology": {
        "display": "Skin / Dermatology Clinics",
        "pre_call_fields": [
            {
                "key": "treatment_type",
                "label": "Treatment type",
                "type": "select",
                "options": [
                    "Acne/Scar",
                    "Laser",
                    "Anti-aging",
                    "Pigmentation",
                    "Hair Removal",
                    "General Checkup",
                    "Unknown",
                ],
            },
        ],
        "collect_during": [
            {"key": "main_concern", "question": "Kya concern hai — acne, dark spots, ya kuch aur?"},
            {"key": "prev_treatment", "question": "Pehle koi treatment liya hai iske liye?"},
            {"key": "budget_ok", "question": "Treatment budget 5,000 se upar comfortable hai?"},
            {"key": "consultation_ok", "question": "Free consultation ke liye kab aa sakte ho?"},
        ],
        "script_context": "Dermatology clinic call — skin concern identify karo, urgency note karo, free consultation book karo.",
        "disqualifiers": ["wrong number", "nahi chahiye"],
    },
    "ayurveda_wellness": {
        "display": "Ayurveda / Wellness Centers",
        "pre_call_fields": [
            {
                "key": "treatment_goal",
                "label": "Goal",
                "type": "select",
                "options": [
                    "Weight loss",
                    "Stress/Anxiety",
                    "Chronic condition",
                    "Detox",
                    "General wellness",
                    "Unknown",
                ],
            },
        ],
        "collect_during": [
            {
                "key": "health_concern",
                "question": "Kaunsi health problem ke liye treatment chahiye?",
            },
            {"key": "duration", "question": "Yeh problem kitne time se hai?"},
            {"key": "preferred_mode", "question": "Center pe aana prefer karte ho ya home visits?"},
            {"key": "budget_range", "question": "Monthly wellness budget 3,000 se upar hai?"},
        ],
        "script_context": "Ayurveda/wellness call — health concern identify karo, duration assess karo, free consultation ya trial session book karo.",
        "disqualifiers": ["wrong number", "nahi chahiye"],
    },
    "ecommerce_d2c": {
        "display": "E-commerce / D2C Brands",
        "pre_call_fields": [
            {
                "key": "product_category",
                "label": "Product category",
                "type": "text",
                "required": False,
            },
            {
                "key": "monthly_revenue",
                "label": "Monthly revenue (₹L)",
                "type": "number",
                "required": False,
            },
            {
                "key": "platform",
                "label": "Platform",
                "type": "select",
                "options": [
                    "Amazon",
                    "Flipkart",
                    "Own website",
                    "Instagram",
                    "Multiple",
                    "Unknown",
                ],
            },
        ],
        "collect_during": [
            {
                "key": "pain_point",
                "question": "Sabse bada challenge kya hai — traffic, conversion, ya returns?",
            },
            {"key": "ad_spend", "question": "Monthly ad spend kitna hai?"},
            {"key": "growth_target", "question": "Next 6 months ka revenue target kya hai?"},
            {"key": "team_size", "question": "Team kitni badi hai?"},
        ],
        "script_context": "E-commerce brand call — pain point identify karo, current metrics le, growth strategy call book karo.",
        "disqualifiers": ["band ho gaya", "nahi chahiye", "wrong number"],
    },
    "solar_residential": {
        "display": "Solar Energy (Residential)",
        "pre_call_fields": [
            {
                "key": "property_type",
                "label": "Property type",
                "type": "select",
                "options": ["Independent house", "Villa", "Apartment", "Unknown"],
            },
            {
                "key": "monthly_bill_inr",
                "label": "Monthly electricity bill (₹)",
                "type": "number",
                "required": False,
            },
            {"key": "city", "label": "City", "type": "text", "required": False},
        ],
        "collect_during": [
            {"key": "monthly_bill", "question": "Monthly bijli bill kitna aata hai?"},
            {"key": "roof_owned", "question": "Apna makan hai — roof use kar sakte hain?"},
            {"key": "kw_estimate", "question": "2 kW ya 5 kW system chahiye?"},
            {"key": "subsidy_aware", "question": "PM Surya Ghar subsidy ke baare me pata hai?"},
        ],
        "script_context": "Residential solar call — bill savings angle, PM Surya Ghar subsidy angle, site survey book karo.",
        "disqualifiers": ["already installed", "rented hai", "nahi chahiye"],
    },
    "travel_packages": {
        "display": "Travel & Tourism",
        "pre_call_fields": [
            {"key": "destination", "label": "Destination", "type": "text", "required": False},
            {
                "key": "travel_type",
                "label": "Travel type",
                "type": "select",
                "options": [
                    "Honeymoon",
                    "Family",
                    "Corporate",
                    "Adventure",
                    "Religious",
                    "Unknown",
                ],
            },
            {
                "key": "budget_lakh",
                "label": "Budget (₹L per person)",
                "type": "number",
                "required": False,
            },
        ],
        "collect_during": [
            {"key": "destination", "question": "Kahan jaana plan hai — domestic ya international?"},
            {"key": "travel_dates", "question": "Kab jaana plan hai approximately?"},
            {"key": "group_size", "question": "Kitne log hain?"},
            {"key": "budget_range", "question": "Per person budget 20,000 se upar hai?"},
        ],
        "script_context": "Travel agency call — destination + dates + group size qualify karo, personalized itinerary offer karo, booking call book karo.",
        "disqualifiers": ["already booked", "nahi chahiye", "wrong number"],
    },
    "upskilling": {
        "display": "Upskilling / Professional Courses",
        "pre_call_fields": [
            {
                "key": "course_type",
                "label": "Course type",
                "type": "select",
                "options": [
                    "Tech (Data/AI/Dev)",
                    "MBA/Management",
                    "Finance (CFA/CA)",
                    "Digital Marketing",
                    "Other",
                ],
            },
            {
                "key": "current_job",
                "label": "Currently employed?",
                "type": "select",
                "options": ["Yes", "No", "Fresher", "Unknown"],
            },
        ],
        "collect_during": [
            {
                "key": "goal",
                "question": "Course kyun karna hai — job change, promotion, ya skill upgrade?",
            },
            {"key": "current_role", "question": "Abhi kya kaam karte ho?"},
            {"key": "start_timeline", "question": "Kab se start karna hai?"},
            {"key": "budget_ok", "question": "Course fee 30,000 se upar comfortable hai?"},
        ],
        "script_context": "Upskilling institute call — career goal identify karo, current skill gap note karo, demo/counseling session book karo.",
        "disqualifiers": ["already enrolled", "nahi chahiye", "wrong number"],
    },
}
