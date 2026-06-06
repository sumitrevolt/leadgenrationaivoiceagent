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
    "real_estate": {
        "name": "Real Estate (Resale & New Projects)",
        "tier": "S",
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
}


# Convenience views ------------------------------------------------------- #

def niches_by_tier(tier: str) -> dict:
    """Return niches of a given tier ('S' | 'A' | 'B')."""
    return {k: v for k, v in NICHES.items() if v.get("tier") == tier}


def niches_by_target(target_type: str) -> dict:
    """Return niches whose END CUSTOMERS match 'b2c' | 'b2b' (includes 'both')."""
    return {
        k: v for k, v in NICHES.items()
        if v.get("target_type") in (target_type, "both")
    }
