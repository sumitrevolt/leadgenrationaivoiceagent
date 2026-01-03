"""
Industry-Specific Call Scripts
B2B (Selling to Businesses) + B2C (For Customer's Leads)

These scripts are the SOUL of your AI Voice Agent.
Each industry has unique pain points, objections, and qualification criteria.
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ScriptType(Enum):
    """Type of script"""
    B2B_PLATFORM_SALES = "b2b_platform_sales"  # Selling YOUR service
    B2C_CLIENT_CAMPAIGNS = "b2c_client_campaigns"  # For YOUR CUSTOMER's leads


@dataclass
class IndustryScript:
    """Complete script for an industry"""
    industry_code: str
    industry_name: str
    script_type: ScriptType
    language: str  # hinglish, english, hindi
    
    # Opening
    greeting: str
    introduction: str
    permission_ask: str
    
    # Value Proposition
    hook_statement: str
    key_benefits: List[str]
    social_proof: str
    
    # Qualification (BANT)
    qualification_questions: List[Dict[str, str]]
    
    # Objection Handling
    objection_responses: Dict[str, str]
    
    # Closing
    appointment_pitch: str
    callback_offer: str
    closing: str
    
    # Industry-specific
    target_persona: str
    avg_deal_value: str
    call_to_action: str
    follow_up_template: str


# =============================================================================
# B2B SCRIPTS - FOR SELLING YOUR AI VOICE AGENT SERVICE
# =============================================================================

B2B_PLATFORM_SCRIPTS = {
    
    # ----- REAL ESTATE AGENCIES -----
    "real_estate_b2b": IndustryScript(
        industry_code="real_estate_b2b",
        industry_name="Real Estate Agencies",
        script_type=ScriptType.B2B_PLATFORM_SALES,
        language="hinglish",
        
        greeting="Hello, Namaste! Main LeadGen AI se Maya bol rahi hoon.",
        
        introduction="""Sir/Ma'am, aap real estate mein hain na? Main specifically 
        property dealers aur brokers ke liye call kar rahi hoon. Humne ek AI system 
        banaya hai jo aapke purane leads ko wapas call karke qualified buyers dhoondh 
        sakta hai - automatically.""",
        
        permission_ask="Kya main 2 minute mein explain karun ye kaise kaam karta hai?",
        
        hook_statement="""Aapke database mein kitne purane leads hain jo kabhi convert 
        nahi hue? 500? 1000? Humare AI ne ek broker ke liye 600 old leads mein se 
        23 serious buyers nikale - 2 weeks mein.""",
        
        key_benefits=[
            "Purane cold leads ko revive karta hai automatically",
            "24/7 calling - Sunday ko bhi, 8 PM ko bhi",
            "Site visit appointments directly book karta hai",
            "Hot leads pe turant WhatsApp alert milta hai",
            "Aapka time sirf serious buyers pe lagta hai"
        ],
        
        social_proof="""Mumbai mein ek luxury real estate firm ne humara AI use karke 
        first month mein 47 site visits book kiye. Unka ek broker kehta hai - 
        'Mera half work AI kar deta hai.'""",
        
        qualification_questions=[
            {
                "question": "Aap currently leads kaise generate karte hain - 99acres, MagicBricks, ya direct?",
                "intent": "lead_source",
                "scoring": {"99acres": 8, "direct": 10, "builder_tie_up": 9}
            },
            {
                "question": "Aapki team mein kitne sales people hain jo calling karte hain?",
                "intent": "team_size",
                "scoring": {"0-2": 6, "3-5": 8, "5+": 10}
            },
            {
                "question": "Monthly kitni inquiries aati hain approximately?",
                "intent": "lead_volume",
                "scoring": {"50+": 10, "20-50": 7, "<20": 5}
            },
            {
                "question": "Site visit se deal close hone mein average kitna time lagta hai?",
                "intent": "sales_cycle",
                "scoring": {"1-2 months": 9, "3-6 months": 7, "6+ months": 5}
            }
        ],
        
        objection_responses={
            "not_interested": """Samajh gaya sir. Ek quick question - aapke paas kitne 
                purane leads hain jo follow-up nahi ho paye? Wo potential revenue hai jo 
                waste ho raha hai. Sirf unko call karke dekhein - free trial hai.""",
            
            "already_have_team": """Perfect! Team ke liye ye helper hai, replacement nahi. 
                AI initial qualification karta hai, hot leads team ko milte hain. 
                Aapki team ka time sirf serious buyers pe lagta hai.""",
            
            "too_expensive": """Actually calculate karein - ek caller ki salary 15-20K, 
                plus phone bills, plus training time. Humara plan 10K se start hota hai 
                aur AI 500+ calls daily handle kar sakta hai. ROI pehle month mein.""",
            
            "ai_wont_work_for_real_estate": """Valid concern. Real estate emotional hai, 
                agreed. Lekin initial screening - budget, location preference, timeline - 
                ye AI efficiently karta hai. Serious buyers ko team handle karti hai. 
                Main ek recording bhejun actual call ki?""",
            
            "buyers_dont_trust_ai": """Actually surprise ho jayenge - log ab AI se comfortable hain. 
                Alexa, Google Assistant - sab use karte hain. Plus humara AI natural baat karta hai, 
                robotic nahi lagta. Demo mein sunayenge.""",
            
            "send_details": """Bilkul! WhatsApp pe case study bhej raha hoon real estate specific. 
                Plus ek sample call recording. Kal 11 baje ek quick call karke discuss karein?"""
        },
        
        appointment_pitch="""Sir, ek kaam karte hain - 15 minute ka demo le lo. Main screen share 
        pe dikhaunga ki AI kaise aapke old leads ko call karega. Live sun sakte hain AI ki baat. 
        Kal 3 baje ya parso 11 baje - kab free hain?""",
        
        callback_offer="""Aap busy hain, samajh gaya. Best time batao, main exactly wahi call karunga. 
        Plus abhi WhatsApp pe info bhej deta hoon review ke liye.""",
        
        closing="""Thank you sir! Demo confirm hai [DATE/TIME] ko. Main reminder WhatsApp pe bhej dunga. 
        Agar koi question ho toh directly reply kar dena. Have a great day!""",
        
        target_persona="Real Estate Broker / Agency Owner",
        avg_deal_value="₹15,000-25,000/month subscription",
        call_to_action="Book 15-minute Demo",
        
        follow_up_template="""🏠 *Real Estate AI Demo Confirmed*
        
Hello {name}!
Main Maya, LeadGen AI se.

Demo Details:
📅 Date: {date}
⏰ Time: {time}
📍 Mode: Google Meet

Aapko dikhaunga:
✅ AI kaise aapke old leads call karta hai
✅ Live call recording
✅ Appointment booking flow
✅ WhatsApp integration

Meeting Link: {link}

Questions? Reply karein!

- Maya, LeadGen AI"""
    ),
    
    # ----- SOLAR COMPANIES -----
    "solar_b2b": IndustryScript(
        industry_code="solar_b2b",
        industry_name="Solar Installation Companies",
        script_type=ScriptType.B2B_PLATFORM_SALES,
        language="hinglish",
        
        greeting="Hello, Namaste! Main LeadGen AI Solutions se bol rahi hoon.",
        
        introduction="""Sir, aap solar installation business mein hain na? Humne solar 
        companies ke liye specifically ek AI calling system banaya hai jo homeowners 
        aur factory owners ko pre-qualify karta hai before aapki team site visit kare.""",
        
        permission_ask="2 minute mein batao kaise 40% unqualified site visits kam ho sakte hain?",
        
        hook_statement="""Ek solar company ne humara AI use karke - pehle wo 100 site visits 
        mein 15 deals close karte the. Ab AI pre-qualify karta hai, 60 visits mein 15 deals. 
        40 visits ki petrol, time, aur manpower save.""",
        
        key_benefits=[
            "Roof suitability pre-check - shadow analysis questions",
            "Budget qualification before site visit",
            "Electricity bill check - viability confirm",
            "Decision maker confirmation",
            "Hot leads ko priority scheduling"
        ],
        
        social_proof="""Pune ki ek solar company - 3 months mein 127 installations. 
        Unhone kaha - 'Humari team sirf ready customers ke paas jaati hai ab.'""",
        
        qualification_questions=[
            {
                "question": "Aap residential solar karte hain ya commercial ya dono?",
                "intent": "business_type",
                "scoring": {"both": 10, "commercial": 9, "residential": 7}
            },
            {
                "question": "Monthly kitne leads generate hote hain - ads se ya referrals se?",
                "intent": "lead_volume"
            },
            {
                "question": "Current mein site visit to close ratio kya hai approximately?",
                "intent": "conversion_rate"
            },
            {
                "question": "Ek installation ka average ticket size kya hai?",
                "intent": "deal_value"
            }
        ],
        
        objection_responses={
            "solar_is_technical": """Exactly! Isliye AI initial screening karta hai - 
                roof type, floor count, electricity bill amount, ownership status. 
                Technical details aapki team handle karti hai qualified leads ke saath.""",
            
            "we_need_site_visit_anyway": """Bilkul, site visit zaruri hai. But imagine - 
                AI pehle 100 leads mein se 40 serious ones filter kar de. 
                Aapki team 40 quality visits karti hai instead of 100 random.""",
            
            "homeowners_wont_talk_to_ai": """Actually solar ke liye log curious hote hain. 
                AI naturally poochta hai - 'Aapka bijli ka bill kitna aata hai? 
                Interested hain solar se kam karne mein?' Conversation natural hai.""",
            
            "too_expensive": """ROI calculate karein - ek site visit ka cost average 500-800 Rs 
                (petrol + time). Agar 50 unnecessary visits save hue, that's 25-40K saved. 
                Humara plan 15K se start."""
        },
        
        appointment_pitch="""Ek 15-minute demo mein dekhein ki AI kaise homeowners ko call 
        karke roof suitability aur budget check karta hai. Kal ya parso kab free hain?""",
        
        callback_offer="Aap site pe hain abhi, samajh gaya. Best time batao, will call back.",
        
        closing="Thank you! WhatsApp pe details aa jayenge. Demo mein milte hain!",
        
        target_persona="Solar Company Owner / Sales Manager",
        avg_deal_value="₹15,000-30,000/month",
        call_to_action="Book Demo",
        
        follow_up_template="""☀️ *Solar Lead Qualification Demo*

Hi {name}!

Demo scheduled:
📅 {date} at {time}

Dekhenge:
✅ Pre-qualification call flow
✅ Roof suitability questions
✅ Budget screening
✅ Site visit booking

Link: {link}

- LeadGen AI Team"""
    ),
    
    # ----- COACHING INSTITUTES -----
    "coaching_b2b": IndustryScript(
        industry_code="coaching_b2b",
        industry_name="Coaching Institutes / EdTech",
        script_type=ScriptType.B2B_PLATFORM_SALES,
        language="hinglish",
        
        greeting="Hello! Main LeadGen AI se Maya bol rahi hoon.",
        
        introduction="""Sir/Ma'am, aap education/coaching mein hain na? Humne coaching 
        institutes ke liye ek AI counselor banaya hai jo students/parents ko call karke 
        qualified admissions le kar aata hai - automatically.""",
        
        permission_ask="2 minute mein batao kaise 3x more admissions possible hain same leads mein?",
        
        hook_statement="""Ek IIT coaching institute - unke paas 5000 leads the website se. 
        Manually call karte to 2 months lagte. AI ne 1 week mein sab call kiye, 
        340 counseling sessions book kiye, 127 admissions.""",
        
        key_benefits=[
            "Instant lead response - enquiry aate hi call",
            "Parent + student dono se baat kar sakta hai",
            "Course interest, budget, timeline qualify karta hai",
            "Demo class / counseling session book karta hai",
            "Cold leads ko regular follow-up"
        ],
        
        social_proof="""NEET coaching institute Delhi mein - admission season mein 
        3 months mein 450+ admissions. Pehle same time mein 200 hote the. 
        AI ne 2x kiya with same team.""",
        
        qualification_questions=[
            {
                "question": "Kaunse courses/exams ke liye coaching hai - JEE, NEET, CA, ya others?",
                "intent": "course_type"
            },
            {
                "question": "Monthly kitni enquiries aati hain website/ads se?",
                "intent": "lead_volume"
            },
            {
                "question": "Enquiry se admission tak conversion rate kya hai currently?",
                "intent": "conversion_rate"
            },
            {
                "question": "Counseling team mein kitne log hain?",
                "intent": "team_size"
            }
        ],
        
        objection_responses={
            "parents_need_personal_touch": """Bilkul sahi! Personal touch counselors dete hain. 
                AI sirf initial screening karta hai - budget, timeline, course interest. 
                Qualified parents counselor ke paas jaate hain.""",
            
            "students_are_different": """Agree. Isliye AI flexible hai - parent se formal, 
                student se friendly baat karta hai. Plus regional language support - 
                Hindi, Hinglish, English.""",
            
            "already_have_tele_callers": """Perfect! Unke liye life easy ho jayegi. 
                AI 1000 leads mein se 200 interested filter kar dega. 
                Telecallers sirf hot leads pe focus karein.""",
            
            "admission_season_is_over": """Actually off-season mein nurture karna important hai. 
                AI regularly purane leads ko follow-up karta hai. 
                Season start hote hi ready pipeline milega."""
        },
        
        appointment_pitch="""15-minute demo mein dekhein AI counselor kaise parents se baat 
        karta hai. Live call sunenge. Kal 4 baje ya parso 11 baje?""",
        
        callback_offer="Classes chal rahi hain, samjha. Evening 6 baje call karun?",
        
        closing="Thank you! WhatsApp pe case study bhej raha hoon. Demo mein milte hain!",
        
        target_persona="Institute Owner / Admission Head",
        avg_deal_value="₹20,000-40,000/month",
        call_to_action="Book Demo",
        
        follow_up_template="""📚 *Education AI Counselor Demo*

Hi {name}!

Demo Details:
📅 {date}
⏰ {time}

Dekhenge:
✅ Parent counseling flow
✅ Course interest qualification
✅ Demo class booking
✅ Follow-up automation

Link: {link}

- LeadGen AI"""
    ),
    
    # ----- DENTAL/HEALTHCARE CLINICS -----
    "healthcare_b2b": IndustryScript(
        industry_code="healthcare_b2b",
        industry_name="Dental & Healthcare Clinics",
        script_type=ScriptType.B2B_PLATFORM_SALES,
        language="hinglish",
        
        greeting="Hello, Namaste! Main LeadGen AI se bol rahi hoon.",
        
        introduction="""Doctor sahab, main clinics ke liye specifically call kar rahi hoon. 
        Humne ek AI appointment system banaya hai jo aapke empty slots fill karta hai 
        automatically - no-shows kam karta hai aur high-value treatments book karta hai.""",
        
        permission_ask="2 minute mein batao kaise aapki chair occupancy 90%+ ho sakti hai?",
        
        hook_statement="""Ek dental clinic Mumbai mein - pehle 30% empty slots hote the. 
        AI ne old patients ko call kiya, reminders bheje, 2 months mein 
        chair occupancy 85% ho gayi. Implant inquiries 2x.""",
        
        key_benefits=[
            "Old patients ko treatment reminders",
            "Empty slot filling - next day appointments",
            "High-value treatment promotion - implants, orthodontics",
            "No-show reduction with confirmation calls",
            "Review collection after visits"
        ],
        
        social_proof="""Dental chain (5 clinics) - monthly appointments 40% increase. 
        Implant revenue alone 3x ho gaya because AI specifically pushes high-ticket.""",
        
        qualification_questions=[
            {
                "question": "Aap general dentistry mein hain ya specialized - implants, orthodontics?",
                "intent": "specialization"
            },
            {
                "question": "Currently empty slots kitne percent hain average?",
                "intent": "occupancy"
            },
            {
                "question": "Patient database mein kitne patients hain approximately?",
                "intent": "database_size"
            },
            {
                "question": "High-value treatments mein kya offer karte hain?",
                "intent": "services"
            }
        ],
        
        objection_responses={
            "patients_need_personal_care": """100% agree! Clinical care personal hi hoga. 
                AI sirf appointment booking aur reminders handle karta hai. 
                Aapki receptionist ko free karta hai quality work ke liye.""",
            
            "we_have_receptionist": """Perfect! Receptionist ke liye ye helper hai. 
                AI off-hours mein calls handle karta hai, follow-ups karta hai. 
                Receptionist clinic pe focus kare.""",
            
            "healthcare_is_sensitive": """Bilkul sahi. Isliye AI trained hai sensitively baat karne ke liye. 
                Plus HIPAA compliant. Recording nahi hoti personal health info ki."""
        },
        
        appointment_pitch="""15-minute demo mein dekhein AI kaise patients ko call karta hai. 
        Appointment booking flow dikhaunga. Kal 2 baje ya parso 11 baje?""",
        
        callback_offer="Patients hain abhi, samjha. Lunch time 1:30 baje call karun?",
        
        closing="Thank you Doctor! WhatsApp pe details aa jayenge. Demo mein milte hain!",
        
        target_persona="Clinic Owner / Practice Manager",
        avg_deal_value="₹10,000-20,000/month",
        call_to_action="Book Demo",
        
        follow_up_template="""🏥 *Healthcare AI Demo*

Hi Dr. {name}!

Demo: {date} at {time}

Topics:
✅ Patient recall system
✅ Appointment booking
✅ No-show reduction
✅ High-value treatment promotion

Link: {link}

- LeadGen AI"""
    ),
    
    # ----- INSURANCE AGENTS -----
    "insurance_b2b": IndustryScript(
        industry_code="insurance_b2b",
        industry_name="Insurance Agents & Agencies",
        script_type=ScriptType.B2B_PLATFORM_SALES,
        language="hinglish",
        
        greeting="Hello! Main LeadGen AI se Maya bol rahi hoon.",
        
        introduction="""Sir, aap insurance mein hain na? Humne insurance agents ke liye 
        specifically ek AI calling system banaya hai jo prospects ko pre-qualify karta hai 
        before aap unse milein. Budget, need, timeline - sab pehle clear.""",
        
        permission_ask="2 minute mein batao kaise aapke 50% meetings more productive ho sakte hain?",
        
        hook_statement="""Ek LIC agent - pehle 20 meetings mein 3 policies close hota tha. 
        AI pre-qualification ke baad - 12 meetings mein 5 policies. 
        Better meetings, better closing, less wasted time.""",
        
        key_benefits=[
            "Lead pre-qualification - budget, need assessment",
            "Policy renewal reminders automatically",
            "Cross-sell/upsell calls to existing customers",
            "Meeting scheduling with qualified prospects",
            "Referral requests from happy customers"
        ],
        
        social_proof="""Insurance agency (10 agents) - monthly premium collection 35% up. 
        AI handles initial calls, agents close. Best part - renewal rate 95% because 
        AI reminds customers before expiry.""",
        
        qualification_questions=[
            {
                "question": "Kaunsi insurance - life, health, motor, ya general?",
                "intent": "insurance_type"
            },
            {
                "question": "Team mein kitne agents hain?",
                "intent": "team_size"
            },
            {
                "question": "Monthly kitne new leads aate hain?",
                "intent": "lead_volume"
            },
            {
                "question": "Lead to meeting to close ratio kya hai currently?",
                "intent": "conversion"
            }
        ],
        
        objection_responses={
            "insurance_needs_trust": """100% agree - trust human relationship se banta hai. 
                AI sirf initial screening karta hai. Aap trust build karte hain 
                already interested prospects ke saath.""",
            
            "customers_wont_share_info": """Actually basic info - family size, current policies, 
                approximate income range - log share karte hain if asked professionally. 
                AI naturally conversation mein poochta hai.""",
            
            "i_work_on_referrals": """Referrals best hain! AI aapke existing customers ko call karke 
                referrals maang sakta hai. Plus renewal reminders - happy customers = more referrals."""
        },
        
        appointment_pitch="""15-minute demo mein dekhein AI kaise prospects ko qualify karta hai. 
        Insurance specific call flow dikhaunga. Kal 5 baje ya parso 11 baje?""",
        
        callback_offer="Client meeting mein hain, samjha. Evening 7 baje call karun?",
        
        closing="Thank you! WhatsApp pe case study aa jayega. Demo mein milte hain!",
        
        target_persona="Insurance Agent / Agency Owner",
        avg_deal_value="₹10,000-25,000/month",
        call_to_action="Book Demo",
        
        follow_up_template="""📋 *Insurance AI Demo*

Hi {name}!

Demo: {date} at {time}

Topics:
✅ Lead pre-qualification
✅ Renewal automation
✅ Cross-sell campaigns
✅ Referral collection

Link: {link}

- LeadGen AI"""
    ),
}


# =============================================================================
# B2C SCRIPTS - FOR YOUR CUSTOMER'S BUSINESSES
# These are the scripts your customers' AI agents will use
# =============================================================================

B2C_CLIENT_SCRIPTS = {
    
    # ----- REAL ESTATE (For Property Dealers) -----
    "real_estate_b2c": IndustryScript(
        industry_code="real_estate_b2c",
        industry_name="Real Estate Lead Qualification",
        script_type=ScriptType.B2C_CLIENT_CAMPAIGNS,
        language="hinglish",
        
        greeting="Hello, Namaste! Main {client_name} ki taraf se call kar rahi hoon.",
        
        introduction="""Sir/Ma'am, aapne {client_name} pe property enquiry ki thi. 
        Main aapki requirement samajhne ke liye call kar rahi hoon taaki 
        aapko suitable options dikha sakein.""",
        
        permission_ask="Kya main 2 minute mein aapki requirement samajh loon?",
        
        hook_statement="Humare paas {location} mein kuch excellent options hain aapke budget mein.",
        
        key_benefits=[
            "Verified properties only",
            "Direct owner/builder connection",
            "No brokerage on select properties",
            "Site visit arrangement",
            "Home loan assistance"
        ],
        
        social_proof="500+ happy families ne {client_name} se apna dream home liya hai.",
        
        qualification_questions=[
            {
                "question": "Aap kahan property dekh rahe hain - koi specific area?",
                "intent": "location_preference",
                "entity_extraction": ["area", "city", "locality"]
            },
            {
                "question": "Budget range kya hai approximately? Ready to move chahiye ya under-construction?",
                "intent": "budget_and_type",
                "entity_extraction": ["budget", "property_type"]
            },
            {
                "question": "Kitne BHK chahiye? Family size kitni hai?",
                "intent": "size_requirement",
                "entity_extraction": ["bhk", "family_size"]
            },
            {
                "question": "Kab tak shift karna hai - 3 months, 6 months?",
                "intent": "timeline",
                "entity_extraction": ["timeline"]
            },
            {
                "question": "Home loan lena hai ya cash purchase?",
                "intent": "payment_mode",
                "entity_extraction": ["payment_mode"]
            }
        ],
        
        objection_responses={
            "just_browsing": """Bilkul, abhi research stage mein hain - samajh gaya. 
                Main aapko WhatsApp pe kuch options bhej deta hoon explore karne ke liye. 
                Jab ready hain toh batana, site visit arrange kar denge.""",
            
            "already_talking_to_broker": """Theek hai! But ek free site visit le lo humare saath bhi. 
                Compare karna achha hai. Koi commitment nahi.""",
            
            "not_interested_now": """Understood. Main 2 weeks baad check karun? 
                Tab tak WhatsApp pe market updates bhejta rahunga.""",
            
            "budget_issue": """Budget flexible hai. EMI options bhi available hain. 
                Ek baar options dekh lo, phir decide karna."""
        },
        
        appointment_pitch="""Sir, ek kaam karte hain - {location} mein 3 best options shortlist 
        karke site visit arrange karta hoon. Kal ya parso kab free hain subah ya dopahar?""",
        
        callback_offer="""Aap busy hain abhi, samajh gaya. Best time batao, 
        main exactly wahi call karunga.""",
        
        closing="""Thank you sir! Site visit {date} {time} ko confirm hai. 
        Main WhatsApp pe location aur property details bhej raha hoon. 
        Koi question ho toh reply kar dena. Have a great day!""",
        
        target_persona="Home Buyer / Investor",
        avg_deal_value="Variable - Property dependent",
        call_to_action="Book Site Visit",
        
        follow_up_template="""🏠 *Site Visit Confirmed*

Hi {name}!

Property Visit Details:
📅 Date: {date}
⏰ Time: {time}
📍 Location: {location}

Properties:
{property_list}

Our Executive: {executive_name}
Contact: {executive_phone}

See you there!

- {client_name}"""
    ),
    
    # ----- SOLAR (For Solar Companies) -----
    "solar_b2c": IndustryScript(
        industry_code="solar_b2c",
        industry_name="Solar Lead Qualification",
        script_type=ScriptType.B2C_CLIENT_CAMPAIGNS,
        language="hinglish",
        
        greeting="Hello, Namaste! Main {client_name} se call kar rahi hoon.",
        
        introduction="""Sir/Ma'am, aapne solar installation ke baare mein enquiry ki thi. 
        Main quick questions se samajhna chahti hoon ki aapke ghar ke liye solar 
        kitna suitable hai aur kitna save hoga.""",
        
        permission_ask="Kya 2 minute mein basic details le loon?",
        
        hook_statement="""Solar se aapka bijli bill 80% tak kam ho sakta hai. 
        Plus government subsidy bhi milti hai.""",
        
        key_benefits=[
            "80% electricity bill reduction",
            "Government subsidy up to ₹78,000",
            "25 year warranty",
            "Net metering - extra power sell back",
            "Free site survey"
        ],
        
        social_proof="{location} mein 200+ families already solar use kar rahi hain {client_name} ke through.",
        
        qualification_questions=[
            {
                "question": "Aapka monthly bijli bill approximately kitna aata hai?",
                "intent": "electricity_bill",
                "entity_extraction": ["bill_amount"],
                "scoring": {">5000": 10, "3000-5000": 8, "1000-3000": 6, "<1000": 3}
            },
            {
                "question": "Ghar apna hai ya rent pe? Kitni floors hai building?",
                "intent": "ownership_and_roof",
                "entity_extraction": ["ownership", "floors"]
            },
            {
                "question": "Roof pe koi shadow aata hai - building, tree se?",
                "intent": "roof_suitability",
                "entity_extraction": ["shadow_status"]
            },
            {
                "question": "Aap decision maker hain ghar ke? Investment kisike saath discuss karni hai?",
                "intent": "decision_maker",
                "entity_extraction": ["is_decision_maker"]
            },
            {
                "question": "Subsidy ke saath ya without - kaise lena chahenge?",
                "intent": "payment_preference",
                "entity_extraction": ["payment_mode"]
            }
        ],
        
        objection_responses={
            "too_expensive": """Actually subsidy ke baad cost bahut reasonable hai. 
                Plus EMI option bhi hai - monthly EMI aapke bijli bill se kam hogi. 
                Free site survey mein exact cost batayenge.""",
            
            "roof_is_not_suitable": """Hmm, expert survey ke bina confirm nahi ho sakta. 
                Free survey hai - engineer aayega, check karega, suitable nahi to bhi koi charge nahi.""",
            
            "need_to_discuss": """Bilkul! Family ke saath discuss karna important hai. 
                Main ek detailed proposal WhatsApp pe bhej deta hoon. 
                2-3 din baad call karun?""",
            
            "already_got_quotes": """Perfect! Compare karna achha hai. Humare rates competitive hain 
                plus after-sales service best hai. Free survey mein quote de denge."""
        },
        
        appointment_pitch="""Sir, ek free site survey schedule karte hain. Engineer aayega, 
        roof check karega, exact savings calculate karke batayega. 
        Kal ya parso - subah 10 baje ya dopahar 3 baje - kab suit karega?""",
        
        callback_offer="Aap ghar pe nahi hain abhi. Kal kab hain? Tab survey schedule karein.",
        
        closing="""Thank you sir! Site survey {date} {time} ko confirm hai. 
        Engineer aane se pehle call karega. WhatsApp pe confirmation aa jayega. 
        Have a great day!""",
        
        target_persona="Homeowner with high electricity bill",
        avg_deal_value="Variable - System size dependent",
        call_to_action="Book Free Site Survey",
        
        follow_up_template="""☀️ *Free Solar Survey Confirmed*

Hi {name}!

Survey Details:
📅 Date: {date}
⏰ Time: {time}
📍 Location: {address}

Survey includes:
✅ Roof assessment
✅ Shadow analysis
✅ System sizing
✅ Savings calculation
✅ Subsidy eligibility

Our Engineer: {engineer_name}
Contact: {engineer_phone}

- {client_name}"""
    ),
    
    # ----- COACHING (For Coaching Institutes) -----
    "coaching_b2c": IndustryScript(
        industry_code="coaching_b2c",
        industry_name="Coaching Admission Calls",
        script_type=ScriptType.B2C_CLIENT_CAMPAIGNS,
        language="hinglish",
        
        greeting="Hello! Main {client_name} se call kar rahi hoon.",
        
        introduction="""Aapne {exam_type} coaching ke baare mein enquiry ki thi. 
        Main briefly samajhna chahti hoon aapki preparation ke baare mein 
        taaki best batch recommend kar sakein.""",
        
        permission_ask="Kya 2-3 minute baat kar sakte hain?",
        
        hook_statement="""{client_name} se {result_stat} - aap bhi achieve kar sakte hain.""",
        
        key_benefits=[
            "Experienced faculty - IIT/AIIMS background",
            "Small batch size for attention",
            "Regular mock tests",
            "Doubt clearing sessions",
            "Study material included"
        ],
        
        social_proof="Last year {success_count} students selected in {exam_type}.",
        
        qualification_questions=[
            {
                "question": "Student class 11th mein hai ya 12th mein?",
                "intent": "current_class"
            },
            {
                "question": "School kaun sa hai? CBSE ya State board?",
                "intent": "school_info"
            },
            {
                "question": "Abhi koi coaching chal rahi hai ya nahi?",
                "intent": "current_coaching"
            },
            {
                "question": "Target exam kya hai - JEE Main, Advanced, NEET?",
                "intent": "target_exam"
            },
            {
                "question": "Fee budget approximately kya hai? Installment chahiye ya lump sum?",
                "intent": "budget"
            }
        ],
        
        objection_responses={
            "fees_too_high": """Fees quality ke hisaab se hai. Plus scholarships available hain - 
                admission test pe percentage ke basis pe. EMI option bhi hai.""",
            
            "already_in_coaching": """Koi baat nahi. Ek demo class attend karo, compare kar lo. 
                Free hai, koi commitment nahi.""",
            
            "results_kya_hain": """Excellent question! Last year {success_count} selections. 
                Air 1, 2, 3 humare hain {exam_type} mein. Demo mein detail batayenge.""",
            
            "too_far": """Humari online batch bhi available hai - same faculty, same material. 
                Ya hostel facility bhi hai for outstation students."""
        },
        
        appointment_pitch="""Ek free counseling session schedule karte hain. 
        Student aur parents dono aa sakte hain. Faculty se milenge, batch dekhenge. 
        Kal ya parso - 4 baje ya 6 baje - kab free hain?""",
        
        callback_offer="School time chal rahi hai. Evening 6 baje call karun?",
        
        closing="""Thank you! Counseling session {date} {time} ko confirm hai. 
        Student ko school report card aur ID laane boliyega. 
        WhatsApp pe reminder aa jayega. See you!""",
        
        target_persona="Student / Parent",
        avg_deal_value="Course fee dependent",
        call_to_action="Book Counseling Session",
        
        follow_up_template="""📚 *Counseling Session Confirmed*

Hi {parent_name}!

Session Details:
📅 Date: {date}
⏰ Time: {time}
📍 Location: {center_address}

Please bring:
- Student ID
- School report card
- Passport photo (for scholarship test)

Counselor: {counselor_name}
Contact: {counselor_phone}

- {client_name}"""
    ),
}


# =============================================================================
# SCRIPT MANAGER
# =============================================================================

class IndustryScriptManager:
    """
    Manages all industry scripts
    Provides easy access for the AI Voice Agent
    """
    
    def __init__(self):
        self.b2b_scripts = B2B_PLATFORM_SCRIPTS
        self.b2c_scripts = B2C_CLIENT_SCRIPTS
    
    def get_b2b_script(self, industry_code: str) -> Optional[IndustryScript]:
        """Get B2B script for selling your service"""
        return self.b2b_scripts.get(industry_code)
    
    def get_b2c_script(self, industry_code: str) -> Optional[IndustryScript]:
        """Get B2C script for customer's campaigns"""
        return self.b2c_scripts.get(industry_code)
    
    def get_all_b2b_industries(self) -> List[str]:
        """List all B2B industries"""
        return list(self.b2b_scripts.keys())
    
    def get_all_b2c_industries(self) -> List[str]:
        """List all B2C industries"""
        return list(self.b2c_scripts.keys())
    
    def get_objection_response(
        self, 
        industry_code: str, 
        objection_type: str,
        script_type: ScriptType = ScriptType.B2B_PLATFORM_SALES
    ) -> Optional[str]:
        """Get objection response for specific industry"""
        if script_type == ScriptType.B2B_PLATFORM_SALES:
            script = self.b2b_scripts.get(industry_code)
        else:
            script = self.b2c_scripts.get(industry_code)
        
        if script:
            return script.objection_responses.get(objection_type)
        return None
    
    def get_qualification_questions(
        self,
        industry_code: str,
        script_type: ScriptType = ScriptType.B2B_PLATFORM_SALES
    ) -> List[Dict[str, str]]:
        """Get qualification questions for industry"""
        if script_type == ScriptType.B2B_PLATFORM_SALES:
            script = self.b2b_scripts.get(industry_code)
        else:
            script = self.b2c_scripts.get(industry_code)
        
        if script:
            return script.qualification_questions
        return []
    
    def format_script_for_llm(
        self,
        industry_code: str,
        script_type: ScriptType,
        client_name: str = "",
        client_service: str = "",
        lead_data: Dict[str, Any] = None
    ) -> str:
        """
        Format script as system prompt for LLM
        This is what feeds into the AI brain
        """
        if script_type == ScriptType.B2B_PLATFORM_SALES:
            script = self.b2b_scripts.get(industry_code)
        else:
            script = self.b2c_scripts.get(industry_code)
        
        if not script:
            return ""
        
        lead_data = lead_data or {}
        
        prompt = f"""You are an AI sales agent calling for {client_name or 'LeadGen AI'}.

INDUSTRY: {script.industry_name}
SCRIPT TYPE: {script_type.value}
LANGUAGE: {script.language} (Hinglish - mix of Hindi and English)

CALL FLOW:
1. GREETING: {script.greeting}
2. INTRODUCTION: {script.introduction}
3. PERMISSION: {script.permission_ask}

VALUE PROPOSITION:
Hook: {script.hook_statement}

Benefits to mention:
{chr(10).join(f'- {b}' for b in script.key_benefits)}

Social Proof: {script.social_proof}

QUALIFICATION QUESTIONS (ask naturally, not like a survey):
{chr(10).join(f'{i+1}. {q["question"]}' for i, q in enumerate(script.qualification_questions))}

OBJECTION HANDLING:
{chr(10).join(f'If they say "{k}": {v}' for k, v in script.objection_responses.items())}

APPOINTMENT PITCH:
{script.appointment_pitch}

CALLBACK OFFER:
{script.callback_offer}

CLOSING:
{script.closing}

LEAD CONTEXT:
{chr(10).join(f'- {k}: {v}' for k, v in lead_data.items()) if lead_data else 'No prior data'}

IMPORTANT RULES:
1. Speak naturally in {script.language}
2. Be conversational, not robotic
3. Listen and respond to what they say
4. Handle objections smoothly
5. Always try to book appointment or get callback time
6. Respect if they say "not interested" - try once, then politely end
7. Never reveal you are AI unless directly asked
"""
        return prompt


# Initialize global script manager
script_manager = IndustryScriptManager()
