"""
Per-niche knowledge + objection playbook for all 25 niches.

`niches.py` me har niche ka TARGETING + PRICING config hai. Yeh module uska
*conversation* counterpart hai — har niche ke liye:

  - facts:      grounded, end-customer-facing knowledge (jo agent SACH-SACH bol
                sakta hai). DATA agent inhe client ke KB me seed karta hai aur
                LEADS agent inse grounded jawab deta hai (hallucination se bachne
                ke liye — natural_dialog ka anti-hallucination design).
  - benefits:   end customer ko kyun farak padta hai (3-5 short points).
  - objections: objection_key -> Hinglish rebuttal (LEADS agent ke liye).

Frame: LEADS agent client ke END CUSTOMER ko call karta hai (niche ka
`target_type`/`end_customer` dekho). Isliye facts/objections end-customer ki
bhasha me likhe hain, factual rakhe hain — jahan exact number/scheme vary karti
hai wahan "team exact detail confirm karwa degi" pe defer karte hain.

Keys EXACTLY app.niches.NICHES jaise hain. Naya niche add karte waqt yahan bhi
ek pack add karo; lookups `.get()` + generic fallback se safe hain.

Usage:
    from app.niche_knowledge import knowledge_facts, objection_response
    facts = knowledge_facts("solar_residential")
    rebut = objection_response("solar_residential", "too_expensive")
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any

# Common objection rebuttals jo har niche pe kaam aate hain (per-niche pack inhe
# override kar sakta hai). End-customer ke saath warm, non-pushy tone.
# NOTE: ye canonical CATEGORY keys hain — har category ka ek generic fallback hai
# taaki koi bhi niche bina apne specific rebuttal ke bhi kuch sahi bol sake.
_GENERIC_OBJECTIONS: Dict[str, str] = {
    "not_interested": "Bilkul samajhti hoon. Bas ek chhoti si baat — agar yeh aapke kaam ka na ho to main 1 minute me phone rakh deti hoon, par sun lijiye?",
    "busy": "Koi baat nahi, aap busy hain. Main aapko kis time call karoon jo aapke liye sahi rahe?",
    "send_details": "Zaroor, main WhatsApp pe detail bhej deti hoon. Bas 30 second me ek main baat bata doon taaki aapko pata ho kya bhej rahi hoon?",
    "think_about_it": "Bilkul, sochna chahiye. Main koi pressure nahi de rahi — ek choti detail bhej deti hoon, aap aaram se dekh lena.",
    "too_expensive": "Samajhti hoon. Aap apna budget batayein to main usi me best option nikaal deti hoon — aur EMI/flexible options bhi aksar hote hain.",
    "already_have": "Achhi baat hai! Ek baar free compare/review kar lijiye — ho sakta hai behtar option ya thodi bachat mil jaaye, koi commitment nahi.",
    "just_browsing": "Bilkul, abhi dekh-dekh rahe hain — samajh gayi. Main 1-2 options bhej deti hoon, jab man kare tab aage badhna, koi jaldi nahi.",
}

# Canonical category -> niche pack me jo synonym keys ho sakti hain (preference
# order). match_objection/objection_response pehle niche-specific wording dhoondte
# hain, phir generic fallback.
_OBJECTION_SYNONYMS: Dict[str, List[str]] = {
    "too_expensive": [
        "too_expensive", "expensive", "expensive_abroad", "expensive_amc",
        "price", "price_high", "price_negotiable", "rate_high", "high_capex",
        "fees", "fees_high", "budget", "budget_issue",
    ],
    "already_have": [
        "already_have", "already_have_broker", "already_coaching",
        "already_applying", "have_vendor", "have_supplier", "have_ca",
        "have_team", "have_loan", "existing_partner", "local_carpenter",
        "carpenter_cheaper",
    ],
    "just_browsing": [
        "just_browsing", "just_looking", "just_planning", "comparing",
    ],
    "think_about_it": [
        "think_about_it", "think", "need_to_discuss", "need_time",
        "not_decided", "not_sure", "later", "not_now",
    ],
    "busy": ["busy", "no_time", "later", "not_now"],
    "send_details": ["send_details", "send_quote", "send_proposal"],
    "not_interested": ["not_interested"],
}


NICHE_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    # ====================================================================== #
    # S-TIER
    # ====================================================================== #
    "real_estate": {
        "facts": [
            "Hum RERA-registered projects aur verified resale properties dono dikhate hain.",
            "Site visit free hai aur kai jagah pickup-drop bhi arrange ho jata hai.",
            "Home loan ke liye bank tie-ups hain — eligibility aur EMI samjhane me madad karte hain.",
            "Budget aur locality ke hisab se 2-3 best options shortlist karke dikhate hain, time waste nahi.",
            "Possession-ready aur under-construction dono options available hain.",
        ],
        "benefits": [
            "Aapke budget aur area me hi shortlisted options",
            "RERA-approved, clear-title properties",
            "Site visit + home loan dono me support",
            "Direct owner/builder connect — beech ka time bachta hai",
        ],
        "objections": {
            "just_browsing": "Bilkul, abhi dekh-dekh rahe hain — samajh gayi. Main WhatsApp pe 2-3 options bhej deti hoon, jab man kare tab site visit, koi jaldi nahi.",
            "already_have_broker": "Theek hai! Ek free site visit humare saath bhi le lijiye, compare karne me kya jaata hai — koi commitment nahi.",
            "budget_issue": "Budget flexible options bhi hain aur EMI bhi — ek baar dekh lijiye, phir decide karna aaram se.",
            "location_far": "Samajhti hoon. Aap kaunsa area prefer karte hain? Wahin ke options dhoondh ke bhejti hoon.",
        },
    },
    "real_estate_luxury": {
        "facts": [
            "₹2 crore+ ki premium aur luxury properties — confidentiality fully maintain hoti hai.",
            "NRI aur HNI investors ke liye end-to-end documentation aur virtual tours arrange karte hain.",
            "Hand-picked inventory: sea-view, gated, branded residences — sirf serious buyers ko.",
            "Private site visit aapke schedule ke hisab se, bina bheed ke arrange hota hai.",
        ],
        "benefits": [
            "Exclusive, off-market premium listings",
            "Poori privacy aur dedicated relationship manager",
            "NRI-friendly: virtual tour + remote paperwork",
            "Investment appreciation pe honest data",
        ],
        "objections": {
            "just_browsing": "Bilkul, is segment me soch-samajh ke hi liya jaata hai. Main ek curated list bhejti hoon — aaram se dekhiye.",
            "price_high": "Is category me value location aur exclusivity me hoti hai. Ek private viewing pe aapko khud farak dikhega.",
            "need_to_discuss": "Zaroor, family/partner se discuss kijiye. Detailed deck bhej deti hoon jise aap share kar sakein.",
        },
    },
    "studying_abroad": {
        "facts": [
            "USA, UK, Canada, Australia jaise countries me admission + visa dono me guidance dete hain.",
            "Profile ke hisab se university aur course shortlist karte hain — intake (Fall/Spring) ke saath.",
            "IELTS/TOEFL, SOP, LOR aur application me step-by-step help milti hai.",
            "Education loan aur scholarship options par bhi counseling hoti hai.",
            "Free counseling session me eligibility aur budget honestly batate hain.",
        ],
        "benefits": [
            "Profile-fit university aur course shortlist",
            "Visa + SOP + application end-to-end support",
            "Education loan aur scholarship guidance",
            "Intake deadlines miss nahi hoti",
        ],
        "objections": {
            "expensive_abroad": "Cost zyada lagti hai, par education loan + scholarship se kaafi manageable ho jaata hai — counseling me exact numbers samjha deti hoon.",
            "not_sure_country": "Koi baat nahi, country decide karna hi to hum help karte hain — aapke budget aur course ke hisab se best fit batate hain.",
            "already_applying": "Badhiya! Ek free profile review le lijiye — ho sakta hai koi behtar university ya scholarship miss ho rahi ho.",
        },
    },
    "home_loans": {
        "facts": [
            "Hum DSA hain — ek saath kai banks/NBFC ke offers compare karke best rate dilate hain.",
            "Home loan, balance transfer aur loan-against-property — teeno me help.",
            "Eligibility income, CIBIL score aur existing EMIs par depend karti hai — pehle free check karte hain.",
            "Document list pehle se de dete hain taaki sanction jaldi ho.",
            "Balance transfer se purani loan ka interest kaafi kam ho sakta hai.",
        ],
        "benefits": [
            "Multiple banks ke rates ek jagah compare",
            "Balance transfer se EMI/interest bachat",
            "Document-ready process — fast sanction",
            "Eligibility ka honest free assessment",
        ],
        "objections": {
            "already_have_loan": "Achha! Aapki current rate kya hai? Balance transfer se aksar 0.5-1% tak bachat ho jaati hai — ek baar check karwa lijiye, free hai.",
            "rate_high": "Rate banks ke saath negotiate karte hain — aapki profile strong hui to behtar offer milta hai. Pehle eligibility dekh lein?",
            "not_now": "Koi baat nahi. Main eligibility ek baar check karke bata deti hoon — jab loge tab kaam aayega, paperwork ready rahega.",
        },
    },
    "solar_residential": {
        "facts": [
            "Rooftop solar se bijli bill 80-90% tak kam ho sakta hai, system 25 saal tak chalta hai.",
            "PM Surya Ghar Muft Bijli Yojana ke tahat subsidy milti hai (3kW tak achhi subsidy) — exact amount system size par.",
            "Net metering se extra bijli grid ko bech ke credit milta hai.",
            "Free site survey hota hai — roof, shadow aur bill dekh ke exact savings batate hain.",
            "EMI option bhi hota hai — aksar EMI aapke bijli bill se kam padti hai.",
        ],
        "benefits": [
            "Bijli bill me 80-90% bachat",
            "Government subsidy + net metering benefit",
            "25-saal lamba system life",
            "Free site survey, koi commitment nahi",
        ],
        "objections": {
            "too_expensive": "Subsidy aur EMI ke baad cost kaafi reasonable ho jaati hai — aur monthly EMI aksar aapke bijli bill se kam hoti hai. Free survey me exact figure bata denge.",
            "roof_not_suitable": "Yeh to engineer survey me hi pakka pata chalta hai — survey bilkul free hai, suitable na ho to bhi koi charge nahi.",
            "need_to_discuss": "Bilkul, ghar me discuss kijiye. Main ek detailed savings estimate WhatsApp pe bhej deti hoon.",
            "tenant": "Samajh gayi, ghar rent pe hai. Owner se baat ho sake to unka property value bhi badhta hai — number de sakein?",
        },
    },
    "solar_commercial": {
        "facts": [
            "Factory/warehouse rooftop par C&I solar se monthly power cost kaafi gir jaata hai.",
            "CAPEX (khud lagao) aur OPEX/PPA (zero investment, per-unit rate) dono models hote hain.",
            "Payback aksar 3-5 saal, uske baad 20+ saal lagभग free power.",
            "Roof area, sanctioned load aur bill dekh ke feasibility report banate hain.",
            "Accelerated depreciation jaisa tax benefit business ko milta hai.",
        ],
        "benefits": [
            "Bijli ka per-unit cost teji se kam",
            "Zero-investment OPEX/PPA option",
            "3-5 saal payback, 20+ saal benefit",
            "Tax depreciation benefit",
        ],
        "objections": {
            "high_capex": "CAPEX nahi lagana to OPEX/PPA model hai — zero investment, aap sirf bijli ke per-unit ka kam rate dete ho. Discuss karein?",
            "roof_doubt": "Roof suitability free feasibility study me confirm karte hain — load aur area dekh ke exact bata denge.",
            "send_proposal": "Zaroor, ek tailored proposal bhejti hoon. Aapka average monthly bill kitna aata hai taaki numbers accurate hon?",
        },
    },
    "insurance": {
        "facts": [
            "Hum IRDAI-registered hain — health, term aur dono ke plans compare karke dete hain.",
            "Term insurance saste premium me badi cover deta hai; health insurance medical kharch cover karta hai.",
            "Premium par 80C/80D ke tahat tax benefit milta hai.",
            "Time pe renewal se no-claim bonus aur continuity benefit bana rehta hai.",
            "Age kam ho to premium bhi kam — jaldi lena faydemand hota hai.",
        ],
        "benefits": [
            "Kai companies ke plans ek jagah compare",
            "Tax benefit (80C/80D)",
            "Claim aur renewal me personal support",
            "Family ke liye sahi cover ka guidance",
        ],
        "objections": {
            "already_have": "Badiya! Ek free policy review karwa lijiye — aksar cover kam ya premium zyada hota hai, theek karwa sakte hain.",
            "too_expensive": "Budget ke hisab se plan customize ho jaata hai — rozana ₹20-30 jitna bhi start point ho sakta hai. Aapka budget batayein?",
            "dont_trust": "Sahi concern hai. Hum IRDAI-registered hain aur claim settlement record transparent hai — kuch bhi commit karne se pehle aap verify kar sakte hain.",
            "later": "Theek hai, par age badhne pe premium badhta hai — abhi ka quote lock karwa deti hoon, lena tab decide karna.",
        },
    },
    "coaching": {
        "facts": [
            "NEET/JEE/UPSC aur board exams ke liye experienced faculty aur structured batches.",
            "Free demo class aur scholarship test se fee me concession mil sakta hai.",
            "Regular mock tests, doubt-clearing aur study material included.",
            "Online aur offline dono batch options, outstation ke liye hostel guidance.",
            "Counseling me student ke level ke hisab se sahi batch suggest karte hain.",
        ],
        "benefits": [
            "Experienced faculty + small batches",
            "Free demo class + scholarship test",
            "Mock tests aur doubt sessions",
            "Online/offline flexibility",
        ],
        "objections": {
            "fees_high": "Fees quality ke hisab se hai, aur scholarship test se concession milta hai — EMI option bhi hai. Demo class free me dekh lijiye pehle.",
            "already_coaching": "Koi baat nahi, ek free demo class attend kar lijiye aur compare kar lijiye — bilkul commitment nahi.",
            "results_doubt": "Bilkul sahi sawaal — counseling me hum pichhle results aur selections detail me dikhate hain.",
            "too_far": "Online batch bhi same faculty ke saath available hai, ya hostel guidance bhi de dete hain.",
        },
    },

    # ====================================================================== #
    # A-TIER
    # ====================================================================== #
    "interior_designers": {
        "facts": [
            "Turnkey interior — design se execution tak ek hi jagah, fixed timeline ke saath.",
            "3D design pehle dikhate hain taaki aapko ghar ka look pehle hi clear ho.",
            "Budget band ke hisab se material aur finishes suggest karte hain.",
            "Modular kitchen, wardrobes aur full-home dono projects.",
            "Free design consultation me requirement aur budget samajhte hain.",
        ],
        "benefits": [
            "Turnkey: design + execution ek chhat ke neeche",
            "3D design pehle se",
            "Budget ke hisab se options",
            "Defined timeline aur warranty",
        ],
        "objections": {
            "expensive": "Budget aap batayein, hum usi me best design nikal dete hain — phir aap decide karein. Consultation free hai.",
            "just_planning": "Bilkul, planning stage best hota hai baat karne ka — taaki budget aur layout pehle se clear ho. 3D idea bhej deti hoon.",
            "local_carpenter": "Carpenter theek hai, par turnkey me warranty, timeline aur finish ki guarantee milti hai — ek baar quote compare kar lijiye.",
        },
    },
    "modular_kitchen": {
        "facts": [
            "Modular kitchen factory-finished hoti hai — better durability aur clean finish.",
            "Material options: HDHMR/plywood, soft-close fittings, warranty ke saath.",
            "Kitchen size aur layout (L/U/parallel) ke hisab se quote banate hain.",
            "Showroom visit ya site measurement free hota hai.",
            "Branded fittings (Hettich/Blum jaise) ke options available.",
        ],
        "benefits": [
            "Factory-finished, durable build",
            "Warranty + branded fittings",
            "Layout ke hisab se custom quote",
            "Free showroom/site visit",
        ],
        "objections": {
            "carpenter_cheaper": "Carpenter sasta lagta hai, par modular me warranty, finish aur soft-close ki life zyada hoti hai — long term me value better.",
            "budget": "Budget batayein to usi me best material suggest karti hoon — aur EMI option bhi hai.",
            "just_looking": "Bilkul, ek baar showroom dekh lijiye ya 2-3 design bhej deti hoon — idea clear ho jaayega.",
        },
    },
    "dental_implants": {
        "facts": [
            "Dental implants natural daant jaise hote hain aur sahi care me bahut saal chalte hain.",
            "Single tooth se full-mouth tak treatment, aur aligners (clear braces) bhi.",
            "Pehle consultation me X-ray/jaanch ke baad exact plan aur cost batate hain.",
            "EMI/payment plans available hote hain high-value treatments ke liye.",
            "Experienced implantologist aur modern equipment.",
        ],
        "benefits": [
            "Natural-looking, long-lasting implants",
            "Single tooth se full-mouth tak",
            "EMI/payment plans",
            "Proper consultation + scan ke baad plan",
        ],
        "objections": {
            "expensive": "Implant ek one-time long-term investment hai aur EMI option bhi hai — consultation me exact cost aur plan samjha denge.",
            "scared": "Bilkul samajhti hoon, dar lagna normal hai — aaj ke implants kaafi comfortable hote hain. Doctor se ek baar baat kar lijiye, koi pressure nahi.",
            "think": "Zaroor sochiye. Ek consultation slot rakh deti hoon — jaanch ke baad clear ho jaayega, decide aap karna.",
        },
    },
    "hair_transplant": {
        "facts": [
            "Hair transplant (FUE/FUT) ek one-time procedure hai, natural results deta hai.",
            "Grafts ki sankhya aur cost scalp dekh ke consultation me decide hoti hai.",
            "EMI/payment options high-value procedures ke liye available.",
            "Procedure ke baad recovery aur care ki poori guidance milti hai.",
            "Experienced surgeon aur hygienic setup.",
        ],
        "benefits": [
            "One-time, natural-looking result",
            "EMI options",
            "Consultation me clear graft + cost plan",
            "Post-procedure care guidance",
        ],
        "objections": {
            "expensive": "Yeh one-time hota hai, baar-baar ka kharch nahi — aur EMI bhi hai. Consultation me exact grafts aur cost bata denge.",
            "will_it_work": "Sahi sawaal — result aapke scalp aur donor area par depend karta hai, jo consultation me doctor clearly batate hain.",
            "later": "Theek hai. Ek free consultation karwa lijiye taaki aapko options pata hon, decide aap aaram se karna.",
        },
    },
    "ivf_clinics": {
        "facts": [
            "IVF aur fertility treatments ke liye experienced doctors aur counseling support.",
            "Pehli consultation me history samajh ke personalized plan banate hain.",
            "Success rate age aur medical condition par depend karta hai — honestly counseling me batate hain.",
            "Privacy aur empathy fully maintain hoti hai.",
            "Treatment cost aur cycle ka clear breakdown dete hain.",
        ],
        "benefits": [
            "Experienced fertility specialists",
            "Personalized, empathetic counseling",
            "Privacy fully maintained",
            "Cost aur process transparent",
        ],
        "objections": {
            "expensive": "Samajhti hoon, yeh badi cycle hoti hai — clinic me cost ka clear breakdown aur options batate hain, kuch jagah EMI bhi.",
            "scared_unsure": "Bilkul natural hai aisa feel hona. Ek counseling session me doctor sab aaram se samjhate hain, koi pressure nahi.",
            "need_time": "Zaroor time lijiye. Jab ready hon, ek consultation rakh deti hoon — aap sab samajh ke decide karna.",
        },
    },
    "immigration": {
        "facts": [
            "Canada PR (Express Entry), Australia PR aur kai countries ke liye guidance.",
            "Eligibility points (age, education, experience, IELTS) ka free assessment karte hain.",
            "Documentation aur application step-by-step handle karne me madad.",
            "Process timelines aur realistic expectations honestly batate hain.",
            "Registered/experienced consultants ke through case file hota hai.",
        ],
        "benefits": [
            "Free eligibility points assessment",
            "Country/program ka sahi fit",
            "Documentation me end-to-end support",
            "Honest timeline + cost",
        ],
        "objections": {
            "is_it_genuine": "Bilkul valid concern. Hum sirf eligibility ke hisab se honest guidance dete hain — koi jhootha promise nahi, aur process aap verify kar sakte hain.",
            "expensive": "Fees process aur country par depend karti hai — pehle free eligibility check karte hain, phir aap decide karein.",
            "not_sure": "Pehle yeh dekhte hain ki aap eligible bhi hain ya nahi — woh free hai. Phir aage badhna ya nahi, aapki marzi.",
        },
    },
    "wedding_venues": {
        "facts": [
            "Banquet/lawn capacity, available dates aur packages ke hisab se options dikhate hain.",
            "Veg/non-veg catering, decor aur AV arrangements customizable hote hain.",
            "Wedding season me dates jaldi book ho jaati hain — early booking better.",
            "Site visit pe venue, parking aur rooms dikha dete hain.",
            "Corporate events/MICE ke liye bhi setup available.",
        ],
        "benefits": [
            "Date + guest-count ke hisab se options",
            "Catering + decor customizable",
            "Site visit pe sab clear",
            "Season ke liye early lock",
        ],
        "objections": {
            "comparing": "Bilkul compare kijiye — ek site visit le lijiye taaki venue real me dekh sakein, photos se behtar lagta hai.",
            "budget": "Aapka budget aur guest count batayein, usi me best package nikal deti hoon.",
            "date_far": "Koi baat nahi, par achhe venues season me jaldi book hote hain — date tentatively hold karwa sakte hain.",
        },
    },
    "used_cars": {
        "facts": [
            "Inspected, verified pre-owned cars — RC transfer aur paperwork me help.",
            "Finance aur exchange (purani gaadi dene) ke options available.",
            "Budget aur model ke hisab se test drive arrange karte hain.",
            "Kai cars par warranty/assurance bhi milti hai.",
            "Procurement ke liye agar aap car bechna chahein to bhi quote dete hain.",
        ],
        "benefits": [
            "Inspected + verified cars",
            "Finance + exchange option",
            "Test drive aapke time pe",
            "RC transfer paperwork support",
        ],
        "objections": {
            "just_looking": "Bilkul, dekhna to banta hai — aap budget aur model batayein, main 2-3 best options bhej deti hoon.",
            "price_negotiable": "Price par baat ho sakti hai — aap pasand to kijiye, test drive ke baad number final karte hain.",
            "condition_doubt": "Har car inspected hoti hai aur aap khud check kar sakte hain — kai par warranty bhi hai.",
        },
    },
    "upskilling": {
        "facts": [
            "Industry-relevant courses (data, tech, management, design) with certificate.",
            "Live + recorded classes, doubt support aur projects.",
            "Placement assistance/career support kai programs me hota hai.",
            "EMI aur no-cost EMI options available.",
            "Counseling me career goal ke hisab se sahi program suggest karte hain.",
        ],
        "benefits": [
            "Job-relevant skills + certificate",
            "Live + recorded flexibility",
            "Placement/career support",
            "EMI options",
        ],
        "objections": {
            "expensive": "EMI aur no-cost EMI options hote hain — aur skill se salary/role upgrade hota hai. Counseling me ROI samjha deti hoon.",
            "no_time": "Recorded classes + weekend batch hote hain, working professionals ke hisab se design kiye gaye hain.",
            "will_i_get_job": "Placement guarantee har jagah alag hoti hai — hum honestly batate hain kya support milta hai aur past outcomes kya rahe.",
        },
    },
    "recruitment": {
        "facts": [
            "Permanent hiring aur staffing dono — screened, relevant candidates dete hain.",
            "Role aur skill ke hisab se candidates shortlist karke bhejte hain.",
            "Kai placements par replacement guarantee period hota hai.",
            "Bulk/volume hiring ke liye fast turnaround.",
            "Fees aksar success-based (placement hone par) hoti hai.",
        ],
        "benefits": [
            "Pre-screened, relevant candidates",
            "Replacement guarantee period",
            "Fast turnaround for bulk hiring",
            "Success-based fees",
        ],
        "objections": {
            "have_team": "Aapki internal team ke saath hum overflow/specialized roles handle karte hain — pressure kam hota hai.",
            "fees": "Fees aksar tabhi lagti hai jab placement ho jaaye — yaani risk kam. Roles batayein to model samjha deti hoon.",
            "tried_before": "Samajhti hoon. Ek role trial pe de dijiye — screened profiles dekh ke aap khud farak judge kar lijiye.",
        },
    },

    # ====================================================================== #
    # B-TIER
    # ====================================================================== #
    "hvac_commercial": {
        "facts": [
            "Commercial HVAC install + AMC (annual maintenance) dono provide karte hain.",
            "AMC se breakdown kam, equipment life zyada aur energy bill control me.",
            "Site load aur area dekh ke right-sized solution suggest karte hain.",
            "Retrofit/energy-efficiency upgrades se running cost girta hai.",
            "Response time aur SLA clearly define karte hain.",
        ],
        "benefits": [
            "Install + AMC ek hi vendor",
            "Kam downtime, lambi equipment life",
            "Energy cost optimization",
            "Defined SLA / response time",
        ],
        "objections": {
            "have_vendor": "Theek hai, par ek free site audit karwa lijiye — aksar AMC cost ya energy bill optimize ho jaata hai.",
            "expensive_amc": "AMC ek breakdown se sasta padta hai — unplanned repair aur downtime ka cost zyada hota hai. Numbers dikha deti hoon.",
            "send_quote": "Zaroor. Aapke setup ki tonnage/area bata dein to accurate quote bana ke bhejti hoon.",
        },
    },
    "b2b_suppliers": {
        "facts": [
            "Direct manufacturer/wholesaler — distributor margin ke bina competitive pricing.",
            "GST invoice, bulk discounts aur defined delivery timelines.",
            "MOQ (minimum order) aur customization options batate hain.",
            "Sample/trial order se quality verify kar sakte hain.",
            "RFQ ka jawab jaldi dete hain — der nahi.",
        ],
        "benefits": [
            "Factory-direct pricing",
            "GST invoice + bulk discount",
            "Sample/trial order possible",
            "Fast RFQ response",
        ],
        "objections": {
            "have_supplier": "Healthy competition achhi hai — ek trial order se quality aur rate compare kar lijiye, koi obligation nahi.",
            "price": "Volume ke hisab se best rate dete hain — aapki monthly requirement batayein to exact quote bhejti hoon.",
            "quality_doubt": "Sample/trial order se aap khud quality check kar sakte hain, aur certifications bhi share kar dete hain.",
        },
    },
    "travel_packages": {
        "facts": [
            "International + domestic packages — destination, dates aur budget ke hisab se customize.",
            "Visa assistance, flights, hotels aur sightseeing inclusions clear batate hain.",
            "Group aur private (FIT) dono options.",
            "Early booking par better rates aur availability.",
            "Itinerary pehle share karte hain taaki sab clear ho.",
        ],
        "benefits": [
            "Customizable itinerary",
            "Visa + flights + hotel ek package me",
            "Group ya private option",
            "Transparent inclusions",
        ],
        "objections": {
            "comparing": "Bilkul compare kijiye — main ek tailored itinerary aur quote bhej deti hoon taaki apples-to-apples compare ho.",
            "expensive": "Budget batayein, usi me best itinerary banati hoon — aur early booking se rate kam hota hai.",
            "not_decided": "Koi baat nahi. Aap destination/dates ka rough idea dein, main 1-2 options bhej deti hoon dekhne ke liye.",
        },
    },
    "packers_movers": {
        "facts": [
            "Household aur office shifting — packing material aur trained staff ke saath.",
            "Transit insurance option hota hai (saaman ke nuksan ke liye).",
            "Move date aur inventory size dekh ke instant quote.",
            "Intercity aur local dono routes, GST bill ke saath.",
            "Loading/unloading aur unpacking bhi cover hota hai.",
        ],
        "benefits": [
            "Trained staff + quality packing",
            "Transit insurance option",
            "GST bill + transparent quote",
            "Local + intercity",
        ],
        "objections": {
            "expensive": "Rate move size aur distance par depend karta hai — proper packing aur insurance ke saath safe shifting hoti hai. Exact quote de deti hoon.",
            "comparing": "Bilkul, compare kijiye — bas insurance aur packing quality bhi dekhiyega, sirf rate nahi.",
            "date_not_fixed": "Koi baat nahi, tentative date bata dijiye — main quote bhej deti hoon, confirm baad me kar lena.",
        },
    },
    "hotels_mice": {
        "facts": [
            "Corporate events, conferences aur banquets ke liye halls + AV setup.",
            "Capacity, catering aur rooms (out-station guests ke liye) arrange hote hain.",
            "Corporate rate contracts aur package deals available.",
            "Event size, dates aur budget dekh ke proposal banate hain.",
            "Dedicated event coordinator milta hai.",
        ],
        "benefits": [
            "Hall + AV + catering one-stop",
            "Corporate package rates",
            "Rooms for outstation guests",
            "Dedicated event coordinator",
        ],
        "objections": {
            "comparing": "Zaroor compare kijiye — ek site visit ya virtual walkthrough karwa deti hoon taaki venue real me dikhe.",
            "budget": "Event size aur budget batayein, usi me best package banati hoon.",
            "date_tentative": "Tentative date bhi chalega — availability check karke hold karwa deti hoon.",
        },
    },
    "digital_marketing": {
        "facts": [
            "SEO, performance ads aur social media — ROI-focused approach.",
            "Free audit me website/social ki current performance dikhate hain.",
            "Industry ke hisab se strategy, monthly reporting ke saath.",
            "Retainer ya project dono models; white-label partnership bhi.",
            "Clear KPIs (leads/traffic) define karke kaam karte hain.",
        ],
        "benefits": [
            "ROI-focused, KPI-driven",
            "Free audit pehle",
            "Transparent monthly reporting",
            "Retainer/project flexibility",
        ],
        "objections": {
            "doing_inhouse": "In-house team ke saath hum specialized kaam (ads/SEO) handle kar sakte hain — coordination easy.",
            "tried_before": "Samajhti hoon, sabka result alag hota hai — humara approach audit + clear KPI se shuru hota hai. Free audit dekh lijiye.",
            "expensive": "Chhote retainer se bhi effective campaign shuru ho sakti hai — budget batayein, plan banati hoon.",
        },
    },
    "ca_legal": {
        "facts": [
            "GST, ITR, ROC compliance, bookkeeping aur company registration — sab ek jagah.",
            "Compliance deadlines track karke timely filing karte hain (penalty se bachav).",
            "Startups/SMBs ke liye affordable retainer packages.",
            "IP/trademark aur basic legal documentation me bhi help.",
            "Pehli consultation me requirement aur scope clear karte hain.",
        ],
        "benefits": [
            "GST/ITR/ROC sab ek jagah",
            "Deadline tracking — no penalty",
            "Affordable SMB retainer",
            "Startup-friendly guidance",
        ],
        "objections": {
            "have_ca": "Achhi baat hai — ek free review karwa lijiye, ho sakta hai koi compliance ya tax saving miss ho rahi ho.",
            "expensive": "Retainer aapke business size ke hisab se hota hai — penalty aur late fees se to yeh kaafi sasta padta hai.",
            "not_now": "Koi baat nahi. Bas upcoming deadlines bata deti hoon taaki koi penalty na lage — jab chahein tab shuru karein.",
        },
    },
}


# Generic pack — unknown niche ya missing fields ke liye safe fallback.
_GENERIC_PACK: Dict[str, Any] = {
    "facts": [
        "Hum aapke business ke potential customers ko AI voice agent se call karke qualified leads laate hain.",
        "Aap sirf qualified result ke paise dete ho — koi bada fixed setup nahi.",
        "Demo free hai; 15 minute me dikha dete hain system kaise kaam karta hai.",
    ],
    "benefits": [
        "Qualified leads, kam mehnat",
        "Pay-per-result pricing",
        "Free demo",
    ],
    "objections": dict(_GENERIC_OBJECTIONS),
}


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def get_knowledge_pack(niche_key: Optional[str]) -> Dict[str, Any]:
    """Return the full pack for a niche (generic fallback for unknown keys)."""
    if not niche_key:
        return _GENERIC_PACK
    return NICHE_KNOWLEDGE.get(niche_key, _GENERIC_PACK)


def knowledge_facts(niche_key: Optional[str]) -> List[str]:
    """Grounded facts for a niche — DATA agent KB seed + LEADS agent grounding."""
    return list(get_knowledge_pack(niche_key).get("facts", []))


def niche_benefits(niche_key: Optional[str]) -> List[str]:
    """End-customer benefits for a niche."""
    return list(get_knowledge_pack(niche_key).get("benefits", []))


def objection_response(niche_key: Optional[str], objection_key: str) -> Optional[str]:
    """
    Objection rebuttal for a niche. Resolution order:
      1. niche pack me exact key ya uske synonyms (niche-specific wording).
      2. generic category fallback.
    Returns None only if category bilkul unknown ho.
    """
    pack = get_knowledge_pack(niche_key)
    obj = pack.get("objections", {})
    for syn in _OBJECTION_SYNONYMS.get(objection_key, [objection_key]):
        if syn in obj:
            return obj[syn]
    if objection_key in obj:
        return obj[objection_key]
    return _GENERIC_OBJECTIONS.get(objection_key)


# Free-form utterance keyword -> canonical objection category. Hindi + English
# dono cover karte hain taaki LEADS agent ka rule-based fallback richer ho.
_OBJECTION_KEYWORDS = [
    (("mehenga", "mehengi", "expensive", "costly", "zyada paisa", "zyada paise",
      "budget nahi", "afford", "paise nahi", "kitne ka", "kitna lagega"), "too_expensive"),
    (("dekh raha", "dekh rahi", "bas dekh", "sirf dekh", "browse", "browsing",
      "just looking", "abhi sirf", "compare", "compar"), "just_browsing"),
    (("already", "pehle se", "humara already", "existing", "already have",
      "ek aur", "lagaya hua", "pehle se hai"), "already_have"),
    (("busy", "abhi nahi", "baad me", "call later", "time nahi", "kaam me"), "busy"),
    (("soch", "think", "dekhungi", "dekhunga", "discuss", "ghar me baat",
      "family se", "samay", "time chahiye"), "think_about_it"),
    (("whatsapp", "email", "detail bhej", "bhej do", "send", "message kar"), "send_details"),
    (("not interested", "nahi chahiye", "interested nahi", "mat karo"), "not_interested"),
]


def match_objection(niche_key: Optional[str], utterance: str) -> Optional[str]:
    """
    Free-form utterance se best niche objection rebuttal nikaalo. Pehle niche ke
    apne objection key ka direct token match, phir keyword->category->synonym
    resolution (niche-specific wording > generic). None = no clear match.
    """
    if not utterance:
        return None
    low = utterance.lower()
    pack = get_knowledge_pack(niche_key)
    niche_obj = pack.get("objections", {})

    # 1) niche ki apni objection keys ka direct token match (e.g. "just looking")
    for key in niche_obj:
        token = key.replace("_", " ")
        if token in low:
            return niche_obj[key]

    # 2) keyword -> category -> niche synonym / generic fallback
    for words, category in _OBJECTION_KEYWORDS:
        if any(w in low for w in words):
            hit = objection_response(niche_key, category)
            if hit:
                return hit
    return None


__all__ = [
    "NICHE_KNOWLEDGE",
    "get_knowledge_pack",
    "knowledge_facts",
    "niche_benefits",
    "objection_response",
    "match_objection",
]
