"""
Script Loader
Dynamic loading and management of call scripts
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import json
import os

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class CallScript:
    """Call script configuration"""
    name: str
    niche: str
    language: str  # hindi, english, hinglish
    
    # Opening
    greeting: str
    introduction: str
    permission_ask: str
    
    # Pitch
    value_proposition: str
    key_benefits: List[str]
    social_proof: str
    
    # Qualification questions
    qualification_questions: List[Dict[str, str]]  # {"question": "", "intent": ""}
    
    # Objection handling
    objection_responses: Dict[str, str]
    
    # Closing
    appointment_pitch: str
    callback_offer: str
    closing: str
    
    # Compliance
    disclosure: str = "This is an automated call from {client_name}. Press 9 at any time to be removed from our list."


class ScriptLoader:
    """Load and manage call scripts"""
    
    SCRIPTS: Dict[str, CallScript] = {}
    
    @classmethod
    def load_script(cls, niche: str, language: str = "hinglish") -> Optional[CallScript]:
        """Load script for a specific niche and language"""
        script_key = f"{niche}_{language}"
        
        if script_key in cls.SCRIPTS:
            return cls.SCRIPTS[script_key]
        
        # Load from predefined scripts
        script = cls._get_predefined_script(niche, language)
        if script:
            cls.SCRIPTS[script_key] = script
            return script
        
        # Fallback to default
        return cls._get_default_script(language)
    
    @classmethod
    def _get_predefined_script(cls, niche: str, language: str) -> Optional[CallScript]:
        """Get predefined script for niche"""
        scripts = {
            "real_estate_hinglish": cls._real_estate_script(),
            "real_estate_hindi": cls._real_estate_script_hindi(),
            "real_estate_english": cls._real_estate_script_english(),
            "solar_hinglish": cls._solar_script(),
            "logistics_hinglish": cls._logistics_script(),
            "digital_marketing_hinglish": cls._digital_marketing_script(),
            "manufacturing_hinglish": cls._manufacturing_script(),
            "insurance_hinglish": cls._insurance_script(),
        }
        
        return scripts.get(f"{niche}_{language}")
    
    @classmethod
    def _get_default_script(cls, language: str = "hinglish") -> CallScript:
        """Default generic B2B script"""
        return CallScript(
            name="Default B2B Script",
            niche="general",
            language=language,
            greeting="Hello, namaste!",
            introduction="Main {client_name} se bol raha/rahi hoon.",
            permission_ask="Kya aapke paas do minute hain mere liye?",
            value_proposition="Hum businesses ko grow karne mein help karte hain {service} ke through.",
            key_benefits=[
                "Apni efficiency improve karein",
                "Cost kam karein",
                "Revenue badhayein"
            ],
            social_proof="Humne 500+ businesses ko successfully help kiya hai.",
            qualification_questions=[
                {"question": "Kya aap business ke owner hain ya decision maker?", "intent": "decision_maker"},
                {"question": "Currently aap kya solution use kar rahe hain?", "intent": "current_solution"},
                {"question": "Kya isko improve karne mein interest hai?", "intent": "interest_level"}
            ],
            objection_responses={
                "not_interested": "Main samajh sakta/sakti hoon. Bahut businesses initially hesitate karte hain. Kya main sirf 2 minute mein batao ki yeh kaise help karega?",
                "no_time": "Bilkul, aap busy hain. Kya main kal ya parso call kar sakta/sakti hoon? Kaunsa time best hoga?",
                "already_have": "Bahut acchi baat hai! Kya current solution se fully satisfied hain ya improvement ki scope hai?",
                "too_expensive": "Pricing ki baat karein toh, investment pe return matter karta hai. Kya main dikhao ki aap kitna save kar sakte hain?",
                "send_email": "Zaroor, email bhej deta/deti hoon. Lekin 30 second mein batao key benefit - email mein detail hoga.",
                "call_later": "Perfect, kab call karun? Aapka convenient time bata dijiye."
            },
            appointment_pitch="Ek free consultation schedule karein jisme main personally aapko dikhaunga ki yeh kaise help karega.",
            callback_offer="Aap batao kab call karun, main exactly usi time pe call karunga.",
            closing="Thank you for your time. {next_steps} Good day!"
        )
    
    @classmethod
    def _real_estate_script(cls) -> CallScript:
        """Real estate script (Hinglish)"""
        return CallScript(
            name="Real Estate Lead Generation",
            niche="real_estate",
            language="hinglish",
            greeting="Hello, namaste! Main {agent_name} bol raha/rahi hoon.",
            introduction="{client_name} ki taraf se call kar raha/rahi hoon, jo {city} ke top real estate developers mein se ek hain.",
            permission_ask="Aapke paas ek minute hai mere liye?",
            value_proposition="Hum {location} mein premium residential aur commercial properties offer kar rahe hain jo excellent investment opportunity hai.",
            key_benefits=[
                "Prime location with great connectivity",
                "Assured returns of 12-15% annually",
                "RERA approved projects with clear titles",
                "Flexible payment plans available"
            ],
            social_proof="Humare 2000+ satisfied investors hain aur last year 150 crore ka business kiya hai.",
            qualification_questions=[
                {"question": "Kya aap property investment mein interested hain - residential ya commercial?", "intent": "interest_type"},
                {"question": "Aapka budget range kya hai approximately?", "intent": "budget"},
                {"question": "Kya aap loan lenge ya cash payment?", "intent": "payment_mode"},
                {"question": "Timeline kya hai aapka? Immediate investment ya future planning?", "intent": "timeline"},
                {"question": "Kya aapne pehle bhi property invest ki hai?", "intent": "experience"}
            ],
            objection_responses={
                "not_interested": "Main samajh sakta hoon. Property investment big decision hai. Lekin ek minute mein batao - aapko pata hai current market mein kaise returns aa rahe hain?",
                "no_budget": "Budget ki baat karein toh, humare paas starting from 25 lakh ke options hain. Plus easy EMI options bhi available hain.",
                "already_invested": "Bahut accha! Smart investor hain aap. Kya portfolio diversify karna chahenge? Ek new location check karein?",
                "market_down": "Actually market correction best time hai invest karne ka. Buy low sell high - abhi perfect opportunity hai.",
                "location_issue": "Location ke baare mein - kya aapko pata hai ki upcoming metro connectivity se prices 40% increase hone wale hain?",
                "not_now": "Bilkul, koi pressure nahi. Lekin current prices lock karne ka option hai. Kab free hain site visit ke liye?"
            },
            appointment_pitch="Sunday ko humari team ke saath free site visit schedule karein. Pickup drop facility hai aur lunch bhi complementary.",
            callback_offer="Aapka WhatsApp number pe brochure bhej deta hoon. Kal subah call karke discuss karein?",
            closing="Thank you for your time. Site visit ke liye confirmation WhatsApp pe bhej dunga. Have a great day!"
        )
    
    @classmethod
    def _real_estate_script_hindi(cls) -> CallScript:
        """Real estate script (Pure Hindi)"""
        return CallScript(
            name="Real Estate Lead Generation Hindi",
            niche="real_estate",
            language="hindi",
            greeting="नमस्ते! मैं {agent_name} बोल रहा/रही हूं।",
            introduction="{client_name} की तरफ से बोल रहा/रही हूं, जो {city} के प्रमुख रियल एस्टेट डेवलपर्स में से एक हैं।",
            permission_ask="क्या आपके पास एक मिनट है मेरे लिए?",
            value_proposition="हम {location} में प्रीमियम रेजिडेंशियल और कमर्शियल प्रॉपर्टी ऑफर कर रहे हैं।",
            key_benefits=[
                "प्राइम लोकेशन",
                "12-15% वार्षिक रिटर्न",
                "RERA अप्रूव्ड प्रोजेक्ट्स",
                "आसान पेमेंट प्लान"
            ],
            social_proof="हमारे 2000+ संतुष्ट निवेशक हैं।",
            qualification_questions=[
                {"question": "क्या आप प्रॉपर्टी इन्वेस्टमेंट में रुचि रखते हैं?", "intent": "interest_type"},
                {"question": "आपका बजट लगभग क्या है?", "intent": "budget"},
                {"question": "क्या आप लोन लेंगे या नकद भुगतान?", "intent": "payment_mode"}
            ],
            objection_responses={
                "not_interested": "मैं समझ सकता हूं। क्या मैं सिर्फ एक मिनट में बता सकता हूं?",
                "no_budget": "हमारे पास 25 लाख से शुरू के विकल्प हैं।"
            },
            appointment_pitch="रविवार को फ्री साइट विजिट शेड्यूल करें।",
            callback_offer="कब कॉल करूं?",
            closing="आपके समय के लिए धन्यवाद।"
        )
    
    @classmethod
    def _real_estate_script_english(cls) -> CallScript:
        """Real estate script (English)"""
        return CallScript(
            name="Real Estate Lead Generation English",
            niche="real_estate",
            language="english",
            greeting="Hello! This is {agent_name} speaking.",
            introduction="I'm calling from {client_name}, one of the leading real estate developers in {city}.",
            permission_ask="Do you have a minute to speak?",
            value_proposition="We're offering premium residential and commercial properties in {location} with excellent investment potential.",
            key_benefits=[
                "Prime location with excellent connectivity",
                "Assured returns of 12-15% annually",
                "RERA approved projects with clear titles",
                "Flexible payment options available"
            ],
            social_proof="We have over 2000 satisfied investors and completed 150 crore in sales last year.",
            qualification_questions=[
                {"question": "Are you interested in residential or commercial property investment?", "intent": "interest_type"},
                {"question": "What's your approximate budget range?", "intent": "budget"},
                {"question": "Would you prefer a loan or cash payment?", "intent": "payment_mode"},
                {"question": "What's your timeline for investment?", "intent": "timeline"}
            ],
            objection_responses={
                "not_interested": "I understand. Property investment is a big decision. May I take just one minute to explain the opportunity?",
                "no_budget": "We have options starting from 25 lakhs with easy EMI plans.",
                "already_invested": "That's great! Would you like to diversify your portfolio with a new location?"
            },
            appointment_pitch="Would you like to schedule a free site visit this weekend? We provide complimentary pickup and drop.",
            callback_offer="I'll send the brochure on WhatsApp. Can I call you tomorrow morning to discuss?",
            closing="Thank you for your time. Have a great day!"
        )
    
    @classmethod
    def _solar_script(cls) -> CallScript:
        """Solar energy script"""
        return CallScript(
            name="Solar Energy Lead Generation",
            niche="solar",
            language="hinglish",
            greeting="Hello, namaste! Main {agent_name} bol raha/rahi hoon.",
            introduction="{client_name} se call kar raha/rahi hoon - hum solar energy solutions provide karte hain.",
            permission_ask="Ek minute hai aapke paas?",
            value_proposition="Apni electricity bill 90% tak kam karein solar panels lagwa ke. Government subsidy bhi available hai.",
            key_benefits=[
                "Bijli bill 90% tak kam",
                "25 saal ki warranty",
                "Government subsidy 40% tak",
                "6-7 saal mein poora payback"
            ],
            social_proof="Humne 5000+ homes aur businesses mein solar lagaya hai.",
            qualification_questions=[
                {"question": "Aapka monthly bijli bill approximately kitna aata hai?", "intent": "bill_amount"},
                {"question": "Aapke paas khud ki property hai ya rent pe hain?", "intent": "ownership"},
                {"question": "Terrace ya rooftop available hai solar panels ke liye?", "intent": "space_available"},
                {"question": "Kya aapne government subsidy ke baare mein suna hai?", "intent": "subsidy_awareness"}
            ],
            objection_responses={
                "too_expensive": "Initial cost lagta hai zyada, lekin 6-7 saal mein poora payback ho jata hai. Uske baad 20 saal free bijli!",
                "rented_property": "Accha, lekin kya owner se baat kar sakte hain? Unka property value bhi badhega.",
                "not_sure": "Bilkul, big decision hai. Free site survey karwa lo - exact savings calculate karke batate hain.",
                "already_have": "Great! Kya current system se satisfied hain? Hum upgrade ya maintenance bhi offer karte hain."
            },
            appointment_pitch="Free site survey schedule karein - engineer aayega, exact savings calculate karega. Koi commitment nahi.",
            callback_offer="WhatsApp pe case study bhej deta hoon - similar size ke customer ki actual savings. Kal discuss karein?",
            closing="Thank you! Survey confirm karne ke liye message aayega. Good day!"
        )
    
    @classmethod
    def _logistics_script(cls) -> CallScript:
        """Logistics/Transport script"""
        return CallScript(
            name="Logistics Lead Generation",
            niche="logistics",
            language="hinglish",
            greeting="Hello, namaste! {client_name} se {agent_name} bol raha/rahi hoon.",
            introduction="Hum B2B logistics aur transportation solutions provide karte hain.",
            permission_ask="Do minute hain aapke paas?",
            value_proposition="Apna transportation cost 20-30% kam karein humare fleet network ke through. Pan-India coverage hai.",
            key_benefits=[
                "20-30% cost saving",
                "Real-time GPS tracking",
                "Pan-India network",
                "Dedicated relationship manager"
            ],
            social_proof="500+ manufacturers aur distributors humare partners hain.",
            qualification_questions=[
                {"question": "Aap mainly kya goods transport karte hain?", "intent": "goods_type"},
                {"question": "Monthly approximately kitne trips hote hain?", "intent": "volume"},
                {"question": "Kaunse routes pe mainly transport hota hai?", "intent": "routes"},
                {"question": "Current logistics partner se satisfied hain?", "intent": "satisfaction"}
            ],
            objection_responses={
                "have_own_fleet": "Own fleet maintain karna expensive hai. Hybrid model try karein - peak load hum handle karenge.",
                "existing_partner": "Competition accha hai! Trial shipment karke compare kar lo - no commitment.",
                "not_now": "Samajh gaya. Kab season peak pe hota hai? Tab ke liye advance planning karein?"
            },
            appointment_pitch="Ek meeting schedule karein - custom quote prepare karke aaunga. Office mein ya video call, jo convenient ho.",
            callback_offer="Requirements email kar do, detailed proposal bhej dunga. Kal follow up karun?",
            closing="Thank you! Quote bhejne ke baad call karunga. Good day!"
        )
    
    @classmethod
    def _digital_marketing_script(cls) -> CallScript:
        """Digital marketing agency script"""
        return CallScript(
            name="Digital Marketing Lead Generation",
            niche="digital_marketing",
            language="hinglish",
            greeting="Hello! Main {agent_name}, {client_name} se bol raha/rahi hoon.",
            introduction="Hum businesses ko digital marketing ke through grow karne mein help karte hain.",
            permission_ask="Ek minute spare kar sakte hain?",
            value_proposition="Apne business ki online presence badhaiye aur leads generate karo. ROI focused approach hai humara.",
            key_benefits=[
                "Leads mein 3x increase",
                "Google pe first page ranking",
                "Social media pe brand building",
                "Performance based pricing option"
            ],
            social_proof="200+ brands ke saath kaam kiya hai - 50% repeat clients hain.",
            qualification_questions=[
                {"question": "Currently digital marketing karwa rahe hain ya in-house kar rahe hain?", "intent": "current_status"},
                {"question": "Website hai aapki? Monthly traffic kitna hai approximately?", "intent": "website_status"},
                {"question": "Main business channel kaunsa hai - B2B ya B2C?", "intent": "business_type"},
                {"question": "Monthly marketing budget approximately kitna hai?", "intent": "budget"}
            ],
            objection_responses={
                "doing_inhouse": "In-house team ke saath coordination kar sakte hain. Specialized work hum handle karenge.",
                "tried_before": "Kya specifically kaam nahi kiya? Humara approach different hai - results show karke fees lete hain.",
                "no_budget": "Start small karein - 15k/month se bhi effective campaign ho sakti hai.",
                "no_results_expected": "Guarantee nahi de sakte, lekin past results share kar sakta hoon. Similar industry ke case studies hain."
            },
            appointment_pitch="Free audit karwa lo website aur social media ka. Detailed report dunga with action items.",
            callback_offer="Competitors ka analysis bhej deta hoon - wo kya kar rahe hain. Kal discuss karein?",
            closing="Thank you! Audit report 2 din mein aayegi. Good day!"
        )
    
    @classmethod
    def _manufacturing_script(cls) -> CallScript:
        """Manufacturing/Industrial script"""
        return CallScript(
            name="Manufacturing Lead Generation",
            niche="manufacturing",
            language="hinglish",
            greeting="Hello, namaste! {client_name} se {agent_name} bol raha hoon.",
            introduction="Hum industrial {product_category} manufacturers hain - OEM aur bulk supply karte hain.",
            permission_ask="Procurement in-charge hain aap? Ek minute hai?",
            value_proposition="Quality products at competitive prices. Direct manufacturer hain - distributor margin nahi hai.",
            key_benefits=[
                "Factory direct pricing",
                "Customization available",
                "Bulk order discounts",
                "Timely delivery commitment"
            ],
            social_proof="100+ companies ko regular supply karte hain including some MNCs.",
            qualification_questions=[
                {"question": "Currently {product_category} kahan se le rahe hain?", "intent": "current_supplier"},
                {"question": "Monthly requirement approximately kitni hai?", "intent": "volume"},
                {"question": "Kya specific quality standards follow karte hain? ISO, etc?", "intent": "quality_requirements"},
                {"question": "Payment terms kya prefer karte hain?", "intent": "payment_terms"}
            ],
            objection_responses={
                "satisfied_supplier": "Competition healthy hai! Trial order se quality compare kar lo. No obligation.",
                "quality_concern": "Factory visit arrange kar sakte hain. Quality certifications bhi share karunga.",
                "price_issue": "Volume based pricing hai. Requirements batao, best quote dunga."
            },
            appointment_pitch="Factory visit arrange karein - production facility dikhaenge. Sample bhi le jaana.",
            callback_offer="Product catalog aur price list bhej deta hoon. Kal procurement team ke saath discuss karein?",
            closing="Thank you! Quotation email pe bhej dunga. Good day!"
        )
    
    @classmethod
    def _insurance_script(cls) -> CallScript:
        """Insurance script"""
        return CallScript(
            name="Insurance Lead Generation",
            niche="insurance",
            language="hinglish",
            greeting="Hello, namaste! Main {agent_name}, {client_name} insurance se bol raha/rahi hoon.",
            introduction="Aapke family ki financial security ke liye best insurance plans offer karte hain.",
            permission_ask="Do minute denge mujhe?",
            value_proposition="Tax savings ke saath future planning - aapke goals ke according customized plans.",
            key_benefits=[
                "Tax benefit Section 80C/80D",
                "Comprehensive coverage",
                "Easy claim process",
                "Premium waiver on critical illness"
            ],
            social_proof="10 lakh+ customers ne humpe trust kiya hai.",
            qualification_questions=[
                {"question": "Currently koi life insurance hai aapke paas?", "intent": "existing_policy"},
                {"question": "Family mein kaun kaun hain - spouse, children?", "intent": "family_status"},
                {"question": "Monthly kitna invest kar sakte hain insurance mein?", "intent": "budget"},
                {"question": "Main priority kya hai - savings, protection, ya dono?", "intent": "priority"}
            ],
            objection_responses={
                "already_have": "Bahut accha! Kya existing coverage sufficient hai? Free policy review karwa lo.",
                "not_now": "Jitna jaldi loge, premium utna kam. Age badhne pe premium badhta hai.",
                "too_expensive": "Budget ke according plan customize ho sakta hai. 500 rupaye daily se bhi start kar sakte hain.",
                "dont_trust": "Valid concern hai. IRDA registered hain hum. Claim settlement ratio 98% hai."
            },
            appointment_pitch="Free financial planning session le lo - ghar pe aake explain karunga. No obligation.",
            callback_offer="Brochure WhatsApp karun? Sunday ko family ke saath baith ke discuss karein.",
            closing="Thank you! Appointment confirm karne ke liye call karunga. Good day!"
        )
    
    @classmethod
    def get_response_for_objection(
        cls,
        script: CallScript,
        objection_type: str
    ) -> str:
        """Get response for a specific objection"""
        return script.objection_responses.get(
            objection_type,
            "Main samajh sakta/sakti hoon aapki concern. Kya main ek aur angle se explain karun?"
        )
    
    @classmethod
    def get_qualification_question(
        cls,
        script: CallScript,
        answered_intents: List[str]
    ) -> Optional[Dict[str, str]]:
        """Get next unanswered qualification question"""
        for q in script.qualification_questions:
            if q["intent"] not in answered_intents:
                return q
        return None
    
    @classmethod
    def format_script_with_variables(
        cls,
        text: str,
        variables: Dict[str, str]
    ) -> str:
        """Replace variables in script text"""
        for key, value in variables.items():
            text = text.replace(f"{{{key}}}", value)
        return text
