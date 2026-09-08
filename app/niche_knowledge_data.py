"""Niche knowledge base — per-niche facts / benefits / objections data.

Extracted from app/niche_knowledge.py (2026-06-20 refactor) to separate ~1000 lines
of pure data from the logic helpers. Re-exported by niche_knowledge.py so
`from app.niche_knowledge import NICHE_KNOWLEDGE` keeps working everywhere.
"""

from typing import Any

NICHE_KNOWLEDGE: dict[str, dict[str, Any]] = {
    # ====================================================================== #
    # S-TIER
    # ====================================================================== #
    "ai_marketing": {
        "facts": [
            "Package me AI social media posts, festival posters, Google Business Profile optimization aur WhatsApp content sab included hai.",
            "Advanced plan me AI voice agent har website/Google inquiry ko 2 minute ke andar khud call karta hai — Hindi me, insaan jaisi awaaz.",
            "Dhanda jaise apps sirf content dete hain; hum content + AI calling dono ek package me dete hain — India me aur koi nahi deta.",
            "Plans ₹2,999/mahina se shuru hote hain — agency retainers (₹15-25K/mo) se kaafi kam.",
            "FREE Google Business Profile audit milta hai — 0-100 score aur top fixes ke saath, bina koi charge.",
        ],
        "benefits": [
            "Roz ka content + festival posts automatic — aapka time zero lagta hai",
            "Har inquiry ko AI turant call karta hai — koi lead thandi nahi padti",
            "Google pe ranking improve hoti hai — naye customers khud aate hain",
            "₹100/din se kam me poora marketing department",
        ],
        "objections": {
            "too_expensive": "Sir ek customer ki value socho — ₹100/din me poora marketing department mil raha hai; ek bhi extra customer aaye to paisa vasool.",
            "already_have": "Agency ₹15-25K/mahina leti hai, hum ₹3K se shuru — aur AI inquiry calls bhi karta hai jo agency nahi karti. Free GBP audit se compare kar lijiye.",
            "think_about_it": "Bilkul sochiye sir — tab tak main aapka FREE Google Business audit karwa deti hoon, score saamne dekh ke aaram se decide kar lena.",
        },
    },
    "edtech_creators": {
        "facts": [
            "Course free demo/trial ke saath aata hai — pehle dekh lijiye, phir decide kijiye.",
            "Recorded lessons lifetime access ke saath milte hain, apne time pe padh sakte ho.",
            "Doubt-solving ke liye community/WhatsApp group hota hai — akele nahi atakte.",
            "Certificate aur practical projects milte hain jo resume/LinkedIn pe kaam aate hain.",
        ],
        "benefits": [
            "Apne pace pe seekho — job ya college ke saath bhi manageable",
            "Industry-relevant skills, sirf theory nahi",
            "Doubt support + community se motivation banta hai",
        ],
        "objections": {
            "too_expensive": "EMI aur scholarship options hote hain — aur ek skill se job/freelance income aapki fees se kahin zyada nikal aati hai. Free demo dekh ke value khud judge kar lijiye.",
            "think_about_it": "Bilkul sochiye — main free demo class ka access bhej deti hoon, content dekh ke aaram se decide karna.",
            "no_time": "Lessons recorded hain, roz 30 minute bhi kaafi hai — apne schedule ke hisab se chal sakta hai.",
        },
    },
    "hospital_appointments": {
        "facts": [
            "Aap symptom batayein, hum sahi department/doctor suggest karke OPD appointment book kar dete hain.",
            "Appointment ka confirmation aur reminder WhatsApp/SMS pe mil jaata hai — line me lagne ki zarurat nahi.",
            "Reschedule ya cancel bhi ek call/message me ho jaata hai.",
            "Reports aur follow-up ke liye bhi hum reminder bhejte hain taaki koi visit miss na ho.",
        ],
        "benefits": [
            "Bina lambi wait ke time-slot mil jaata hai",
            "Sahi doctor tak seedha pahunch — sahi department",
            "Reminder se follow-up miss nahi hota",
        ],
        "objections": {
            "too_expensive": "Consultation fee standard hi hai — hum sirf booking aasaan banate hain, koi extra charge nahi. Aapko slot aur doctor confirm karke bata dete hain.",
            "think_about_it": "Koi jaldi nahi — aap jab ready ho tab slot book kar dijiye, main aapke liye available timings WhatsApp pe bhej deti hoon.",
            "busy": "Samajhti hoon. Aap apna preferred din-time bata dijiye, us hisab se appointment fix kar deti hoon.",
        },
    },
    "finance_advisory": {
        "facts": [
            "Pehle aapke goals aur risk-comfort samajhte hain, phir hi koi plan suggest karte hain — ek-size-fits-all nahi.",
            "SIP chhoti amount (₹500/mahina) se bhi shuru ho sakti hai; insurance term plans ki cost aksar logon ke andaaze se kam hoti hai.",
            "Tax-saving (80C/80D) aur investment dono ek saath plan ho sakte hain.",
            "Exact returns market pe depend karte hain — hum realistic picture dete hain, jhoothe vaade nahi.",
        ],
        "benefits": [
            "Goal-based plan — sirf product bechna nahi",
            "Tax bachat + wealth dono ek saath",
            "Regular review — plan time ke saath adjust hota hai",
        ],
        "objections": {
            "too_expensive": "Shuruaat chhoti SIP se ho sakti hai — ₹500/mahina bhi. Pehle ek free goal-planning baithak kar lijiye, koi commitment nahi.",
            "think_about_it": "Bilkul, paise ka decision soch ke hi lena chahiye. Main ek simple goal-plan summary bhej deti hoon, aaram se dekh lena.",
            "not_interested": "Koi baat nahi — bas itna, jaldi shuru karne se compounding ka fayda zyada milta hai. Ek 2-minute summary bhej doon?",
        },
    },
    "cloud_kitchen": {
        "facts": [
            "Direct WhatsApp/phone order pe aksar Zomato/Swiggy se behtar rate aur portion milta hai.",
            "Roz ka fresh menu aur timing aapko WhatsApp pe mil jaata hai.",
            "Hygiene aur packaging ka dhyan rakha jaata hai — ghar tak safe delivery.",
            "Bulk/monthly tiffin plans pe special pricing hoti hai.",
        ],
        "benefits": [
            "Ghar jaisa khana, roz fresh",
            "Direct order pe better value (commission nahi)",
            "Monthly plan se time aur paisa dono bachta hai",
        ],
        "objections": {
            "too_expensive": "Direct order pe aggregator commission nahi lagta isliye rate behtar rehta hai — aur monthly tiffin plan me per-meal cost aur kam ho jaati hai.",
            "already_have": "Ek baar try karke dekh lijiye — pehla order pe chhota offer de deti hoon, taste pasand aaye to hi continue kijiye.",
            "send_details": "Zaroor, aaj ka menu aur pricing WhatsApp pe bhej deti hoon — dekh ke order kar lena.",
        },
    },
    "ecommerce_d2c": {
        "facts": [
            "Genuine products with proper warranty/return policy — koi duplicate nahi.",
            "Festival aur launch offers pe pricing kaafi competitive hoti hai.",
            "Order tracking aur support WhatsApp pe milta hai — delivery tak update.",
            "COD aur prepaid dono options, secure payment ke saath.",
        ],
        "benefits": [
            "Authentic products + easy returns",
            "Direct-from-brand pricing aur offers",
            "WhatsApp pe quick support aur tracking",
        ],
        "objections": {
            "too_expensive": "Quality aur warranty ke saath ye rate reasonable hai — aur abhi ek launch/festival offer chal raha hai jisse aur sasta pad jaata hai.",
            "just_browsing": "Bilkul dekhiye — main naye arrivals aur current offers WhatsApp pe bhej deti hoon, jab man kare order kar lena.",
            "trust_issue": "Samajhti hoon. Return/replacement policy clear hai aur COD bhi available hai — risk minimal rakha hai.",
        },
    },
    "skin_dermatology": {
        "facts": [
            "Pehle skin assessment hota hai, phir aapki skin ke hisab se treatment plan banta hai.",
            "Acne, pigmentation, anti-aging, laser, PRP jaise common concerns clinic me address hote hain.",
            "Qualified dermatologist consult karte hain — results realistic aur safe rakhe jaate hain.",
            "Consultation me hi expected sessions aur approximate cost clear bata dete hain.",
        ],
        "benefits": [
            "Personalized plan — generic cream nahi",
            "Doctor-supervised, safe procedures",
            "Pehle hi clear expectations aur cost",
        ],
        "objections": {
            "too_expensive": "Treatment session-wise hota hai aur EMI bhi available hoti hai — pehle ek consultation me exact plan aur cost jaan lijiye, phir decide karna.",
            "think_about_it": "Bilkul, skin ka decision soch ke lena sahi hai. Ek consultation book kar deti hoon — doctor se baat karke aaram se decide karna.",
            "not_sure_works": "Har skin alag hoti hai isliye pehle assessment karte hain — jhoothe vaade nahi. Realistic result hi batate hain.",
        },
    },
    "event_management": {
        "facts": [
            "Budget aur theme batayein — uske hisab se end-to-end planning (venue, decor, catering, vendors) handle karte hain.",
            "Corporate offsites/launches aur family functions dono ka experience hai.",
            "Ek single point of contact rehta hai — aapko alag-alag vendors chase nahi karne padte.",
            "Past events ka portfolio aur references share kar sakte hain.",
        ],
        "benefits": [
            "Stress-free planning — sab kuch ek jagah se",
            "Budget ke andar best vendors aur deals",
            "On-the-day coordination — aap relax karein",
        ],
        "objections": {
            "too_expensive": "Hum aapke budget ke andar hi plan banate hain aur vendor deals se aksar paisa bachate hain — pehle ek free planning call kar lijiye.",
            "think_about_it": "Bilkul, event bada decision hai. Main ek sample plan aur portfolio bhej deti hoon, dekh ke aaram se decide karna.",
            "already_have": "Koi baat nahi — ek free quote/idea le lijiye, compare karne me kuch nuksan nahi.",
        },
    },
    "ayurveda_wellness": {
        "facts": [
            "Pehle aapki body-type aur problem samajhte hain, phir personalized treatment/diet plan dete hain.",
            "Chronic issues, immunity, stress, weight jaise concerns pe natural approach se kaam hota hai.",
            "Treatment qualified practitioner ki guidance me hota hai — safe aur gradual.",
            "Results time lete hain; hum realistic timeline batate hain, instant ke jhoothe vaade nahi.",
        ],
        "benefits": [
            "Natural, side-effect-minimal approach",
            "Personalized plan — diet + lifestyle ke saath",
            "Practitioner guidance throughout",
        ],
        "objections": {
            "too_expensive": "Plan aapke budget ke hisab se adjust ho jaata hai — pehle ek consultation me problem aur approximate cost samajh lijiye, koi pressure nahi.",
            "think_about_it": "Bilkul soch ke lijiye — main ek short consultation book kar deti hoon, baat karke aaram se decide karna.",
            "not_sure_works": "Har body alag react karti hai isliye pehle assessment karte hain aur realistic timeline batate hain — jhoothe vaade nahi.",
        },
    },
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
    # ====================================================================== #
    # MARKETING NICHES — local-business categories (AI-marketing services).
    # Facts/benefits MARKETING-context me: kaunsa content chalta hai, kaunse
    # festivals matter karte hain, GBP tips. End-customer = business owner.
    # ====================================================================== #
    "restaurant_cafe": {
        "facts": [
            "Restaurant ke liye Instagram Reels sabse zyada reach laate hain — dish videos aur kitchen behind-the-scenes best perform karte hain.",
            "Google Business Profile pe achhe photos + reviews se 'near me' searches me aapka restaurant upar aata hai.",
            "Diwali, New Year, Valentine's aur weekend offers ke posters se footfall aur online orders dono badhte hain.",
            "Zomato/Swiggy ke alawa khud ka WhatsApp + Insta content direct orders laata hai (commission bachta hai).",
            "Hum roz ka content (posts/reels/menu posters) + festival creatives + Google reviews management sab handle karte hain.",
        ],
        "benefits": [
            "Roz ki dish reels aur posts — aapka time zero",
            "Google pe 'near me' me upar dikhna",
            "Festival offers se footfall + online orders",
            "Reviews badhne se naye customers ka bharosa",
        ],
        "objections": {
            "too_expensive": "₹100/din se kam me poora social media + posters — ek extra table bhi roz bhare to paisa vasool.",
            "already_have": "Zomato/Swiggy commission khaate hain; hum aapka KHUD ka Insta+Google strong karte hain jisse direct order aaye — commission bache.",
            "no_time": "Aapko kuch nahi karna — content, posters, posting sab hum karte hain; aap sirf khana banaiye.",
        },
    },
    "jewellery_store": {
        "facts": [
            "Jewellery me Dhanteras, Diwali, Akshaya Tritiya aur wedding season sabse bada sales window — in par festival posters zaroori.",
            "Instagram pe nayi collection ke high-quality photos/reels se walk-in enquiries badhti hain.",
            "Google Business Profile pe trust badhana zaroori — reviews aur showroom photos se serious buyers aate hain.",
            "Offer creatives (making-charges off, exchange offer) festival pe sabse zyada chalte hain.",
            "Hum festival calendar ke hisab se pehle se posters + collection posts + Google reviews handle karte hain.",
        ],
        "benefits": [
            "Har festival/shaadi season ke ready posters",
            "Nayi collection Insta pe — walk-ins badhein",
            "Google pe trust + reviews se serious buyers",
            "Offer creatives jo sach me bikte hain",
        ],
        "objections": {
            "too_expensive": "Ek bhi extra customer aaye to ₹2,999 nikal jaata hai — jewellery ticket-size badi hoti hai, ROI clear hai.",
            "already_have": "Agency ₹15-25K leti hai; hum ₹3K me wahi festival posters + collection posts + reviews dete hain.",
            "think_about_it": "Bilkul sochiye — tab tak main free Google Business audit karwa deti hoon, score dekh ke decide karna.",
        },
    },
    "salon_spa": {
        "facts": [
            "Before-after reels salon ke liye #1 content hain — naye customers result dekh ke turant book karte hain.",
            "Google reviews salon business ka sabse bada trust signal — jitne zyada utni nayi booking.",
            "Monthly offers (bridal package, weekday discount) aur festival posters se slow days bharte hain.",
            "Instagram + Google Business Profile dono pe regular content se 'salon near me' me upar aate hain.",
            "Hum before-after reels, offers, festival posters aur review collection sab manage karte hain.",
        ],
        "benefits": [
            "Before-after reels se direct appointments",
            "Google reviews se naye customers ka bharosa",
            "Monthly offers se slow days bhare",
            "'Near me' search me upar dikhna",
        ],
        "objections": {
            "too_expensive": "Mahine me 5-6 nayi appointments bhi aaye to ₹2,999 vasool — salon me repeat customer banta hai.",
            "already_have": "Sirf post karna kaafi nahi — hum before-after reels + reviews + offers ka poora system dete hain.",
            "no_time": "Aap customers pe focus kijiye — content, reels, posting sab hamara kaam hai.",
        },
    },
    "boutique_fashion": {
        "facts": [
            "Boutique ke liye nayi collection ke reels aur try-on videos Insta pe sabse zyada chalte hain.",
            "WhatsApp Status + broadcast pe naye design daalne se repeat customers turant order karte hain.",
            "Festival aur wedding season (Navratri, Diwali, shaadi) ke offer posters peak sales laate hain.",
            "Google Business Profile + Insta se 'boutique near me' searches me dikhna footfall badhata hai.",
            "Hum collection posts, reels, festival posters aur WhatsApp offers sab handle karte hain.",
        ],
        "benefits": [
            "Nayi collection ke reels — daily reach",
            "WhatsApp pe direct orders",
            "Festival offers se peak sales",
            "'Near me' search me boutique dikhe",
        ],
        "objections": {
            "too_expensive": "Ek-do extra order roz bhi ho to ₹2,999 nikal jaata hai — clothing me margin achha hota hai.",
            "already_have": "Khud post karna time-consuming hai; hum daily content + reels + WhatsApp offers professionally karte hain.",
            "no_time": "Aap design aur store sambhaliye — Insta, reels aur WhatsApp marketing hum karenge.",
        },
    },
    "gym_fitness": {
        "facts": [
            "Member transformation reels gym ke liye sabse powerful content hain — log result dekh ke join karte hain.",
            "January (New-Year resolution) aur season-start pe joining offers sabse zyada chalte hain — posters zaroori.",
            "Google reviews + Business Profile se 'gym near me' searches me upar aate hain.",
            "Regular fitness tips aur class reels se members engaged rehte hain (renewals badhte hain).",
            "Hum transformation reels, offer posters, reviews aur regular posts sab manage karte hain.",
        ],
        "benefits": [
            "Transformation reels se nayi joinings",
            "New-Year/season offers se member surge",
            "Google reviews se trust + 'near me' ranking",
            "Engagement se renewals badhein",
        ],
        "objections": {
            "too_expensive": "Ek membership ₹2,999 se zyada hoti hai — mahine me 1-2 nayi joining bhi aaye to faayda.",
            "already_have": "Sirf posting nahi — hum transformation reels + offers + reviews ka poora system dete hain.",
            "no_time": "Aap training pe focus kijiye — content, reels aur offers hum sambhalenge.",
        },
    },
    "bakery_sweets": {
        "facts": [
            "Festival (Diwali, Raksha Bandhan, Holi) ke mithai/cake posters bakery ke liye sabse bada sales driver hain.",
            "Cake aur dessert ke close-up reels Instagram pe khoob reach laate hain — orders direct aate hain.",
            "Google Business Profile pe photos + reviews se 'cake shop near me' me upar aate hain.",
            "Birthday/anniversary cake offers aur custom-order posts repeat customers laate hain.",
            "Hum festival posters, product reels, offers aur Google reviews sab handle karte hain.",
        ],
        "benefits": [
            "Festival mithai/cake posters se order surge",
            "Dessert reels se direct enquiries",
            "Google pe 'near me' me dikhna",
            "Custom-order posts se repeat business",
        ],
        "objections": {
            "too_expensive": "Festival pe hi ₹2,999 se zyada extra orders aa jaate hain — saal bhar ki marketing ka faayda.",
            "already_have": "Hum festival calendar ke hisab se pehle se posters + reels banate hain — aap kuch miss nahi karte.",
            "no_time": "Aap baking pe dhyaan dijiye — posters, reels aur posting hamara kaam.",
        },
    },
    "mobile_electronics": {
        "facts": [
            "Mobile shop ke liye naye launch + EMI/exchange offer ke posters sabse zyada footfall laate hain.",
            "Festival sale (Diwali, Republic Day, Independence Day) pe offer creatives peak sales window hai.",
            "Google Business Profile pe shop dikhna zaroori — log 'mobile shop near me' search karke aate hain.",
            "WhatsApp broadcast pe naye stock/offers daalne se purane customers wapas aate hain.",
            "Hum offer posters, new-arrival posts, festival creatives aur Google listing sab manage karte hain.",
        ],
        "benefits": [
            "Launch + offer posters se footfall",
            "Festival sale creatives — peak orders",
            "'Near me' search me shop dikhe",
            "WhatsApp offers se repeat customers",
        ],
        "objections": {
            "too_expensive": "Ek phone ka margin se hi ₹2,999 nikal aata hai — mahine me kuch extra customers = clear profit.",
            "already_have": "Sirf board lagana kaafi nahi — online (Google+Insta+WhatsApp) pe dikhna aaj zaroori hai, wahi hum karte hain.",
            "no_time": "Aap shop chalaiye — posters, posts aur Google listing hum sambhalenge.",
        },
    },
    "hotel_resort": {
        "facts": [
            "Hotel/resort ke liye property ke reels aur Google reviews booking ka sabse bada source hain.",
            "Festival aur season packages (New Year, weekend getaway, wedding) ke posters direct bookings laate hain.",
            "Google Business Profile pe achhe photos + ratings se 'hotel near me' searches me upar aate hain.",
            "Instagram pe rooms, food aur views ke reels se family aur event bookings badhti hain.",
            "Hum venue reels, festival/season posters, reviews aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Property reels se direct bookings",
            "Season/festival package posters",
            "Google reviews + 'near me' ranking",
            "Event aur family bookings badhein",
        ],
        "objections": {
            "too_expensive": "Ek booking se hi ₹2,999 se zyada milta hai — mahine me 1-2 extra booking = profit.",
            "already_have": "OTA commission khaate hain; hum aapka direct Insta+Google strong karte hain jisse commission-free booking aaye.",
            "no_time": "Aap guests sambhaliye — content, reels aur listing hum manage karenge.",
        },
    },
    "automobile_service": {
        "facts": [
            "Car/bike service ke liye Google Business Profile #1 lever hai — log 'car service near me' search karke aate hain.",
            "Seasonal-check (monsoon/summer AC) aur service-package offer ke posters footfall laate hain.",
            "Google reviews trust banate hain — zyada reviews = zyada walk-ins.",
            "Before-after detailing reels aur quick-tips content Insta pe engagement laate hain.",
            "Hum service-offer posters, festival creatives, Google listing aur reviews sab handle karte hain.",
        ],
        "benefits": [
            "Google 'near me' me garage dikhe",
            "Seasonal + package offers se footfall",
            "Reviews se naye customers ka bharosa",
            "Detailing reels se engagement",
        ],
        "objections": {
            "too_expensive": "Mahine me kuch extra services bhi aaye to ₹2,999 nikal jaata hai — repeat customer banta hai.",
            "already_have": "Google pe sahi se dikhna aur reviews manage karna alag skill hai — wahi hum professionally karte hain.",
            "no_time": "Aap gaadiyon pe focus kijiye — Google listing, posters aur reviews hum sambhalenge.",
        },
    },
    "photography_studio": {
        "facts": [
            "Photography studio ke liye best shoots ke portfolio reels Insta pe sabse zyada bookings laate hain.",
            "Wedding season ke offer posters aur package creatives peak enquiry window me kaam aate hain.",
            "Google Business Profile + reviews se 'photographer near me' searches me dikhna footfall laata hai.",
            "Behind-the-scenes aur client-testimonial reels trust badhate hain.",
            "Hum portfolio reels, festival/wedding posters, reviews aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Portfolio reels se wedding bookings",
            "Season package posters",
            "Google reviews + 'near me' ranking",
            "Testimonial reels se trust",
        ],
        "objections": {
            "too_expensive": "Ek shoot ka package se hi ₹2,999 se kahin zyada milta hai — ek booking = profit.",
            "already_have": "Sirf photos daalna kaafi nahi — reels, SEO aur reviews ka poora system bookings laata hai, wahi hum dete hain.",
            "no_time": "Aap shoots pe focus kijiye — reels, posters aur posting hum karenge.",
        },
    },
    "pharmacy_medical": {
        "facts": [
            "Pharmacy ke liye Google Business Profile #1 lever hai — log 'medical store near me' / '24-hour pharmacy' search karte hain.",
            "Home-delivery offer ko Google + WhatsApp pe highlight karne se orders badhte hain.",
            "Health-day posts (Diabetes Day, Heart Day) aur seasonal tips se community engagement banta hai.",
            "Google reviews trust badhate hain — medical me bharosa sabse important.",
            "Hum Google listing optimization, health-day posts, delivery offers aur reviews sab handle karte hain.",
        ],
        "benefits": [
            "Google 'near me' me store dikhe",
            "Home-delivery enquiries badhein",
            "Health-day posts se engagement",
            "Reviews se medical-trust",
        ],
        "objections": {
            "too_expensive": "Ek mahine me kuch extra delivery customers bhi aaye to ₹2,999 nikal jaata hai.",
            "already_have": "Google pe sahi se dikhna aur delivery promote karna alag kaam hai — wahi hum karte hain.",
            "no_time": "Aap dukaan chalaiye — Google listing, posts aur reviews hum sambhalenge.",
        },
    },
    "furniture_decor": {
        "facts": [
            "Furniture showroom ke liye product catalog posters aur naye-design reels Insta pe footfall laate hain.",
            "Festival aur wedding-season offers (gruha-pravesh, Diwali) ke posters peak sales window hain.",
            "Google Business Profile pe showroom photos + reviews se 'furniture shop near me' me upar aate hain.",
            "WhatsApp pe naya stock/catalog bhejne se enquiries direct aati hain.",
            "Hum catalog posters, product reels, festival offers aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Catalog posters + reels se footfall",
            "Festival/wedding offers se sales",
            "Google 'near me' me showroom dikhe",
            "WhatsApp catalog se enquiries",
        ],
        "objections": {
            "too_expensive": "Furniture ka ek sale margin se hi ₹2,999 nikal aata hai — kuch extra footfall = profit.",
            "already_have": "Sirf board kaafi nahi — Insta catalog, reels aur Google listing aaj zaroori hain, wahi hum karte hain.",
            "no_time": "Aap showroom sambhaliye — catalog, posters aur posting hum karenge.",
        },
    },
    "kirana_supermarket": {
        "facts": [
            "Kirana/supermarket ke liye weekly WhatsApp offers repeat footfall ka sabse sasta tarika hain.",
            "Festival aur monthly grocery offer posters se customers planned shopping aapke yahan karte hain.",
            "Google Business Profile pe store dikhna zaroori — naye log 'grocery near me' / 'supermarket near me' search karte hain.",
            "WhatsApp broadcast pe combo/discount daalne se home-delivery orders badhte hain.",
            "Hum WhatsApp offer creatives, festival posters aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Weekly WhatsApp offers se repeat footfall",
            "Festival posters se planned shopping",
            "Google 'near me' me store dikhe",
            "Home-delivery orders badhein",
        ],
        "objections": {
            "too_expensive": "Mahine me kuch extra repeat customers bhi rahein to ₹2,999 aaram se nikal jaata hai.",
            "already_have": "WhatsApp pe sirf forward karna alag baat hai — hum professional offer creatives + Google listing dete hain.",
            "no_time": "Aap dukaan chalaiye — offers, posters aur WhatsApp marketing hum sambhalenge.",
        },
    },
    "travel_agency": {
        "facts": [
            "Travel agency ke liye season package posters (summer hills, Diwali break, honeymoon) sabse zyada enquiries laate hain.",
            "Destination reels aur customer-trip photos Insta pe trust aur bookings badhate hain.",
            "Google Business Profile + reviews se 'travel agent near me' searches me dikhna zaroori.",
            "WhatsApp broadcast pe naye packages bhejne se repeat travellers turant pooch-taach karte hain.",
            "Hum package posters, destination reels, offers aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Season package posters se enquiries",
            "Destination reels se bookings",
            "Google reviews + 'near me' ranking",
            "WhatsApp offers se repeat travellers",
        ],
        "objections": {
            "too_expensive": "Ek package booking se hi ₹2,999 se kahin zyada commission milta hai — ek booking = profit.",
            "already_have": "Sirf forward karna nahi — hum professional posters, reels aur Google presence ka system dete hain.",
            "no_time": "Aap bookings sambhaliye — posters, reels aur posting hum karenge.",
        },
    },
    "gift_stationery": {
        "facts": [
            "Gift/stationery shop ke liye occasion posters (Rakhi, Diwali, Valentine's, back-to-school) sabse zyada footfall laate hain.",
            "Naye gift items aur hampers ke Insta/WhatsApp posts se customers aapki shop yaad rakhte hain.",
            "Google Business Profile pe dikhna zaroori — log 'gift shop near me' search karke aate hain.",
            "Festival combo aur offer creatives peak occasion pe sabse zyada chalte hain.",
            "Hum festival/occasion posters, product posts aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Occasion posters se footfall",
            "Naye items ke posts se recall",
            "Google 'near me' me shop dikhe",
            "Festival combos se peak sales",
        ],
        "objections": {
            "too_expensive": "Festival season me hi ₹2,999 se zyada extra sale ho jaati hai — saal bhar ka faayda.",
            "already_have": "Hum occasion-calendar ke hisab se pehle se posters banate hain — aap koi festival miss nahi karte.",
            "no_time": "Aap shop sambhaliye — posters, posts aur Google listing hum karenge.",
        },
    },
    "hardware_paint": {
        "facts": [
            "Hardware/paint shop ke liye Google Business Profile #1 lever hai — contractors aur ghar-wale 'hardware shop near me' search karte hain.",
            "Offer aur naye-product posters (paint combo, festival discount) footfall laate hain.",
            "Festival aur construction-season (gruha-pravesh, renovation) ke posters peak enquiry window hain.",
            "Google reviews aur shop photos se trust badhta hai — bade orders aate hain.",
            "Hum offer posters, festival creatives, product posts aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Google 'near me' me dukaan dikhe",
            "Offer + product posters se footfall",
            "Festival/season posters se bade orders",
            "Reviews se contractor-trust",
        ],
        "objections": {
            "too_expensive": "Ek-do bade order se hi ₹2,999 nikal jaata hai — contractor repeat customer banta hai.",
            "already_have": "Google pe sahi dikhna aur reviews manage karna alag kaam hai — wahi hum professionally karte hain.",
            "no_time": "Aap dukaan chalaiye — Google listing, posters aur posts hum sambhalenge.",
        },
    },
    "tiffin_service": {
        "facts": [
            "Tiffin service ka #1 business engine monthly subscription hai — naye customers office/home area ke groups se aate hain.",
            "Google reviews aur WhatsApp orders se trust banta hai — log 'tiffin near me' ya 'ghar ka khana home delivery' search karte hain.",
            "Menu ki daily photos aur weekly offers ke posts se existing customers engaged rehte hain (renewals badhte hain).",
            "Office zones aur housing societies me target karo — ek contract se 5-10 monthly subscriptions ek saath milte hain.",
            "Hum menu posts, Google reviews aur WhatsApp order flow sab manage karte hain.",
        ],
        "benefits": [
            "Monthly subscriptions consistently badhein",
            "Google 'tiffin near me' me top dikhna",
            "WhatsApp orders se direct bookings",
            "Menu posts se renewals",
        ],
        "objections": {
            "too_expensive": "Ek extra monthly subscription se hi ₹2,999 nikal jaata hai — tiffin business repeat hai, ROI clear hai.",
            "already_have": "Sirf post karna kaafi nahi — hum reviews, WhatsApp follow-up aur Google listing ka poora system dete hain.",
            "no_time": "Aap khana aur delivery sambhaliye — posts, listing aur follow-up hum karenge.",
        },
    },
    "gents_salon": {
        "facts": [
            "Men's salon/barber shop ke liye Google Business Profile #1 lever hai — 'salon near me' ya 'barber shop near me' searches me dikhna.",
            "Before-after reels aur beard/haircut styling posts Instagram pe sabse zyada reach laate hain.",
            "Google reviews se trust badhta hai — aadmi phone pe puchhne se pehle reviews dekh ke aata hai.",
            "Festival season (Diwali, weddings) aur weekend offers se walk-ins badhte hain — posters zaroori.",
            "Hum before-after reels, offers, reviews aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Naye walk-in customers 'near me' se",
            "Before-after reels se direct bookings",
            "Google reviews se bharosa",
            "Festival offers se peak footfall",
        ],
        "objections": {
            "too_expensive": "Roz 2-3 extra walk-in customers se ₹2,999 nikal jaata hai — salon me repeat customer hi business hai.",
            "already_have": "Sirf post karna kaafi nahi — hum review collection + Google ranking ka system dete hain.",
            "no_time": "Aap clients sambhaliye — reels, posts aur listing hum karenge.",
        },
    },
    "tuition_classes": {
        "facts": [
            "Tuition classes ke liye admission season (April-June, Dec-Jan) main window hai — usse pehle visibility ready honi chahiye.",
            "Google 'tuition near me' / 'maths tuition' searches parents ko admission dilaate hain — listing + reviews zaroori.",
            "Result posts aur topper photos se trust badhta hai — parents results dekh ke admission karte hain.",
            "WhatsApp group aur parent reviews se referrals badhte hain — har admission inquiry ka turant follow-up.",
            "Hum result posts, reviews, Google listing aur inquiry follow-up sab handle karte hain.",
        ],
        "benefits": [
            "Admission season me pehle dikhna",
            "Result posts se parent trust",
            "Google 'tuition near me' ranking",
            "Har inquiry ka turant follow-up",
        ],
        "objections": {
            "too_expensive": "Ek extra student per month se ₹2,999 nikal jaata hai — seats fill hote hi ROI clear hai.",
            "already_have": "Sirf board pe ad dena kaafi nahi — hum result posts + parent reviews + Google ka system dete hain.",
            "no_time": "Aap padhane pe focus kijiye — posts, listing aur follow-up hum karenge.",
        },
    },
    "play_school": {
        "facts": [
            "Play school ke liye admission season (Nov-Feb nursery/LKG/UKG) main window hai — parents 6 mahine pehle research shuru karte hain.",
            "Campus photos, activities aur safe-environment posts se parents ka bharosa banta hai.",
            "Google 'play school near me' / 'nursery school admission' searches se direct admission inquiries aate hain.",
            "Parent reviews aur testimonials play school ke liye sabse strong trust signal hain.",
            "Hum campus posts, reviews, Google listing aur admission inquiry follow-up sab handle karte hain.",
        ],
        "benefits": [
            "Admission season se pehle visibility ready",
            "Campus photos se parent trust",
            "Google 'play school near me' ranking",
            "Har parent inquiry ka turant follow-up",
        ],
        "objections": {
            "too_expensive": "Ek extra admission per season se ₹2,999 se zyada nikal jaata hai — parents pehle hi admission karwana chahte hain.",
            "already_have": "Sirf walk-in boards pe bharosa nahi — hum campus photos + reviews + Google ka system dete hain.",
            "no_time": "Aap bacchon pe focus kijiye — posts, listing aur inquiries hum sambhalenge.",
        },
    },
    "laundry_dryclean": {
        "facts": [
            "Laundry/dryclean ke liye Google Business Profile #1 lever hai — 'laundry near me' aur 'dry cleaning near me' searches me dikhna.",
            "Home pickup/delivery offers se society aur office-zone customers repeat order karte hain.",
            "Festival season (Diwali, shaadi) me dry-cleaning demand spike hoti hai — pehle se offers ready hona chahiye.",
            "Google reviews se trust badhta hai — log door pe jane se pehle reviews dekh ke aate hain.",
            "Hum home-pickup offers, reviews aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Home-pickup orders consistently badhein",
            "Google 'laundry near me' me top dikhna",
            "Festival dry-clean offers se peak demand",
            "Reviews se naye customers ka bharosa",
        ],
        "objections": {
            "too_expensive": "Ek do home-pickup customers se hi ₹2,999 nikal jaata hai — laundry repeat business hai, ROI clear hai.",
            "already_have": "Sirf post karna kaafi nahi — hum reviews, offers aur Google listing ka poora system dete hain.",
            "no_time": "Aap kaam sambhaliye — posts, listing aur follow-up hum karenge.",
        },
    },
    "electronics_repair": {
        "facts": [
            "Mobile/electronics repair ke liye Google Business Profile #1 lever hai — 'mobile repair near me' searches me dikhna.",
            "Doorstep repair aur warranty offers ko highlight karna — log convenience aur trust dono dhoondhte hain.",
            "Screen/battery repair India me sabse zyada search volume wale repairs hain.",
            "Google reviews se bharosa banta hai — customer repair se pehle shop ki reputation check karta hai.",
            "Hum doorstep offers, reviews aur Google listing sab handle karte hain.",
        ],
        "benefits": [
            "Naye repair customers 'near me' se",
            "Doorstep service offers se convenience demand",
            "Google reviews se bharosa",
            "High-search repairs pe visibility",
        ],
        "objections": {
            "too_expensive": "Ek do extra repairs se hi ₹2,999 nikal jaata hai — repair demand roz ki hai, ROI clear hai.",
            "already_have": "Sirf post karna kaafi nahi — hum reviews, offers aur Google listing ka poora system dete hain.",
            "no_time": "Aap repairs sambhaliye — posts, listing aur follow-up hum karenge.",
        },
    },
}
