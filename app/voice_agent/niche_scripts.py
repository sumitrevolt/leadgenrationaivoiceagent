"""
Professional Hinglish telecaller script dataset for the AI voice sales agent.

Yeh pure-data file hai — koi heavy import nahi (import-safe). Har niche ka
ek script-block hai jo END-CUSTOMER outbound call ke liye likha gaya hai
(LEADS agent client ke potential customers ko call karta hai). Lines real
Indian telecaller best-practices pe based hain (web-researched, June 2026):

  - Permission-based + pattern-interrupt opener (TRAI-friendly, brief)
  - Goal = appointment / site-visit / callback BOOK karna, phone pe close nahi
  - Objection handling = LAER (Listen-Acknowledge-Explore-Respond): pehle
    empathize, phir 1 value-line, phir aage badho
  - Har line phone-ready: 1 vakya, warm, confident, chhota Hinglish
  - [Company]/[Name]/[Project] placeholders runtime pe brain substitute karta

Niche-specific facts baked-in: solar = PM Surya Ghar subsidy (3kW pe ~Rs.78k,
300 unit free); home loan = balance-transfer EMI savings; insurance = term plan
~Rs.20-30/din; study-abroad/coaching/interior/dental = FREE consultation hook
+ no-cost EMI.

Consumers: TelecallerBrain (prompt grounding), knowledge_base (KB embedding via
kb_documents()), web-call demo. get_script() builtin/custom dono ke liye safe —
jo niche cover nahi, wo "general" fallback pe aata hai.
"""

from __future__ import annotations

# Objection dict keys (sab niches me same — brain/KB consistent rehte hain):
#   mehenga      -> "price / too expensive / mehnga hai"
#   abhi_nahi    -> "timing / abhi nahi / baad me"
#   soch_ke      -> "soch ke batata hoon / need to think"
#   pehle_se_hai -> "already have it / pehle se laga/liya hai"
#   bharosa      -> "trust / bharosa nahi / genuine ho kya"

NICHE_SCRIPTS: dict[str, dict] = {
    # ====================================================================== #
    # PRIORITY NICHES (researched, niche-specific)
    # ====================================================================== #
    "real_estate": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapne [Project] me 2 BHK ke liye inquiry ki thi, bas 30 second baat kar lein?",
        "discovery": [
            "Aap apne rehne ke liye dekh rahe hain ya investment ke liye?",
            "Budget approx kis range me chal raha hai — 50 lakh ke aas-paas?",
            "Location aur possession kab tak chahiye — ready-to-move ya under-construction?",
            "Home loan plan kar rahe hain ya self-funded?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon sir, par is location me rate abhi monthly badh rahe hain — ek baar site dekh lijiye, EMI me payment plan aaram se set ho jaata hai.",
            "abhi_nahi": "Koi baat nahi sir, abhi sirf dekhne aaiye — booking ki koi jaldi nahi, par aaj ke rates ka idea ho jayega.",
            "soch_ke": "Bilkul sochiye sir, bas itna batayein kis cheez pe doubt hai — budget ya location — taaki main aapke liye sahi 2-3 option hi shortlist karoon.",
            "pehle_se_hai": "Achhi baat hai sir, par ek aur option compare karne me kya jaata hai — abhi ka rate aur layout dekh ke aap khud farak samajh jayenge.",
            "bharosa": "Sahi sawaal hai sir, yeh RERA-registered project hai aur aap khud site pe aakar har cheez verify kar sakte hain.",
        },
        "value_lines": [
            "Project metro, school aur market sab walking distance pe hai.",
            "Abhi book karne pe pre-launch price aur extra discount chal raha hai.",
        ],
        "closing": "Toh sir, weekend pe ek site visit fix kar dein — Saturday subah ya Sunday shaam, kaunsa time aapke liye theek rahega?",
    },
    "solar_residential": {
        "opening": "Namaste sir, main [Company] se [Name] — bas 30 second, PM Surya Ghar solar subsidy ke baare me batana tha, theek hai?",
        "discovery": [
            "Aapka monthly bijli bill abhi kitna aata hai — 2000 se zyada?",
            "Ghar aur chhat aapke khud ke naam pe hai, system lagane ki jagah hai?",
            "PM Surya Ghar subsidy scheme ke baare me suna hai aapne?",
        ],
        "objections": {
            "mehenga": "Sir investment ek hi baar ka hai — 3kW pe Rs.78,000 tak government subsidy milti hai aur 4-5 saal me poora paisa bill bachat se nikal aata hai.",
            "abhi_nahi": "Koi pressure nahi sir, bas ek free site survey karwa lijiye — system size aur monthly savings ka pakka estimate mil jayega.",
            "soch_ke": "Zaroor sochiye sir, itna bata doon — har mahine jo bill bekaar ja raha hai, wahi paisa solar EMI ban jaata hai, baaki aap decide karein.",
            "pehle_se_hai": "Achha sir, pehle se laga hai toh maintenance ya extra panel me bhi help kar dete hain — chhat pe aur kitni jagah khaali hai?",
            "bharosa": "Bilkul sahi sir, hum DISCOM-registered vendor hain aur subsidy seedha government se aapke account me aati hai, hamare through nahi.",
        },
        "value_lines": [
            "PM Surya Ghar me 300 unit tak bijli practically free ho jaati hai.",
            "25 saal panel warranty milti hai aur bill 80-90% tak gir jaata hai.",
        ],
        "closing": "Toh sir, ek free roof survey set kar dein — kal subah ya parso, hamara engineer aapke convenient time pe aa jayega?",
    },
    "studying_abroad": {
        "opening": "Hello sir, main [Company] se [Name] bol raha hoon — aapne abroad study ke liye inquiry ki thi, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Aap kaunsa course aur country soch rahe hain — USA, UK, Canada ya Australia?",
            "Intake kab ka target hai — is saal ka ya agle saal ka?",
            "Funding self karenge ya education loan se plan hai?",
            "IELTS ya GRE ka score ready hai ya abhi tayari chal rahi hai?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par hamari counselling poori free hai — aur scholarship aur education loan dono budget ke hisaab se arrange karwa dete hain.",
            "abhi_nahi": "Koi baat nahi sir, par intake deadlines jaldi aati hain — ek free counselling le lijiye taaki poori timeline clear ho jaye.",
            "soch_ke": "Zaroor sochiye sir, bas ek baar counselor se baat kar lijiye — aapki profile ke hisaab se best university shortlist free me ban jayegi.",
            "pehle_se_hai": "Achhi baat hai sir, par ek second opinion lene me kya harj hai — ho sakta hai hum better university ya zyada scholarship dhoondh dein.",
            "bharosa": "Bilkul sir, hamare 500+ students is saal visa pe gaye hain — aap unse aur hamari university tie-ups khud verify kar sakte hain.",
        },
        "value_lines": [
            "Profile evaluation, university shortlist aur visa guidance — sab free counselling me cover hota hai.",
            "Scholarship aur education loan dono me hum end-to-end help karte hain.",
        ],
        "closing": "Toh ek free counselling session fix karein — aaj shaam 5 baje ya kal, jab aap aur aapke parents dono available ho?",
    },
    "insurance": {
        "opening": "Namaste sir, main [Company] se baat kar raha hoon — aapki family ke liye ek quick protection review tha, bas ek minute de sakte hain?",
        "discovery": [
            "Aapki age abhi kya hai, aur family me kitne log aap pe dependent hain?",
            "Abhi koi health ya term cover chal raha hai, ya pehli baar le rahe hain?",
            "Premium me monthly ya yearly, kitna comfortable rahenge?",
        ],
        "objections": {
            "mehenga": "Samjha sir, par term plan din ke 20-30 rupaye me 1 crore tak cover deta hai — ek chai se bhi kam me poori family secure ho jaati hai.",
            "abhi_nahi": "Theek hai sir, bas itna ki age badhne pe premium har saal mehnga hota hai — abhi lock karaa lein toh life-time sasta padta hai.",
            "soch_ke": "Zaroor sochiye sir, main ek quick quote WhatsApp pe bhej deta hoon — number saamne dekh ke aaram se decide kar lijiye.",
            "pehle_se_hai": "Achhi baat hai sir, par aksar purana plan ya toh kam cover ka hota hai ya mehnga — ek free comparison karwa lein, paisa bach sakta hai.",
            "bharosa": "Bilkul sir, hum IRDAI-registered hain — company ka claim settlement ratio aur policy aap seedha verify kar sakte hain.",
        },
        "value_lines": [
            "1 crore ka term cover sahi age pe sirf Rs.600-700 mahine se shuru hota hai.",
            "Health plan me cashless hospital network aur tax bachat dono milti hai.",
        ],
        "closing": "Toh sir, main aaj hi aapke liye 2 best quotes nikaal ke ek short call fix karta hoon — shaam 6 baje theek rahega?",
    },
    "coaching": {
        "opening": "Namaste sir, main [Company] se bol raha hoon — aapne apne bachche ki NEET/JEE coaching ke liye poocha tha, bas 2 minute baat kar lein?",
        "discovery": [
            "Bachcha abhi kaunsi class me hai, aur target exam kya hai — NEET ya JEE?",
            "Abhi koi coaching chal rahi hai ya naye se shuru karwana hai?",
            "Online batch prefer karenge ya classroom?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par yeh poore saal ki tayari ka investment hai — hum EMI aur scholarship test dono dete hain fees aasaan karne ke liye.",
            "abhi_nahi": "Theek hai sir, par batches jaldi bhar jaate hain — ek free demo class aur counselling le lijiye, decision aaram se kar lena.",
            "soch_ke": "Zaroor sir, bachche ko ek free demo class dilwa dijiye — faculty aur padhai dekh ke aap dono saath me decide kar lena.",
            "pehle_se_hai": "Achhi baat hai sir, par ek free assessment test karwa lein — pata chal jayega bachcha sahi track pe hai ya improvement chahiye.",
            "bharosa": "Bilkul sir, hamare is saal ke results aur selections aap dekh sakte hain — ek baar center visit karke faculty se mil lijiye.",
        },
        "value_lines": [
            "Experienced faculty, regular test series aur personal doubt-solving — sab ek package me.",
            "Scholarship test me achhe number pe fees me kaafi chhoot mil jaati hai.",
        ],
        "closing": "Toh ek free demo class aur counselling fix karein — is weekend Saturday ya Sunday, bachche ke saath aa sakte hain?",
    },
    "home_loans": {
        "opening": "Namaste sir, main [Company] se home loan ke baare me baat kar raha hoon — aapne loan ke liye inquiry ki thi, bas 1 minute baat ho jaye?",
        "discovery": [
            "Loan kitne amount ka chahiye, aur property ready hai ya under-construction?",
            "Aap salaried hain ya self-employed, monthly income approx kitni hai?",
            "Naya loan le rahe hain ya existing loan kam rate pe transfer karwana hai?",
        ],
        "objections": {
            "mehenga": "Sir hum processing fee minimum rakhte hain aur 15+ banks ke rate compare karke sabse sasti EMI nikaalte hain — aapko mehnga nahi padega.",
            "abhi_nahi": "Koi baat nahi sir, bas ek free eligibility check karwa lein — kitna loan kis rate pe milega abhi pata chal jayega, bina kisi commitment.",
            "soch_ke": "Zaroor sochiye sir, main aapki eligibility aur EMI ka number WhatsApp pe bhej deta hoon — dekh ke aaram se decide kar lena.",
            "pehle_se_hai": "Achhi baat hai sir, agar pehle se loan chal raha hai toh balance transfer pe EMI kam ho sakti hai — aapka current rate kya hai?",
            "bharosa": "Bilkul sir, hum banks aur NBFC ke authorised partner hain — saari processing bank ke through legal aur transparent hoti hai.",
        },
        "value_lines": [
            "Hum 15+ banks compare karke sabse kam rate aur fast approval dilwate hain.",
            "Balance transfer pe aksar EMI Rs.2,000-5,000 mahine tak bach jaati hai.",
        ],
        "closing": "Toh sir, main ek free eligibility check karta hoon — documents ka list bhej doon aur kal ek call fix kar lein?",
    },
    "interior_designers": {
        "opening": "Namaste sir, main [Company] se bol raha hoon — aapne apne ghar ke interior ke liye inquiry ki thi, bas 2 minute baat kar sakte hain?",
        "discovery": [
            "Property kitne BHK ki hai, aur ready-to-move hai ya abhi construction me?",
            "Poore ghar ka interior chahiye ya kuch specific — kitchen, wardrobe?",
            "Budget approx kis range me soch rahe hain, aur possession kab tak hai?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par hum aapke budget ke andar hi design banate hain — aur 0% EMI pe poora interior ho jaata hai, ek baar quote dekh lijiye.",
            "abhi_nahi": "Koi baat nahi sir, bas ek free design consultation le lijiye — 3D design aur estimate mil jayega, kaam jab marzi shuru karein.",
            "soch_ke": "Zaroor sir, ek free 3D design aur quote bana dete hain — saamne dekh ke aaram se decide kijiye, koi charge nahi.",
            "pehle_se_hai": "Achhi baat hai sir, agar designer dekh liya hai toh ek comparison quote le lijiye — design aur price dono saamne aa jayenge.",
            "bharosa": "Bilkul sir, hum likhit warranty aur fixed timeline dete hain — aap hamare completed projects aur reviews dekh sakte hain.",
        },
        "value_lines": [
            "Free 3D design, fixed timeline aur material warranty — sab ek package me.",
            "Aapke budget ke hisaab se design, aur 0% EMI option bhi available hai.",
        ],
        "closing": "Toh ek free design consultation fix karein — designer aapke ghar aaye ya aap studio aayein, is weekend kaunsa time theek rahega?",
    },
    "dental_implants": {
        "opening": "Namaste sir, main [Company] se bol raha hoon — aapne dental implant ke baare me poocha tha, bas 1 minute baat kar lein?",
        "discovery": [
            "Kitne teeth ka issue hai — ek single tooth ya zyada?",
            "Problem kab se hai, aur kisi doctor ko dikha chuke hain?",
            "Aap hamare clinic ke aas-paas hi rehte hain kya?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par implant ek baar ka lifetime solution hai — aur hum no-cost EMI dete hain taaki kharcha aaram se ho jaye.",
            "abhi_nahi": "Theek hai sir, par dant ka issue tala nahi jaata — ek baar free consultation aur X-ray karwa lijiye, condition clear ho jayegi.",
            "soch_ke": "Zaroor sochiye sir, bas ek free consultation le lijiye — doctor exact cost aur options batayenge, phir aaram se decide karein.",
            "pehle_se_hai": "Achha sir, agar kisi aur clinic me dikhaya hai toh ek free second opinion le lijiye — pricing aur quality dono compare kar lijiye.",
            "bharosa": "Bilkul sir, hamare implants warranty ke saath international brand ke hain — aap clinic aakar doctor se sab confirm kar sakte hain.",
        },
        "value_lines": [
            "Implant ek lifetime solution hai — ek baar lagao, baar-baar ka kharcha khatam.",
            "Free consultation, digital X-ray aur no-cost EMI — sab available hai.",
        ],
        "closing": "Toh sir, ek free consultation fix kar dein — kal subah ya shaam, doctor ke paas aapka slot reserve kar doon?",
    },
    "ai_marketing": {
        "opening": "Namaste sir, main LeadGen AI se [Name] bol rahi hoon — local businesses ki marketing AI se automate karte hain, bas 30 second baat kar sakti hoon?",
        "discovery": [
            "Abhi aap apni marketing kaise karte ho — khud post dalte ho, staff hai, ya agency?",
            "Google pe aapka business search karne par upar dikhta hai kya?",
            "Website ya Google se jo inquiries aati hain, unka follow-up kaun karta hai?",
            "Mahine me marketing pe approx kitna kharcha ho jaata hai?",
        ],
        "objections": {
            "mehenga": "Sir ek customer ki value socho — ₹100/din me poora marketing department mil jaata hai; ek bhi extra customer aaye to paisa vasool.",
            "abhi_nahi": "Koi baat nahi sir, tab tak ek FREE Google Business audit karwa lijiye — aapka score aur fixes saamne aa jayenge, koi charge nahi.",
            "soch_ke": "Bilkul sochiye sir — main aapka FREE GBP audit bhej deti hoon, score dekh ke aaram se decide kar lena, koi obligation nahi.",
            "pehle_se_hai": "Achha sir, agency to ₹15-25K/mahina leti hai — hum ₹3K se shuru karte hain, aur AI aapki inquiries ko CALL bhi karta hai jo agency nahi karti.",
            "bharosa": "Sahi sawaal hai sir — pehle FREE audit aur live AI demo call dekh lijiye, kaam pasand aaye tabhi aage badhna.",
        },
        "value_lines": [
            "Dhanda-type apps sirf content dete hain — hum content ke saath aapki har inquiry ko AI se CALL bhi karwate hain, India me sirf hamare paas.",
            "Shuru karne ke liye 10 FREE leads ka trial milta hai — risk zero.",
            "Festival posts, Google ranking aur AI receptionist — teeno ek hi price me.",
        ],
        "closing": "Toh sir, main aapka FREE Google Business audit aur ek AI demo call book kar deti hoon — aaj shaam ya kal subah, kaunsa time theek rahega?",
    },

    # ====================================================================== #
    # GENERAL FALLBACK — baaki saare niches (real_estate_luxury, modular_kitchen,
    # hair_transplant, immigration, custom niches, etc.) yahi use karte hain.
    # ====================================================================== #
    "general": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapne hamari service ke baare me poocha tha, bas 1 minute baat ho sakti hai?",
        "discovery": [
            "Aap exactly kis cheez ki talaash me hain?",
            "Budget ya timeline kya soch rahe hain?",
            "Pehle kabhi yeh service li hai ya pehli baar dekh rahe hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par jo value milti hai uske saamne yeh investment chhota lagta hai — aur EMI/flexible option bhi hai.",
            "abhi_nahi": "Koi baat nahi sir, bas ek free consultation le lijiye — poori jaankari le ke baad me aaram se decide karein.",
            "soch_ke": "Zaroor sochiye sir, bas batayein kis baat pe doubt hai — taaki main aapko sahi jaankari de sakoon.",
            "pehle_se_hai": "Achhi baat hai sir, ek baar compare kar lijiye — ho sakta hai hum aapko behtar deal de payein.",
            "bharosa": "Bilkul sahi sawaal hai sir, aap hamare reviews aur past customers se khud verify kar sakte hain.",
        },
        "value_lines": [
            "Aapki zaroorat ke hisaab se best option aur transparent pricing dete hain.",
            "Free consultation me poori jaankari milti hai, koi obligation nahi.",
        ],
        "closing": "Toh ek short call ya visit fix karein — aaj shaam ya kal, jo aapko convenient ho?",
    },
}


# ========================================================================== #
# Readable labels for KB strings (KB me niche/objection naam saaf dikhe)
# ========================================================================== #

_NICHE_LABELS: dict[str, str] = {
    "real_estate": "real estate (site visit)",
    "solar_residential": "residential solar",
    "studying_abroad": "study abroad counselling",
    "insurance": "health/term insurance",
    "coaching": "coaching institute (NEET/JEE)",
    "home_loans": "home loan / balance transfer",
    "interior_designers": "interior design",
    "dental_implants": "dental implants",
    "ai_marketing": "AI marketing services (B2B, business owners)",
    "general": "general sales call",
}

_OBJ_LABELS: dict[str, str] = {
    "mehenga": "price / too expensive",
    "abhi_nahi": "not now / timing",
    "soch_ke": "need to think about it",
    "pehle_se_hai": "already have it",
    "bharosa": "trust / credibility",
}


# ========================================================================== #
# Tiny helpers (pure, no side effects)
# ========================================================================== #

def get_script(niche_key: str) -> dict:
    """Return the script-block for a niche, ya 'general' fallback.

    Builtin priority niches ke liye custom script, baaki sab (incl. custom
    niches) ke liye general. Hamesha ek valid dict return karta hai.
    """
    if niche_key and niche_key in NICHE_SCRIPTS:
        return NICHE_SCRIPTS[niche_key]
    return NICHE_SCRIPTS["general"]


def kb_documents(niche_key: str) -> list[str]:
    """Niche script ko chhote standalone fact/example strings me flatten karo.

    Output KB embedding ke liye ready hai (har string self-contained sentence).
    Covered niche ka apna data; uncovered niche general script pe map hota hai.
    """
    script = get_script(niche_key)
    label = _NICHE_LABELS.get(niche_key, niche_key.replace("_", " ") if niche_key else "general")
    docs: list[str] = []

    opening = script.get("opening")
    if opening:
        docs.append(f"Opening line for {label}: {opening}")

    for q in script.get("discovery", []):
        docs.append(f"Qualification question for {label}: {q}")

    for obj_key, rebuttal in script.get("objections", {}).items():
        obj_label = _OBJ_LABELS.get(obj_key, obj_key)
        docs.append(f"Objection ({obj_label}) rebuttal for {label}: {rebuttal}")

    for line in script.get("value_lines", []):
        docs.append(f"Value point for {label}: {line}")

    closing = script.get("closing")
    if closing:
        docs.append(f"Closing line for {label}: {closing}")

    return docs


__all__ = ["NICHE_SCRIPTS", "get_script", "kb_documents"]
