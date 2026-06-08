"""
Top 25 Niches Configuration — research-finalized (June 2026).

Selection criteria (web research, see docs/Niche_Pricing_Research.md + Excel):
  (a) high ticket size, (b) phone-call-heavy buying journey in India,
  (c) proven willingness to pay for qualified leads (CPL/CPQL benchmarks),
  (d) clear B2B client + B2C/B2B end-customer extension for tier-2 campaigns.

Two-tier model:
  - Tier 1 (platform → B2B): hum in niches ke BUSINESSES ko client banate hain.
  - Tier 2 (client → end customers): client ka voice agent uske END CUSTOMERS
    ko call karta hai — `target_type` batata hai wo audience B2C hai ya B2B.

Pricing fields (INR, research-benchmarked):
  pricing_inr = {
    "qualified_lead": (min, max),   # per qualified lead delivered
    "appointment": (min, max),      # per appointment/site-visit/consult booked
    "monthly_starter": int,         # entry monthly plan (capped leads)
  }
Backward-compatible fields retained: name, keywords, avg_deal_value,
pitch_hook, qualification_questions.
"""

NICHES = {
    # ====================================================================== #
    # S-TIER — flagship niches: sell these first
    # ====================================================================== #
    "ai_marketing": {
        "name": "AI Marketing Services",
        "tier": "S",
        "category": "both",
        "content_focus": ["festival posters", "GBP optimization", "social posts", "reels"],
        "target_type": "b2b",
        "b2b_client": "local businesses needing marketing",
        "end_customer": "business owners",
        "keywords": ["local business marketing", "ai marketing services", "digital marketing for small business", "google business profile optimization"],
        "avg_deal_value": "₹36,000–1,44,000/yr",
        "avg_ticket_inr": "₹3–12K/mo subscription (₹36K–1.44L/yr LTV)",
        "pitch_hook": "posts, Google ranking, festival posters — plus an AI that calls every inquiry in 2 minutes; no Indian competitor bundles both",
        "pricing_inr": {"qualified_lead": (300, 1000), "appointment": (800, 2000), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi aap apni marketing kaise karte ho — khud, staff, ya agency?",
            "Google pe aapka business search karne par dikhta hai kya?",
            "Website ya Google se aayi inquiries ka follow-up kaun karta hai?",
        ],
    },
    "real_estate": {
        "name": "Real Estate (Resale & New Projects)",
        "tier": "S",
        "category": "both",
        "content_focus": ["property posts", "festival posters", "reels", "reviews"],
        "target_type": "b2c",
        "b2b_client": "Brokers, channel partners, builders' sales teams",
        "end_customer": "Property buyers/sellers (site-visit booking, budget/locality qualification)",
        "keywords": ["real estate agents", "property dealers", "real estate brokers", "channel partners real estate"],
        "avg_deal_value": "₹40,00,000+",
        "avg_ticket_inr": "₹40L–1Cr (brokerage 1–2%)",
        "pitch_hook": "every portal lead called in under 5 minutes — site visits booked while competitors are still dialing",
        "pricing_inr": {"qualified_lead": (800, 2500), "appointment": (3000, 7500), "monthly_starter": 15000},
        "qualification_questions": [
            "Are you actively buying leads from portals like 99acres or MagicBricks?",
            "How many site visits does your team complete per week?",
            "Do you have inventory in the ₹40L+ segment?",
        ],
    },
    "real_estate_luxury": {
        "name": "Luxury Real Estate",
        "tier": "S",
        "category": "both",
        "content_focus": ["premium listing posts", "reels", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Luxury brokers, premium project marketers",
        "end_customer": "HNI investors & buyers (₹2Cr+ properties)",
        "keywords": ["luxury real estate agents", "premium property dealers", "high end real estate brokers"],
        "avg_deal_value": "₹2,00,00,000+",
        "avg_ticket_inr": "₹2Cr+ (brokerage ₹2L+/deal)",
        "pitch_hook": "re-engage your cold database of HNI investors",
        "pricing_inr": {"qualified_lead": (3000, 6000), "appointment": (7500, 15000), "monthly_starter": 25000},
        "qualification_questions": [
            "Do you handle properties above 2 Cr?",
            "Are you currently looking for HNI investors?",
            "What is your current marketing budget for luxury listings?",
        ],
    },
    "studying_abroad": {
        "name": "Study Abroad Consultants",
        "tier": "S",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "Overseas education consultancies",
        "end_customer": "Students/parents (country, budget, intake qualification + counseling booking)",
        "keywords": ["study abroad consultants", "overseas education counsellors", "visa consultants"],
        "avg_deal_value": "₹2,00,000+",
        "avg_ticket_inr": "₹2–3L commission/enrolled student (10–15% of first-year tuition)",
        "pitch_hook": "every inquiry counselled within minutes — enrollments worth ₹2-3L commission each",
        "pricing_inr": {"qualified_lead": (1000, 2500), "appointment": (2000, 4000), "monthly_starter": 20000},
        "qualification_questions": [
            "Do you handle admissions for USA/UK/Canada?",
            "Are you looking for students with budget above 20L?",
            "Do you have university tie-ups?",
        ],
    },
    "home_loans": {
        "name": "Home Loans & LAP (DSA)",
        "tier": "S",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "Loan DSAs, mortgage brokers, fintech lending partners",
        "end_customer": "Home-loan seekers (eligibility, ticket size, balance-transfer qualification)",
        "keywords": ["home loan dsa", "loan agents", "mortgage brokers india", "loan against property agents"],
        "avg_deal_value": "₹25,00,000+",
        "avg_ticket_inr": "₹23–33L avg ticket (DSA payout 0.5–1.5%)",
        "pitch_hook": "your telecalling team replaced — eligibility-checked, doc-ready borrowers on your calendar",
        "pricing_inr": {"qualified_lead": (500, 1500), "appointment": (1500, 3000), "monthly_starter": 15000},
        "qualification_questions": [
            "Are you an active DSA with bank/NBFC tie-ups?",
            "What loan ticket sizes do you focus on?",
            "How many files do you log per month?",
        ],
    },
    "solar_residential": {
        "name": "Residential Rooftop Solar",
        "tier": "S",
        "category": "both",
        "content_focus": ["subsidy posts", "before-after reels", "offer posters"],
        "target_type": "b2c",
        "b2b_client": "Solar installers & EPC dealers (residential)",
        "end_customer": "Homeowners (roof ownership, bill size, subsidy interest → site-survey booking)",
        "keywords": ["solar installers residential", "rooftop solar dealers", "solar panel installation company"],
        "avg_deal_value": "₹1,50,000+",
        "avg_ticket_inr": "₹1.5–1.8L per 3kW install (PM Surya Ghar demand)",
        "pitch_hook": "subsidy-curious homeowners qualified for roof & bill size before your surveyor leaves the office",
        "pricing_inr": {"qualified_lead": (400, 1000), "appointment": (800, 1500), "monthly_starter": 12000},
        "qualification_questions": [
            "Do you install residential rooftop systems?",
            "Which cities/areas do you cover?",
            "How many site surveys can your team handle weekly?",
        ],
    },
    "solar_commercial": {
        "name": "Commercial Solar Installers",
        "tier": "S",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2b",
        "b2b_client": "Solar EPC companies (C&I segment)",
        "end_customer": "Factory/warehouse owners (roof suitability, load, capex appetite)",
        "keywords": ["commercial solar installers", "solar epc companies", "industrial solar solutions"],
        "avg_deal_value": "₹20,00,000+",
        "avg_ticket_inr": "₹20L+ per C&I project",
        "pitch_hook": "qualify factory owners for roof suitability before you visit",
        "pricing_inr": {"qualified_lead": (1500, 3000), "appointment": (3000, 6000), "monthly_starter": 20000},
        "qualification_questions": [
            "Do you handle commercial installations above 100kW?",
            "Are you looking for industrial leads?",
            "What is your installation capacity per month?",
        ],
    },
    "insurance": {
        "name": "Health & Term Insurance",
        "tier": "S",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "Insurance agencies, POSPs, broker teams",
        "end_customer": "Families/professionals (age, cover need, premium budget) — IRDAI/DND compliant",
        "keywords": ["insurance agents", "health insurance brokers", "term insurance advisors", "posp insurance"],
        "avg_deal_value": "₹25,000+",
        "avg_ticket_inr": "₹15–50K premium (35–40% first-year commission)",
        "pitch_hook": "renewal reminders + new-policy qualification on autopilot — the classic telesales niche without telecaller churn",
        "pricing_inr": {"qualified_lead": (300, 800), "appointment": (800, 1500), "monthly_starter": 10000},
        "qualification_questions": [
            "Are you an IRDAI-registered agent/broker/POSP?",
            "Which products do you focus on — health, term, motor?",
            "Do you have a renewal book to re-engage?",
        ],
    },
    "coaching": {
        "name": "Coaching Institutes (NEET/JEE/UPSC)",
        "tier": "S",
        "category": "marketing",
        "content_focus": ["result posters", "admission posts", "reels", "reviews"],
        "target_type": "b2c",
        "b2b_client": "Test-prep coaching institutes",
        "end_customer": "Parents/students (target exam, class, budget → counseling session booking)",
        "keywords": ["neet coaching institutes", "jee coaching centers", "upsc coaching", "test prep institutes"],
        "avg_deal_value": "₹1,50,000+",
        "avg_ticket_inr": "₹1.5–2.5L/year fees (₹58,000Cr industry)",
        "pitch_hook": "every admission inquiry counselled the same hour — seats filled before parents compare brochures",
        "pricing_inr": {"qualified_lead": (500, 1200), "appointment": (1000, 2000), "monthly_starter": 15000},
        "qualification_questions": [
            "Which exams do you coach for?",
            "What is your annual fee structure?",
            "Do you have admission counselors following up on inquiries today?",
        ],
    },

    # ====================================================================== #
    # A-TIER — strong economics, proven phone funnels
    # ====================================================================== #
    "interior_designers": {
        "name": "Interior Design Studios",
        "tier": "A",
        "category": "marketing",
        "content_focus": ["portfolio reels", "before-after posts", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Interior design firms & studios",
        "end_customer": "Homeowners (BHK, budget band, possession date → design-consult booking)",
        "keywords": ["interior designers", "home interior companies", "turnkey interior firms"],
        "avg_deal_value": "₹10,00,000+",
        "avg_ticket_inr": "₹4–20L per 2BHK project",
        "pitch_hook": "possession-ready homeowners qualified by budget before your designer picks up the phone",
        "pricing_inr": {"qualified_lead": (1000, 2500), "appointment": (2000, 4000), "monthly_starter": 15000},
        "qualification_questions": [
            "Do you handle turnkey residential projects?",
            "What is your minimum project budget?",
            "Which cities do you operate in?",
        ],
    },
    "modular_kitchen": {
        "name": "Modular Kitchen Manufacturers",
        "tier": "A",
        "category": "both",
        "content_focus": ["catalog posters", "before-after reels", "offers"],
        "target_type": "b2c",
        "b2b_client": "Modular kitchen brands & showrooms",
        "end_customer": "Homeowners (kitchen size, budget, timeline → showroom/site visit)",
        "keywords": ["modular kitchen manufacturers", "luxury kitchen showrooms", "italian kitchen dealers"],
        "avg_deal_value": "₹2,00,000+",
        "avg_ticket_inr": "₹1.2–6.5L per kitchen",
        "pitch_hook": "showroom visits from budget-qualified homeowners, not window shoppers",
        "pricing_inr": {"qualified_lead": (600, 1500), "appointment": (1200, 2500), "monthly_starter": 12000},
        "qualification_questions": [
            "Do you manufacture in-house or trade?",
            "Are you looking for direct homeowner leads?",
            "Do you deal in premium German/Italian fittings?",
        ],
    },
    "dental_implants": {
        "name": "Dental Clinics (Implants/Aligners)",
        "tier": "A",
        "category": "marketing",
        "content_focus": ["before-after posts", "health-day posts", "reviews", "GBP optimization"],
        "target_type": "b2c",
        "b2b_client": "Dental clinics & chains",
        "end_customer": "Patients (treatment need, budget → appointment booking + reminders)",
        "keywords": ["dental implant clinics", "cosmetic dentistry", "premium dental clinic"],
        "avg_deal_value": "₹50,000+",
        "avg_ticket_inr": "₹20–50K/tooth, full-mouth ₹3–8L",
        "pitch_hook": "fill your empty chair slots with high-value implant patients",
        "pricing_inr": {"qualified_lead": (500, 1500), "appointment": (1000, 2200), "monthly_starter": 12000},
        "qualification_questions": [
            "Do you offer dental implants?",
            "Are you looking to increase high-ticket patient footfall?",
            "Do you have a dedicated sales team for follow-ups?",
        ],
    },
    "hair_transplant": {
        "name": "Hair Transplant Clinics",
        "tier": "A",
        "category": "both",
        "content_focus": ["before-after reels", "reviews", "offer posts"],
        "target_type": "b2c",
        "b2b_client": "Hair transplant & aesthetics clinics",
        "end_customer": "Prospects (grade, budget, city → consult booking; market CPQL ~₹4,100)",
        "keywords": ["hair transplant clinics", "hair restoration centers", "aesthetics clinics"],
        "avg_deal_value": "₹1,50,000+",
        "avg_ticket_inr": "₹1–3.5L per procedure",
        "pitch_hook": "consults booked at half the ₹4,000+ cost-per-qualified-lead you pay ads today",
        "pricing_inr": {"qualified_lead": (1200, 2500), "appointment": (2000, 4000), "monthly_starter": 15000},
        "qualification_questions": [
            "How many consults does your counselor team handle daily?",
            "What is your average procedure value?",
            "Are you running Google/Meta ads currently?",
        ],
    },
    "ivf_clinics": {
        "name": "IVF & Fertility Clinics",
        "tier": "A",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "IVF & fertility centers",
        "end_customer": "Couples (empathetic intake, history, budget → doctor consult booking)",
        "keywords": ["ivf centers", "fertility clinics", "ivf hospitals"],
        "avg_deal_value": "₹1,50,000+",
        "avg_ticket_inr": "₹1–2.5L per cycle",
        "pitch_hook": "compassionate 24/7 intake — every inquiry answered, qualified and booked with a counselor",
        "pricing_inr": {"qualified_lead": (800, 2200), "appointment": (1800, 3500), "monthly_starter": 15000},
        "qualification_questions": [
            "How many new patient inquiries do you get monthly?",
            "Do you have counselors for first-call intake?",
            "Which cities are your centers in?",
        ],
    },
    "immigration": {
        "name": "Immigration & PR Consultants",
        "tier": "A",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "Immigration/PR consultancies",
        "end_customer": "Aspirants (eligibility points-check, country, budget → consult booking)",
        "keywords": ["immigration consultants", "canada pr consultants", "visa services australia"],
        "avg_deal_value": "₹75,000+",
        "avg_ticket_inr": "₹50K–1.25L per case",
        "pitch_hook": "eligibility-scored PR aspirants on your counselors' calendars every morning",
        "pricing_inr": {"qualified_lead": (800, 2000), "appointment": (1500, 3000), "monthly_starter": 15000},
        "qualification_questions": [
            "Which countries do you process — Canada, Australia, UK?",
            "Are you ICCRC/MARA registered or partnered?",
            "How many cases do you file monthly?",
        ],
    },
    "wedding_venues": {
        "name": "Wedding Venues & Banquets",
        "tier": "A",
        "category": "both",
        "content_focus": ["venue reels", "festival posters", "reviews"],
        "target_type": "both",
        "b2b_client": "Venues, banquet halls, resorts",
        "end_customer": "Couples/families (date, guests, budget → venue visit) + corporate event planners",
        "keywords": ["luxury wedding venues", "5 star banquet halls", "destination wedding resorts"],
        "avg_deal_value": "₹10,00,000+",
        "avg_ticket_inr": "₹2–25L/booking (avg Indian wedding ₹39.5L)",
        "pitch_hook": "date-and-budget-matched venue visits — calendars filled for the season before rivals reply",
        "pricing_inr": {"qualified_lead": (500, 1500), "appointment": (800, 2000), "monthly_starter": 12000},
        "qualification_questions": [
            "What is your guest capacity?",
            "Are you looking for corporate event bookings as well?",
            "Do you have available dates for the upcoming wedding season?",
        ],
    },
    "used_cars": {
        "name": "Used Car Dealers",
        "tier": "A",
        "category": "both",
        "content_focus": ["new-arrival posts", "offer posters", "reels"],
        "target_type": "b2c",
        "b2b_client": "Used-car dealerships & multi-brand outlets",
        "end_customer": "Buyers (budget, model, exchange → test-drive booking; sellers for procurement)",
        "keywords": ["used car dealers", "pre owned car showrooms", "second hand car dealers"],
        "avg_deal_value": "₹4,00,000+",
        "avg_ticket_inr": "₹3–5L core segment (market $36B→$83B)",
        "pitch_hook": "test drives booked from portal leads in minutes — and trade-in sellers qualified for procurement",
        "pricing_inr": {"qualified_lead": (300, 800), "appointment": (400, 800), "monthly_starter": 10000},
        "qualification_questions": [
            "How many cars do you retail monthly?",
            "Do you buy leads from CarWale/Cars24/OLX today?",
            "Do you also procure via trade-ins?",
        ],
    },
    "upskilling": {
        "name": "Upskilling & EdTech Programs",
        "tier": "A",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "EdTech companies, certification institutes",
        "end_customer": "Working professionals (career goal, budget, EMI eligibility → counselor call)",
        "keywords": ["edtech companies", "professional certification institutes", "online course providers"],
        "avg_deal_value": "₹1,00,000+",
        "avg_ticket_inr": "₹50K–3L per program",
        "pitch_hook": "the BYJU's-style telecalling engine — without the 200-person telecalling floor",
        "pricing_inr": {"qualified_lead": (300, 800), "appointment": (800, 1500), "monthly_starter": 10000},
        "qualification_questions": [
            "What programs do you sell and at what ticket size?",
            "Do you have an inside-sales team today?",
            "What is your current cost per enrollment?",
        ],
    },
    "recruitment": {
        "name": "Recruitment & Staffing Agencies",
        "tier": "A",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "both",
        "b2b_client": "Recruitment/staffing firms",
        "end_customer": "Candidates (screening at scale) + employer mandates (BD calls)",
        "keywords": ["recruitment agencies", "staffing companies", "it recruitment agencies", "headhunters"],
        "avg_deal_value": "₹1,00,000+",
        "avg_ticket_inr": "8.33–16.67% of CTC ≈ ₹50K–2L per placement",
        "pitch_hook": "screen 200 candidates a day and qualify new employer mandates — one agent, both sides",
        "pricing_inr": {"qualified_lead": (300, 800), "appointment": (1500, 3000), "monthly_starter": 15000},
        "qualification_questions": [
            "Do you do permanent hiring, staffing, or both?",
            "How many open mandates are you working?",
            "What volumes of candidate screening do you do weekly?",
        ],
    },

    # ====================================================================== #
    # B-TIER — solid volume/strategic plays
    # ====================================================================== #
    "hvac_commercial": {
        "name": "Commercial HVAC",
        "tier": "B",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2b",
        "b2b_client": "HVAC contractors & AMC providers",
        "end_customer": "IT parks, malls, offices (AMC renewals, retrofit projects)",
        "keywords": ["hvac contractors commercial", "central ac installation", "industrial cooling solutions"],
        "avg_deal_value": "₹5,00,000+",
        "avg_ticket_inr": "₹5L+ projects; AMC recurring",
        "pitch_hook": "secure high-value AMC contracts with IT parks",
        "pricing_inr": {"qualified_lead": (1500, 3000), "appointment": (3000, 5000), "monthly_starter": 15000},
        "qualification_questions": [
            "Do you take AMC contracts for IT parks/malls?",
            "What is your minimum project size?",
            "Are you looking for more B2B contracts?",
        ],
    },
    "b2b_suppliers": {
        "name": "Manufacturing & B2B Suppliers",
        "tier": "B",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2b",
        "b2b_client": "Manufacturers/wholesalers on IndiaMART/TradeIndia",
        "end_customer": "Business buyers (RFQ follow-up in minutes — speed wins the order)",
        "keywords": ["manufacturers india", "industrial suppliers", "wholesale suppliers b2b"],
        "avg_deal_value": "₹2,00,000+",
        "avg_ticket_inr": "₹50K–50L orders (IndiaMART BuyLead ₹16–24 raw)",
        "pitch_hook": "every IndiaMART RFQ called back in 5 minutes — before the other 6 suppliers wake up",
        "pricing_inr": {"qualified_lead": (150, 400), "appointment": (500, 1200), "monthly_starter": 8000},
        "qualification_questions": [
            "Are you buying BuyLeads on IndiaMART today?",
            "What is your average order value?",
            "Who follows up your RFQs currently?",
        ],
    },
    "travel_packages": {
        "name": "International Travel Packages",
        "tier": "B",
        "category": "both",
        "content_focus": ["package posters", "destination reels", "offers"],
        "target_type": "b2c",
        "b2b_client": "Travel agencies & tour operators",
        "end_customer": "Families/couples (destination, dates, budget → itinerary consult)",
        "keywords": ["travel agencies international packages", "tour operators", "holiday package companies"],
        "avg_deal_value": "₹3,00,000+",
        "avg_ticket_inr": "₹2.9–3.2L per international trip (couple)",
        "pitch_hook": "itinerary-ready travellers with dates and budgets locked — not brochure collectors",
        "pricing_inr": {"qualified_lead": (400, 1000), "appointment": (800, 1500), "monthly_starter": 10000},
        "qualification_questions": [
            "Which destinations do you specialize in?",
            "What is your average package value?",
            "Do you handle visas in-house?",
        ],
    },
    "packers_movers": {
        "name": "Packers & Movers",
        "tier": "B",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2c",
        "b2b_client": "Relocation companies",
        "end_customer": "Households/offices (move date, inventory size → instant quote callback)",
        "keywords": ["packers and movers", "relocation services", "household shifting services"],
        "avg_deal_value": "₹30,000+",
        "avg_ticket_inr": "₹11–55K intercity moves",
        "pitch_hook": "fastest quote wins the move — your agent calls back in 60 seconds, day or night",
        "pricing_inr": {"qualified_lead": (200, 500), "appointment": (400, 800), "monthly_starter": 8000},
        "qualification_questions": [
            "Which routes/cities do you cover?",
            "How many moves do you handle monthly?",
            "Who answers your inquiry calls after hours?",
        ],
    },
    "hotels_mice": {
        "name": "Hotels & Banquets (Corporate/MICE)",
        "tier": "B",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2b",
        "b2b_client": "Hotels, resorts, convention centers",
        "end_customer": "Corporate event planners, HR/admin teams (event size, dates, budget)",
        "keywords": ["hotels corporate events", "convention centers", "mice venues", "conference halls"],
        "avg_deal_value": "₹5,00,000+",
        "avg_ticket_inr": "MICE market $37.75B; corporate events high-value",
        "pitch_hook": "banquet inquiries qualified for date, size and budget — sales team only talks to real events",
        "pricing_inr": {"qualified_lead": (1000, 2500), "appointment": (2000, 4000), "monthly_starter": 15000},
        "qualification_questions": [
            "What is your banquet/hall capacity?",
            "Do you target corporate MICE business?",
            "Who handles inbound event inquiries today?",
        ],
    },
    "digital_marketing": {
        "name": "Digital Marketing Agencies",
        "tier": "B",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2b",
        "b2b_client": "Agencies (also white-label channel partners for our platform)",
        "end_customer": "SMB owners needing marketing (audit-call booking)",
        "keywords": ["digital marketing agency", "seo company", "social media marketing agency"],
        "avg_deal_value": "₹50,000/mo",
        "avg_ticket_inr": "₹15–50K/mo retainers",
        "pitch_hook": "white-label our voice agents — sell lead-gen calling to your clients under your brand",
        "pricing_inr": {"qualified_lead": (800, 2000), "appointment": (1500, 3000), "monthly_starter": 12000},
        "qualification_questions": [
            "Are you accepting new white-label partners?",
            "What is your minimum retainer?",
            "Do you specialize in any specific industry?",
        ],
    },
    "ca_legal": {
        "name": "CA & Legal Services",
        "tier": "B",
        "category": "leadgen",
        "content_focus": ["offer posts", "lead forms"],
        "target_type": "b2b",
        "b2b_client": "CA firms, compliance/legal service providers",
        "end_customer": "SMBs/startups (GST, ROC, IP, compliance needs → consult booking)",
        "keywords": ["ca firms", "chartered accountants", "compliance services", "corporate law firms"],
        "avg_deal_value": "₹50,000+",
        "avg_ticket_inr": "₹10–50K recurring engagements",
        "pitch_hook": "compliance-season pipelines filled — qualified SMBs booked while rivals rely on referrals",
        "pricing_inr": {"qualified_lead": (600, 1500), "appointment": (1200, 2500), "monthly_starter": 10000},
        "qualification_questions": [
            "Which services do you focus on — GST, ROC, audit, IP?",
            "Do you serve startups/SMBs?",
            "What is your typical engagement value?",
        ],
    },

    # ====================================================================== #
    # MARKETING NICHES — local-business categories jinhe hum AI-marketing
    # (posts / GBP / posters / festivals / reviews / reels) bechte hain.
    # category="marketing"; monthly_starter ₹2,999 retainer; pricing modest.
    # ====================================================================== #
    "restaurant_cafe": {
        "name": "Restaurant / Cafe",
        "tier": "S",
        "category": "marketing",
        "content_focus": ["reels", "menu posters", "reviews", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Restaurants, cafes, cloud kitchens, food joints",
        "end_customer": "Local foodies & families (footfall + online orders)",
        "keywords": ["restaurant", "cafe", "cloud kitchen", "food joint", "dhaba"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "roz ki dish reels, menu posters aur festival offers — Insta+Google pe aapka restaurant chamke, footfall badhe",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi aap restaurant ki marketing kaise karte ho — khud post karte ho ya koi karta hai?",
            "Instagram aur Google pe roz naye photos/reels daalte ho kya?",
            "Festival ya naye offer ke posters kaun banata hai?",
        ],
    },
    "jewellery_store": {
        "name": "Jewellery Store",
        "tier": "S",
        "category": "marketing",
        "content_focus": ["festival posters", "offer creatives", "collection posts", "reels"],
        "target_type": "b2c",
        "b2b_client": "Jewellery showrooms & retail stores",
        "end_customer": "Local buyers (festival/wedding jewellery shoppers)",
        "keywords": ["jewellery store", "jeweller", "gold showroom", "diamond jewellery"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "Dhanteras-Diwali-shaadi season ke designer posters aur offer creatives — har tyohaar pe aapka store sabse aage dikhe",
        "pricing_inr": {"qualified_lead": (150, 400), "appointment": (200, 500), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi jewellery store ki marketing kaise hoti hai — khud ya koi designer?",
            "Festival aur shaadi season pe offer posters kaun banata hai?",
            "Instagram pe nayi collection regularly daalte ho kya?",
        ],
    },
    "salon_spa": {
        "name": "Salon / Spa / Beauty",
        "tier": "S",
        "category": "marketing",
        "content_focus": ["before-after reels", "offers", "reviews", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Salons, spas, beauty & wellness studios",
        "end_customer": "Local customers (appointments + walk-ins)",
        "keywords": ["salon", "spa", "beauty parlour", "unisex salon", "wellness studio"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "before-after reels, monthly offers aur Google reviews — naye customers khud appointment book karein",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi salon ki marketing kaise karte ho — Insta khud chalate ho ya koi?",
            "Before-after photos ya reels banate ho customers ke liye?",
            "Google pe reviews maangne ka koi tarika hai aapke paas?",
        ],
    },
    "boutique_fashion": {
        "name": "Boutique / Clothing Store",
        "tier": "S",
        "category": "marketing",
        "content_focus": ["collection posts", "reels", "offer posters", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Boutiques, clothing & garment stores",
        "end_customer": "Local fashion shoppers (footfall + WhatsApp orders)",
        "keywords": ["boutique", "clothing store", "garment shop", "fashion store", "saree shop"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "nayi collection ke reels aur festival offer posters — Insta+WhatsApp pe customers daily naye design dekhein",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi boutique ki marketing kaise hoti hai — khud post karte ho?",
            "Nayi collection aane par Instagram/WhatsApp pe daalte ho kya?",
            "Festival offer ke posters kaun banata hai?",
        ],
    },
    "gym_fitness": {
        "name": "Gym / Fitness / Yoga",
        "tier": "A",
        "category": "marketing",
        "content_focus": ["transformation reels", "offers", "reviews"],
        "target_type": "b2c",
        "b2b_client": "Gyms, fitness centers, yoga & Zumba studios",
        "end_customer": "Local members (new joinings + renewals)",
        "keywords": ["gym", "fitness center", "yoga studio", "zumba", "crossfit"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "member transformation reels aur New-Year/Jan offers — naye joinings aapke gym me khud aayein",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi gym ki marketing kaise karte ho — Insta khud chalate ho?",
            "Members ke transformation/results post karte ho kya?",
            "Naye saal ya season offer ke posters kaun banata hai?",
        ],
    },
    "bakery_sweets": {
        "name": "Bakery / Sweets / Mithai",
        "tier": "A",
        "category": "marketing",
        "content_focus": ["festival posters", "product posts", "reels", "offers"],
        "target_type": "b2c",
        "b2b_client": "Bakeries, sweet shops, mithai & cake stores",
        "end_customer": "Local buyers (festival/occasion orders + footfall)",
        "keywords": ["bakery", "sweet shop", "mithai", "cake shop", "confectionery"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "Diwali-Raksha Bandhan ke mithai posters aur cake reels — har festival pe aapke orders badhein",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi bakery/sweet shop ki marketing kaise hoti hai?",
            "Festival pe special items ke posters kaun banata hai?",
            "Instagram pe naye cakes/sweets ke photos daalte ho kya?",
        ],
    },
    "mobile_electronics": {
        "name": "Mobile / Electronics Shop",
        "tier": "A",
        "category": "marketing",
        "content_focus": ["offer posters", "new-arrival posts", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Mobile & electronics retail shops",
        "end_customer": "Local buyers (footfall + enquiry calls)",
        "keywords": ["mobile shop", "electronics store", "mobile retailer", "gadget shop"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "naye launch aur EMI/exchange offer ke posters — festival sale pe aapki shop sabse aage dikhe",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi mobile/electronics shop ki marketing kaise karte ho?",
            "Naye phone launch ya offer ke posters kaun banata hai?",
            "Google aur Instagram pe aapki shop dikhti hai kya?",
        ],
    },
    "hotel_resort": {
        "name": "Hotel / Resort / Banquet",
        "tier": "A",
        "category": "marketing",
        "content_focus": ["venue posters", "festival posters", "reels", "reviews"],
        "target_type": "b2c",
        "b2b_client": "Hotels, resorts, banquet halls, lodges",
        "end_customer": "Local guests, event/family bookings",
        "keywords": ["hotel", "resort", "banquet hall", "lodge", "guest house"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "venue reels, festival packages aur Google reviews — bookings aur enquiries direct aapke paas aayein",
        "pricing_inr": {"qualified_lead": (150, 400), "appointment": (200, 500), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi hotel/resort ki marketing kaise hoti hai — khud ya koi agency?",
            "Festival ya season package ke posters kaun banata hai?",
            "Google aur Insta pe property ke photos/reels daalte ho kya?",
        ],
    },
    "automobile_service": {
        "name": "Automobile / Car Service",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["service-offer posters", "festival posters", "reviews"],
        "target_type": "b2c",
        "b2b_client": "Car/bike service centers, garages, detailing studios",
        "end_customer": "Local vehicle owners (service bookings + walk-ins)",
        "keywords": ["car service", "garage", "auto repair", "bike service", "car detailing"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "service-offer aur seasonal-check posters — Google pe rank karke nazdeeki gaadi-walon ko laaye",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi service center ki marketing kaise karte ho?",
            "Google pe aapka garage search karne par dikhta hai kya?",
            "Service offer ke posters kaun banata hai?",
        ],
    },
    "photography_studio": {
        "name": "Photography / Wedding Studio",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["portfolio reels", "festival posters", "reviews"],
        "target_type": "b2c",
        "b2b_client": "Photography & wedding studios, photographers",
        "end_customer": "Couples & families (shoots, wedding bookings)",
        "keywords": ["photography studio", "wedding photographer", "photo studio", "candid photography"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "aapke best shoots ke portfolio reels — Insta pe dikhe to wedding aur event bookings khud aayein",
        "pricing_inr": {"qualified_lead": (150, 400), "appointment": (200, 500), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi studio ki marketing kaise hoti hai — khud Insta chalate ho?",
            "Apne best shoots ke reels banate ho kya?",
            "Wedding season ke offer posters kaun banata hai?",
        ],
    },
    "pharmacy_medical": {
        "name": "Pharmacy / Medical Store",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["GBP optimization", "health-day posts", "offers"],
        "target_type": "b2c",
        "b2b_client": "Pharmacies, medical & chemist stores",
        "end_customer": "Local customers (footfall + home-delivery orders)",
        "keywords": ["pharmacy", "medical store", "chemist", "medical shop", "drug store"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "Google Business Profile + health-day posts — nazdeeki log aapki dukaan dhoondh ke pahunchein aur delivery maangein",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Google pe aapka medical store search karne par dikhta hai kya?",
            "Home delivery offer karte ho — log ko pata hai kya?",
            "Abhi koi WhatsApp/Insta pe marketing karta hai?",
        ],
    },
    "furniture_decor": {
        "name": "Furniture / Home Decor",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["catalog posters", "offers", "reels", "festival posters"],
        "target_type": "b2c",
        "b2b_client": "Furniture showrooms, home decor & furnishing stores",
        "end_customer": "Homeowners (showroom footfall + enquiries)",
        "keywords": ["furniture store", "home decor", "furnishing shop", "sofa shop", "furniture showroom"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "product catalog posters aur festival offers — naye design Insta+WhatsApp pe dikhein, footfall badhe",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi furniture showroom ki marketing kaise karte ho?",
            "Naye products ke photos/catalog Insta pe daalte ho kya?",
            "Festival offer ke posters kaun banata hai?",
        ],
    },
    "kirana_supermarket": {
        "name": "Kirana / Supermarket",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["WhatsApp offers", "festival posts", "offer posters"],
        "target_type": "b2c",
        "b2b_client": "Kirana stores, supermarkets, grocery shops",
        "end_customer": "Local households (repeat footfall + WhatsApp orders)",
        "keywords": ["kirana store", "supermarket", "grocery shop", "general store", "provision store"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "weekly WhatsApp offers aur festival posters — mohalle ke customers baar-baar aapki dukaan pe aayein",
        "pricing_inr": {"qualified_lead": (80, 250), "appointment": (120, 350), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi customers ko offers kaise batate ho — WhatsApp pe ya nahi?",
            "Festival ya monthly offer ke posters kaun banata hai?",
            "Google pe aapki dukaan dikhti hai kya?",
        ],
    },
    "travel_agency": {
        "name": "Travel Agency / Tours",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["package posters", "offers", "destination reels"],
        "target_type": "b2c",
        "b2b_client": "Travel agencies, tour & holiday operators",
        "end_customer": "Local travellers & families (package enquiries)",
        "keywords": ["travel agency", "tour operator", "holiday packages", "tour and travels", "ticketing agent"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "season package posters aur destination reels — Insta+WhatsApp pe travellers khud enquiry karein",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi travel agency ki marketing kaise hoti hai?",
            "Package ya offer ke posters kaun banata hai?",
            "Instagram pe destinations ke reels/photos daalte ho kya?",
        ],
    },
    "gift_stationery": {
        "name": "Gift / Stationery Shop",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["festival posters", "offer posters", "product posts"],
        "target_type": "b2c",
        "b2b_client": "Gift shops, stationery & novelty stores",
        "end_customer": "Local buyers (occasion + festival footfall)",
        "keywords": ["gift shop", "stationery shop", "gift store", "novelty store", "card shop"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "Rakhi-Diwali-Valentine ke gift posters aur offers — har occasion pe customers aapki shop yaad rakhein",
        "pricing_inr": {"qualified_lead": (80, 250), "appointment": (120, 350), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi gift/stationery shop ki marketing kaise karte ho?",
            "Festival aur occasion ke posters kaun banata hai?",
            "Instagram/WhatsApp pe naye gift items daalte ho kya?",
        ],
    },
    "hardware_paint": {
        "name": "Hardware / Paint / Electrical",
        "tier": "B",
        "category": "marketing",
        "content_focus": ["offer posters", "festival posters", "product posts"],
        "target_type": "b2c",
        "b2b_client": "Hardware, paint & electrical supply shops",
        "end_customer": "Homeowners, contractors & local trade (footfall + enquiries)",
        "keywords": ["hardware shop", "paint shop", "electrical store", "sanitary shop", "building material"],
        "avg_deal_value": "₹35,988/yr",
        "avg_ticket_inr": "₹2,999/mo retainer (₹36K/yr LTV)",
        "pitch_hook": "offer aur festival posters + Google listing — contractors aur ghar-walon ko aapki dukaan aasani se mile",
        "pricing_inr": {"qualified_lead": (100, 300), "appointment": (150, 400), "monthly_starter": 2999},
        "qualification_questions": [
            "Abhi hardware/paint shop ki marketing kaise hoti hai?",
            "Google pe aapki dukaan search karne par dikhti hai kya?",
            "Offer ya naye product ke posters kaun banata hai?",
        ],
    },
}


# ========================================================================== #
# CUSTOM NICHES — runtime-added niches (persisted to data/custom_niches.json)
# Builtin 42 upar static hain; client koi NAYA niche maange to add_custom_niche()
# se turant add hota hai aur flows/KB/agents/web-call sab me waise hi kaam
# karta hai (sab consumers NICHES dict hi padhte hain — hum usme merge karte).
# ========================================================================== #
import json as _json
import re as _re
from pathlib import Path as _Path

_BUILTIN_KEYS = frozenset(NICHES.keys())
_CUSTOM_FILE = _Path(__file__).resolve().parent.parent / "data" / "custom_niches.json"
_custom_mtime: float = -1.0


def _slugify(name: str) -> str:
    s = _re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return s[:50] or "custom_niche"


def _load_custom_niches(force: bool = False) -> None:
    """File se custom niches NICHES me merge karo (mtime-cached, multi-worker safe)."""
    global _custom_mtime
    try:
        if not _CUSTOM_FILE.exists():
            if _custom_mtime != -1.0:  # file delete ho gayi — purge customs
                for k in [k for k in list(NICHES) if k not in _BUILTIN_KEYS]:
                    NICHES.pop(k, None)
                _custom_mtime = -1.0
            return
        m = _CUSTOM_FILE.stat().st_mtime
        if not force and m == _custom_mtime:
            return
        data = _json.loads(_CUSTOM_FILE.read_text(encoding="utf-8")) or {}
        for k in [k for k in list(NICHES) if k not in _BUILTIN_KEYS and k not in data]:
            NICHES.pop(k, None)
        for k, cfg in data.items():
            if k in _BUILTIN_KEYS:
                continue
            cfg["custom"] = True
            NICHES[k] = cfg
        _custom_mtime = m
    except Exception:
        pass  # corrupt file should never break the app


def refresh_custom_niches() -> None:
    """Cheap mtime check — call before reads jahan freshness chahiye."""
    _load_custom_niches(force=False)


def add_custom_niche(
    name: str,
    keywords: list = None,
    target_type: str = "b2c",
    b2b_client: str = "",
    end_customer: str = "",
    avg_ticket_inr: str = "",
    pitch_hook: str = "",
    qualification_questions: list = None,
    pricing_inr: dict = None,
    key: str = None,
) -> tuple:
    """
    Naya niche register karo. Returns (key, config).
    Sensible defaults — sirf `name` zaroori hai; baaki business ke hisab se.
    """
    nkey = _slugify(key or name)
    refresh_custom_niches()
    if nkey in _BUILTIN_KEYS or nkey in NICHES:
        raise ValueError(f"Niche '{nkey}' already exists")
    if target_type not in ("b2c", "b2b", "both"):
        raise ValueError("target_type must be b2c | b2b | both")
    pricing = pricing_inr or {}
    cfg = {
        "name": name.strip(),
        "tier": "C",  # custom tier — dropdown me [custom] group
        "custom": True,
        "target_type": target_type,
        "b2b_client": b2b_client or f"{name} businesses",
        "end_customer": end_customer or (
            "Consumers interested in this service" if target_type != "b2b"
            else "Business buyers for this service"
        ),
        "keywords": keywords or [name.lower()],
        "avg_deal_value": avg_ticket_inr or "varies",
        "avg_ticket_inr": avg_ticket_inr or "varies",
        "pitch_hook": pitch_hook or f"bring qualified {name} customers to your business on autopilot",
        "pricing_inr": {
            "qualified_lead": tuple(pricing.get("qualified_lead", (300, 1500))),
            "appointment": tuple(pricing.get("appointment", (800, 2500))),
            "monthly_starter": int(pricing.get("monthly_starter", 12000)),
        },
        "qualification_questions": qualification_questions or [
            f"Are you currently looking for more {name} customers?",
            "What is your average deal or ticket size?",
            "Who follows up with your inquiries today?",
        ],
    }
    data = {}
    if _CUSTOM_FILE.exists():
        try:
            data = _json.loads(_CUSTOM_FILE.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    data[nkey] = cfg
    _CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CUSTOM_FILE.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    NICHES[nkey] = cfg
    _load_custom_niches(force=True)
    return nkey, cfg


def remove_custom_niche(key: str) -> bool:
    """Sirf custom niches delete ho sakte hain (builtin 25 protected)."""
    if key in _BUILTIN_KEYS:
        raise ValueError("Built-in niches cannot be removed")
    refresh_custom_niches()
    if not _CUSTOM_FILE.exists():
        return False
    try:
        data = _json.loads(_CUSTOM_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if key not in data:
        return False
    del data[key]
    _CUSTOM_FILE.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    NICHES.pop(key, None)
    _load_custom_niches(force=True)
    return True


_load_custom_niches(force=True)  # module import pe custom niches merge


# Convenience views ------------------------------------------------------- #

def niches_by_tier(tier: str) -> dict:
    """Return niches of a given tier ('S' | 'A' | 'B' | 'C'=custom)."""
    refresh_custom_niches()
    return {k: v for k, v in NICHES.items() if v.get("tier") == tier}


def niches_by_target(target_type: str) -> dict:
    """Return niches whose END CUSTOMERS match 'b2c' | 'b2b' (includes 'both')."""
    refresh_custom_niches()
    return {
        k: v for k, v in NICHES.items()
        if v.get("target_type") in (target_type, "both")
    }
