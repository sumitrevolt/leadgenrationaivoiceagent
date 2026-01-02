"""
Platform Self-Selling Scripts
Scripts for YOUR COMPANY to sell the voice agent service to potential clients

These scripts are used when the platform calls B2B leads to sell your service.
"""
from typing import Dict, List
from dataclasses import dataclass

from app.scripts.script_loader import CallScript


@dataclass
class PlatformScript(CallScript):
    """Extended script for platform sales"""
    pricing_tiers: Dict[str, str] = None
    demo_offer: str = ""
    trial_offer: str = ""


class PlatformScripts:
    """
    Scripts for selling YOUR voice agent service to businesses
    """
    
    @classmethod
    def get_sales_script(cls, language: str = "hinglish") -> PlatformScript:
        """Main script for selling voice agent service"""
        
        if language == "hinglish":
            return cls._get_hinglish_sales_script()
        elif language == "english":
            return cls._get_english_sales_script()
        else:
            return cls._get_hinglish_sales_script()
    
    @classmethod
    def _get_hinglish_sales_script(cls) -> PlatformScript:
        """Hinglish script for selling to Indian businesses"""
        return PlatformScript(
            name="Platform Sales - Hinglish",
            niche="platform_sales",
            language="hinglish",
            
            greeting="Hello, Namaste! Main LeadGen AI Solutions se bol raha/rahi hoon.",
            
            introduction="""Hum businesses ko AI-powered voice agent provide karte hain 
            jo automatically aapke liye leads generate karta hai aur customers ko call karta hai.
            Kya aapke paas do minute hain?""",
            
            permission_ask="Kya main briefly batao ki yeh aapke business ke liye kaise helpful ho sakta hai?",
            
            value_proposition="""Socho agar ek AI agent 24/7 aapke potential customers ko call kare, 
            unhe qualify kare, aur directly aapke calendar mein appointments book kare - 
            bina kisi human intervention ke. Yahi hum offer karte hain.""",
            
            key_benefits=[
                "100% Automated lead generation - no manual effort",
                "AI jo natural Hindi/English mein baat karta hai",
                "Automatically appointments book karta hai",
                "Real-time WhatsApp pe hot lead alerts",
                "CRM integration - HubSpot, Zoho, Google Sheets",
                "7-day FREE trial - no credit card required"
            ],
            
            social_proof="""Currently 200+ businesses humare platform use kar rahe hain.
            Ek real estate company ne pichle month 47 appointments book kiye sirf is AI se.
            Digital marketing agency ne apne lead generation cost 70% kam kiya.""",
            
            qualification_questions=[
                {
                    "question": "Aap currently leads kaise generate karte hain? Cold calling, ads, ya referrals?",
                    "intent": "current_method"
                },
                {
                    "question": "Aapki team mein kitne log sales calls handle karte hain?",
                    "intent": "team_size"
                },
                {
                    "question": "Monthly approximately kitni leads ki zaroorat hai aapko?",
                    "intent": "lead_volume"
                },
                {
                    "question": "Aapka target customer kaun hai - businesses ya consumers?",
                    "intent": "target_audience"
                },
                {
                    "question": "Currently marketing pe monthly kitna invest karte hain approximately?",
                    "intent": "budget"
                }
            ],
            
            objection_responses={
                "not_interested": """Main samajh sakta hoon, bahut companies initially skeptical hoti hain AI ke baare mein.
                    Lekin kya main ek real example share karun? Similar industry mein ek client ne 
                    first month mein hi 3x ROI dekha. Free trial hai - risk zero hai aapka.""",
                
                "already_have_team": """Bilkul, aapki team valuable hai! Yeh unhe replace nahi karta, 
                    unhe empower karta hai. AI initial calls handle karta hai, qualified leads team ko milte hain.
                    Aapki team ka time sirf hot leads pe lagta hai.""",
                
                "too_expensive": """Actually yeh bahut cost-effective hai. Ek sales person ki salary 
                    30-40K monthly hai, plus incentives. Humara starter plan sirf 15K mein 500 calls 
                    monthly - aur AI kabhi chutti nahi leta, kabhi mood off nahi hota!""",
                
                "not_now": """Bilkul, timing important hai. Lekin consider kariye - jab tak aap decide karenge,
                    aapke competitors already yeh use kar rahe honge. Free trial ke liye koi commitment nahi.
                    Kya next week ek demo schedule karein?""",
                
                "need_to_think": """Of course, smart decision hai properly evaluate karna. 
                    Main aapko WhatsApp pe case studies bhej deta hoon similar businesses ke.
                    Kal ya parso kab free hain review karne ke liye?""",
                
                "send_details": """Zaroor! Main abhi aapke WhatsApp pe detailed brochure bhej deta hoon
                    with pricing, features, aur case studies. Kal subah ek quick call karke 
                    questions answer kar dunga. Kya 10 baje theek hai?""",
                
                "ai_wont_work": """Valid concern hai. Actually humara AI natural conversation karta hai - 
                    log pehchaan nahi paate ki AI hai. Main ek sample call recording bhejun? 
                    Sunke khud decide kijiye.""",
                
                "my_industry_different": """Har industry unique hai, agreed. Isliye humara AI 
                    customizable hai. Aapke specific pitch, aapke products ke baare mein train hota hai.
                    Real estate, solar, logistics, insurance - sab mein successfully use ho raha hai."""
            },
            
            appointment_pitch="""Ek idea hai - 15-minute ka free demo le lo. 
            Main actually aapko live dikhaunga ki AI kaise call karta hai, kaise leads qualify karta hai.
            Screen share pe sab samajh aa jayega. Kal 3 baje ya parso 11 baje - kab suit karta hai?""",
            
            callback_offer="""Aap busy hain abhi, samajh gaya. Aapka convenient time batao, 
            main exactly usi time pe call karunga. Plus WhatsApp pe info bhej deta hoon 
            taaki aap free hoke padh sakein.""",
            
            closing="""Thank you for your time! Main aapko abhi WhatsApp pe details bhej raha hoon.
            Demo ke liye confirmation message aayega. Agar koi question ho, directly reply kar dena.
            Have a great day!""",
            
            # Platform-specific
            pricing_tiers={
                "trial": "7 days FREE - 100 calls, full features",
                "starter": "₹15,000/month - 500 calls",
                "growth": "₹25,000/month - 2000 calls",
                "enterprise": "₹50,000/month - Unlimited calls + Priority support"
            },
            
            demo_offer="15-minute live demo - see AI in action",
            
            trial_offer="7-day FREE trial - No credit card, no commitment"
        )
    
    @classmethod
    def _get_english_sales_script(cls) -> PlatformScript:
        """English script for selling to businesses"""
        return PlatformScript(
            name="Platform Sales - English",
            niche="platform_sales",
            language="english",
            
            greeting="Hello! This is a call from LeadGen AI Solutions.",
            
            introduction="""We provide AI-powered voice agents that automatically 
            generate leads and make calls for your business. Do you have two minutes?""",
            
            permission_ask="May I briefly explain how this can help your business?",
            
            value_proposition="""Imagine an AI agent that calls your potential customers 24/7, 
            qualifies them, and books appointments directly in your calendar - 
            with zero human intervention. That's exactly what we offer.""",
            
            key_benefits=[
                "100% Automated lead generation",
                "Natural AI conversations in Hindi/English",
                "Automatic appointment booking",
                "Real-time WhatsApp alerts for hot leads",
                "CRM integration - HubSpot, Zoho, Google Sheets",
                "7-day FREE trial - no credit card required"
            ],
            
            social_proof="""Currently 200+ businesses are using our platform.
            A real estate company booked 47 appointments last month using just the AI.
            A marketing agency reduced their lead generation cost by 70%.""",
            
            qualification_questions=[
                {
                    "question": "How do you currently generate leads? Cold calling, ads, or referrals?",
                    "intent": "current_method"
                },
                {
                    "question": "How many people in your team handle sales calls?",
                    "intent": "team_size"
                },
                {
                    "question": "Approximately how many leads do you need monthly?",
                    "intent": "lead_volume"
                },
                {
                    "question": "Who is your target customer - businesses or consumers?",
                    "intent": "target_audience"
                }
            ],
            
            objection_responses={
                "not_interested": """I understand. Many companies are initially skeptical about AI.
                    But let me share a real example - a client in a similar industry saw 3x ROI 
                    in the first month. There's a free trial - zero risk for you.""",
                
                "already_have_team": """Absolutely, your team is valuable! This doesn't replace them, 
                    it empowers them. AI handles initial calls, qualified leads go to your team.
                    Your team's time is spent only on hot prospects.""",
                
                "too_expensive": """Actually, it's very cost-effective. A sales person costs 
                    30-40K monthly plus incentives. Our starter plan is just 15K for 500 calls - 
                    and AI never takes leave, never has a bad day!"""
            },
            
            appointment_pitch="""Here's an idea - take a 15-minute free demo.
            I'll show you live how the AI makes calls and qualifies leads.
            Tomorrow at 3 PM or day after at 11 AM - what works for you?""",
            
            callback_offer="""You're busy now, I understand. Tell me your convenient time,
            I'll call exactly then. Plus I'll send info on WhatsApp so you can review it.""",
            
            closing="""Thank you for your time! I'm sending you details on WhatsApp now.
            You'll receive a demo confirmation. If you have questions, just reply directly.
            Have a great day!""",
            
            pricing_tiers={
                "trial": "7 days FREE - 100 calls, full features",
                "starter": "₹15,000/month - 500 calls",
                "growth": "₹25,000/month - 2000 calls",
                "enterprise": "₹50,000/month - Unlimited calls + Priority support"
            },
            
            demo_offer="15-minute live demo - see AI in action",
            trial_offer="7-day FREE trial - No credit card, no commitment"
        )
    
    @classmethod
    def get_followup_script(cls, followup_type: str) -> Dict:
        """Get follow-up scripts for different scenarios"""
        
        scripts = {
            "demo_reminder": {
                "message": """Hi! Kal aapka demo scheduled hai LeadGen AI Solutions ke saath.
                Timing: {time}. Join link bhej diya hai email pe.
                Koi question ho toh reply karein. See you tomorrow!""",
                "timing": "1 day before demo"
            },
            
            "trial_started": {
                "message": """🎉 Congratulations! Aapka 7-day FREE trial start ho gaya hai.
                
                Agle steps:
                1. Dashboard access: {dashboard_url}
                2. WhatsApp pe lead alerts aa jayenge
                3. Questions? Reply karein
                
                Let's generate some leads! 🚀""",
                "timing": "Immediately after trial start"
            },
            
            "trial_day_3": {
                "message": """Hi {name}! Aapke trial ke 3 din ho gaye.
                
                Ab tak:
                - {leads_scraped} leads scraped
                - {calls_made} calls made
                - {appointments} appointments booked
                
                Koi issue hai? Main help kar sakta hoon.
                Reply karein ya call schedule karein.""",
                "timing": "Day 3 of trial"
            },
            
            "trial_ending": {
                "message": """Hi {name}! Aapka trial kal end ho raha hai.
                
                Trial summary:
                - {total_leads} total leads
                - {total_calls} calls made
                - {appointments} appointments
                
                Continue karna chahenge? Special offer: 
                First month 20% OFF if you subscribe today!
                
                Reply YES to upgrade, or call {support_number}.""",
                "timing": "1 day before trial ends"
            },
            
            "trial_ended": {
                "message": """Hi {name}, aapka trial end ho gaya.
                
                Miss mat karo jo aapne build kiya:
                - {leads} leads database
                - Trained AI for your business
                
                Reactivate karo sirf ₹12,000/month (20% OFF) - 48 hours only!
                
                Reply START to reactivate.""",
                "timing": "After trial ends"
            },
            
            "no_response_followup": {
                "message": """Hi! Main pichle hafte call kiya tha LeadGen AI Solutions se.
                
                Quick recap: AI-powered lead generation - FREE trial available.
                
                200+ businesses already use kar rahe hain.
                
                Interested? Reply YES for a quick demo.
                Not interested? Reply STOP - no more messages.""",
                "timing": "3 days after no response"
            }
        }
        
        return scripts.get(followup_type, scripts["no_response_followup"])
    
    @classmethod
    def get_objection_handler(cls, objection: str) -> str:
        """Get response for specific objection"""
        script = cls.get_sales_script("hinglish")
        return script.objection_responses.get(
            objection,
            "Main samajh sakta hoon. Kya main ek different angle se explain karun?"
        )
