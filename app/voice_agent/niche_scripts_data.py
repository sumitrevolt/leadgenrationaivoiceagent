"""Niche telecaller script dataset — the NICHE_SCRIPTS dict (per-niche Hinglish call scripts).

Extracted from app/voice_agent/niche_scripts.py (2026-06-20 refactor) — pure data, re-exported.
"""

from app.voice_agent.universal_pitch import INTEREST_ASK, PITCH_SHORT, UNIVERSAL_AGENT_INTRO

NICHE_SCRIPTS: dict[str, dict] = {
    # ====================================================================== #
    # PRIORITY NICHES (researched, niche-specific)
    # ====================================================================== #
    "real_estate_luxury": {
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
            "abhi_nahi": "Theek hai sir, par batches jaldi bhar jaate hain — ek free demo class aur counselling le lijiye, decision aaram se kar lijiye.",
            "soch_ke": "Zaroor sir, bachche ko ek free demo class dilwa dijiye — faculty aur padhai dekh ke aap dono saath me decide kar lijiye.",
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
            "soch_ke": "Zaroor sochiye sir, main aapki eligibility aur EMI ka number WhatsApp pe bhej deta hoon — dekh ke aaram se decide kar lijiye.",
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
        "opening": UNIVERSAL_AGENT_INTRO,
        "pitch_short": PITCH_SHORT,
        "interest_ask": INTEREST_ASK,
        "yes_praise": (
            "Theek — pehle aapki situation samajh leti hoon. "
            "Marketing abhi khud karte ho, staff se, ya agency?"
        ),
        "no_convince_once": (
            "Samajh sakti hoon — 7 din ka FREE trial hai, pehle result dekho phir decide."
        ),
        "close_cold": "Theek hai, shukriya — din shubh!",
        "discovery": [
            "Marketing abhi khud karte ho, staff se, ya agency?",
            "Google pe search karne par upar dikhta hai kya?",
            "Social pe regular post ho paata hai, ya time nahi milta?",
            "Mahine me marketing pe approx kitna kharcha?",
        ],
        "objections": {
            "mehenga": "₹1,999/mahina se shuru — din me ₹40 se kam. Ek extra customer se kharcha nikal jaata hai.",
            "abhi_nahi": "Koi baat nahi — tab tak FREE Google audit karwa doon? Score aur fixes, koi charge nahi.",
            "soch_ke": "Bilkul sochiye — FREE audit bhej deti hoon, 7-din trial bhi hai, aaram se decide kijiye.",
            "pehle_se_hai": "Agency ₹15-25K leti hai, hum ₹1,999 se. Inquiry follow-up bhi AI se ho jaata hai.",
            "bharosa": "Sahi sawaal — pehle FREE audit aur trial lijiye, pasand aaye tabhi aage badhiye.",
        },
        "value_lines": [
            "Roz ke posts, festival posters aur Google profile — sab automatic, aapka time bachta hai.",
            "7 din FREE trial — bina card, pehle result dekho.",
            "Advanced me inquiry pe 2 minute me AI callback bhi — koi lead miss nahi.",
        ],
        "closing": "Toh FREE Google audit abhi bhej doon? Saath me 7-din trial — aaj ya kal set kar doon?",
    },
    # ====================================================================== #
    # ADDITIONAL NICHE SCRIPTS (29 niches — professionally researched Hinglish)
    # ====================================================================== #
    "solar_commercial": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — commercial solar pe aapki factory ya warehouse ke liye baat karni thi, bas 1 minute denge?",
        "discovery": [
            "Aapki factory ya building ka monthly electricity bill kitna hai — 50,000 se zyada?",
            "Roof ka ownership aapka hai, aur kitna area available hai roughly?",
            "Koi solar vendor se pehle quote liya hai ya pehli baar explore kar rahe hain?",
            "Capex khud lagayenge ya OPEX/lease model prefer karenge?",
        ],
        "objections": {
            "mehenga": "Sir 100kW ke upar project me ROI 3-4 saal me aata hai — OPEX model me toh zero upfront lagta hai, sirf bijli bill ka paisa solar me jaata hai.",
            "abhi_nahi": "Bilkul sir, abhi koi pressure nahi — bas ek free site survey karwa lijiye, potential savings ka exact number saamne aa jayega.",
            "soch_ke": "Zaroor sochiye sir, main ek case study bhejta hoon jisme aap jaisi industry ka ROI calculation hai — dekh ke decide karein.",
            "pehle_se_hai": "Achha sir, pehle se hai toh O&M aur performance audit me help kar sakte hain — current system peak pe kaam kar raha hai kya?",
            "bharosa": "Bilkul sahi sawaal sir, hum MNRE-empanelled vendor hain aur bank-funded projects pe bhi kaam karte hain — references de sakte hain.",
        },
        "value_lines": [
            "Commercial solar pe electricity cost 60-70% tak gir jaati hai aur GST input credit bhi milta hai.",
            "OPEX model me zero investment, aur performance guarantee ke saath 25 saal ki savings.",
        ],
        "closing": "Toh sir, ek free site survey aur savings estimate fix kar dein — is hafte kaunsa din convenient rahega?",
    },
    "modular_kitchen": {
        "opening": "Namaste madam/sir, main [Company] se [Name] bol raha hoon — aapne modular kitchen ke liye interest dikhaya tha, bas 2 minute baat kar sakte hain?",
        "discovery": [
            "Kitchen ka size roughly kitna hai — 8x8 ya bada?",
            "Property ready-to-move hai ya abhi renovation chal raha hai?",
            "Budget approx kya hai — ek lakh ke andar ya premium range dekh rahe hain?",
            "German hardware jaise Hettich/Blum prefer karenge ya local fittings theek hai?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par modular kitchen ek baar ka 10-15 saal ka investment hai — hum aapke budget me best material shorlist karte hain, aur EMI bhi available hai.",
            "abhi_nahi": "Koi baat nahi sir, bas ek free 3D design aur quote banwa lijiye — ghar dekhte hi judge kar sakenge, material aur finish ka idea ho jayega.",
            "soch_ke": "Zaroor sochiye sir, main factory visit arrange kar sakta hoon — material aur finish khud touch karke decide karna kaafi aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, ek comparison quote lene me kya harj hai — design, material quality aur price teen cheez saamne aayengi.",
            "bharosa": "Bilkul sir, hum 5+ saal se kaam kar rahe hain — installed kitchens ki photos aur customers se baat karwa sakte hain.",
        },
        "value_lines": [
            "Factory-made precision fit, German hardware aur 5-year warranty — ek baar sahi lagao, baarbar repair khatam.",
            "Free 3D design, home visit aur no-cost EMI — poora process hamaara, aapko bas pasand karna hai.",
        ],
        "closing": "Toh sir, ek free measurement aur 3D design visit fix karein — kal ya parso, hamare designer aapke ghar aa sakte hain?",
    },
    "hair_transplant": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — hair restoration ke liye aapne inquiry ki thi, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Kitne saal se hair loss ho raha hai, aur family me bhi yeh issue hai?",
            "Koi doctor ya clinic se pehle advice liya hai?",
            "FUE procedure ke baare me suna hai aapne?",
            "Aap hamare city me hi rehte hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par transplant ek permanent solution hai — temporary treatments pe jo paisa baar-baar jaata hai, usse zyada cost-effective hai. No-cost EMI bhi available hai.",
            "abhi_nahi": "Theek hai sir, par hair loss ruk nahi ruka — ek free consultation le lijiye, doctor grafts ka estimate aur best time bata denge.",
            "soch_ke": "Zaroor sochiye sir, bas ek free consultation le lijiye — doctor aapki scalp dekh ke realistic result batayenge, koi commitment nahi.",
            "pehle_se_hai": "Achha sir, different clinics me quality aur result kaafi vary karta hai — ek free second opinion lena sahi decision lene me help karega.",
            "bharosa": "Bilkul sir, hamare results photos aur patient reviews online hain — aap khud dekh sakte hain, aur clinic visit pe past patients se baat karwa sakte hain.",
        },
        "value_lines": [
            "FUE transplant natural result deta hai — koi stitch nahi, tezi se recovery, aur baale permanent hain.",
            "Free consultation me grafts count, cost aur expected result ki poori clarity milti hai.",
        ],
        "closing": "Toh sir, ek free scalp analysis aur consultation fix kar dein — is hafte doctor se milne ka slot reserve kar doon?",
    },
    "ivf_clinics": {
        "opening": "Namaste madam, main [Company] se [Name] bol raha hoon — IVF ya fertility ke baare me aapne poocha tha, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Kitne time se family planning try kar rahe hain?",
            "Koi doctor se pehle checkup ya test hua hai?",
            "Aap humare city me hi hain?",
            "Funding ke liye koi concern hai ya EMI option jaanna chahte hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon madam, IVF ek bada financial aur emotional decision hai — hum transparent costing dete hain aur EMI aur insurance reimbursement me bhi help karte hain.",
            "abhi_nahi": "Koi pressure nahi madam, bas ek free initial consultation le lijiye — doctor current situation assess karenge aur best next step batayenge.",
            "soch_ke": "Zaroor sochiye madam, yeh personal decision hai — ek free consultation me sirf clarity milegi, koi commitment nahi.",
            "pehle_se_hai": "Achhi baat hai madam, ek second opinion lena sahi rehta hai — success rates, protocol aur costs compare kar lene me samajhdaari hai.",
            "bharosa": "Bilkul sahi madam, hamare success rates aur IVF cycles ke outcomes aap website pe dekh sakte hain — doctor se bhi openly pooch sakte hain.",
        },
        "value_lines": [
            "Empathetic care, transparent costing aur high success rates — starting point se final step tak hamaara team saath rehta hai.",
            "Free initial consultation me fertility assessment, treatment roadmap aur cost clarity — sab ek visit me.",
        ],
        "closing": "Toh madam, ek free initial consultation fix karein — doctor se milna sabse pehla sahi step hai, is hafte kaunsa din theek rahega?",
    },
    "immigration": {
        "opening": "Hello sir, main [Company] se [Name] bol raha hoon — Canada ya Australia PR ke liye aapne inquiry ki thi, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Kaunsa country aur visa category dekh rahe hain — Canada Express Entry, Australia 189, ya UK Skilled?",
            "Current qualification aur work experience kitne saal ka hai?",
            "IELTS ya PTE score ready hai ya abhi tayari chal rahi hai?",
            "Timeline kya soch rahe hain — is saal apply karna hai?",
        ],
        "objections": {
            "mehenga": "Sir hamari eligibility assessment free hai — aage ka process step-by-step hota hai, aur hum tab tak fees nahi lete jab tak file actually process nahi hoti.",
            "abhi_nahi": "Theek hai sir, par PR points har saal change hote hain — ek free eligibility check se pata chal jayega abhi apply karna sahi waqt hai ya nahi.",
            "soch_ke": "Zaroor sochiye sir, main aapka free eligibility score nikaal deta hoon — number saamne aayega toh decision aasaan ho jayega.",
            "pehle_se_hai": "Achha sir, ek second opinion lene me kya harj hai — kabhi kabhi ek minor documentation difference success aur rejection ka farak ban jaata hai.",
            "bharosa": "Bilkul sir, hum ICCRC/MARA registered hain aur is saal ke success cases aap dekh sakte hain — visa approvals proof ke saath.",
        },
        "value_lines": [
            "Free eligibility check me aapka actual CRS/points score aur best pathway clear ho jaata hai.",
            "End-to-end support — eligibility se lekar visa approval tak, ek consultant hamaara hamaara saath rehta hai.",
        ],
        "closing": "Toh sir, ek free eligibility assessment fix kar dein — 15 minute me aapka actual score pata chal jayega, kal ya parso kaunsa time theek rahega?",
    },
    "upskilling": {
        "opening": "Hello sir, main [Company] se [Name] bol raha hoon — professional certification ya upskilling program ke baare me baat karni thi, abhi 2 minute de sakte hain?",
        "discovery": [
            "Abhi kaunsa field me kaam kar rahe hain, aur kaunse skills upgrade karna chahte hain?",
            "Full-time job ke saath karna hai, ya weekends pe?",
            "Budget approx kitna soch rahe hain — EMI prefer karenge?",
            "Certificate ya actual job change ke liye yeh program le rahe hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par course complete hone ke baad average salary hike 30-50% tak hota hai — EMI me sirf ₹2-3K mahine me shuru hota hai.",
            "abhi_nahi": "Theek hai sir, par next batch jaldi bhar jaata hai — ek free career counselling session le lijiye, next step clear ho jayega.",
            "soch_ke": "Zaroor sochiye sir, ek free demo class le lijiye — instructor, content aur format dekh ke aap khud decide kar lijiye.",
            "pehle_se_hai": "Achha sir, agar course chal raha hai toh kaunsa hai — sometimes ek advanced ya specialized certification salary me bada jump deta hai.",
            "bharosa": "Bilkul sir, placement records aur alumni salary data publicly available hai — aap dekh sakte hain, aur alumni se bhi baat karwa sakte hain.",
        },
        "value_lines": [
            "Industry-recognized certificate, live projects aur placement support — career mein real jump ka shortcut.",
            "Flexible schedule — job ke saath weekends ya live + recorded mix me complete hota hai.",
        ],
        "closing": "Toh sir, ek free demo class aur counselling session fix karein — kal shaam ya is weekend, jo aapko suit kare?",
    },
    "recruitment": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — hiring aur recruitment automation ke baare me baat karni thi, 2 minute baat ho sakti hai?",
        "discovery": [
            "Aap abhi kaunsi roles ke liye hire kar rahe hain — IT, sales, operations?",
            "Monthly kitne candidates screen karne padthe hain approximately?",
            "Abhi bulk screening manually hoti hai ya koi tool use karte hain?",
            "Employer side hai ya candidate placement side bhi karte hain?",
        ],
        "objections": {
            "mehenga": "Sir cost per hire calculate karein — ek placement pe jo 8-10% CTC milti hai, hamaara monthly cost ek hire me hi cover ho jaata hai.",
            "abhi_nahi": "Koi baat nahi sir, bas ek demo dekh lijiye — 200 candidates ko 30 minute me screen karna live dekhne ke baad decision aasaan ho jaata hai.",
            "soch_ke": "Zaroor sochiye sir, main ek free pilot run offer kar sakta hoon — 50 candidates screen karwayein, result dekh ke decide karein.",
            "pehle_se_hai": "Achha sir, jo tool use karte hain usse compare karein — speed, qualification accuracy aur cost per screen me difference clearly dikhega.",
            "bharosa": "Bilkul sir, hamare clients ke placement numbers aur time-to-hire data share kar sakte hain — references bhi de sakte hain.",
        },
        "value_lines": [
            "200+ candidate screening ek din me — AI sab primary screening karta hai, aap sirf shortlist dekhte hain.",
            "Employer side BD calls aur candidate screening dono automate hota hai — ek tool, dono kaam.",
        ],
        "closing": "Toh sir, ek 15-minute demo fix karein — live screening dekh ke aap khud judge kar lijiye, is hafte kab convenient hai?",
    },
    "hvac_commercial": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — commercial AC aur HVAC ke liye aapko contact kiya tha, abhi 1 minute baat ho sakti hai?",
        "discovery": [
            "Kitna area cover karna hai — office, warehouse ya IT park?",
            "New installation chahiye ya existing system ka AMC aur maintenance?",
            "Abhi kaun service karta hai, koi contract chal raha hai?",
            "Decision aap karte hain ya purchase manager alag hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par AMC mein emergency breakdown cost compare karein — annual contract mein unexpected kharch zero hota hai aur uptime guarantee milti hai.",
            "abhi_nahi": "Koi baat nahi sir, bas ek free site audit karwa lijiye — current system ki condition aur energy wastage ka honest report milega.",
            "soch_ke": "Zaroor sochiye sir, main ek detailed proposal aur case study bhej deta hoon — dono compare kar ke decide kar lijiye.",
            "pehle_se_hai": "Achha sir, comparison quote aur service SLA dekh lein — response time aur parts availability ek hi jagah kaafi vary karta hai.",
            "bharosa": "Bilkul sir, hum 50+ commercial sites serve karte hain — site visit pe kuch references bhi de sakte hain is area mein.",
        },
        "value_lines": [
            "Dedicated AMC mein emergency pe 4-hour response SLA milta hai — downtime zero rakhta hai.",
            "Energy audit ke baad average 20-25% bijli bill reduction possible hota hai commercial buildings mein.",
        ],
        "closing": "Toh sir, ek free site audit aur proposal fix kar dein — is hafte engineer bhejna theek rahega?",
    },
    "travel_packages": {
        "opening": "Hello sir, main [Company] se [Name] bol raha hoon — international travel package ke liye aapne interest dikhaya tha, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Kaunsi destination soch rahe hain — Europe, Southeast Asia, ya Dubai/Maldives?",
            "Dates roughly kab ki hain — kitne logon ke saath?",
            "Budget per person approx kitna comfortable rahega?",
            "Visa aur flights khud book karenge ya packaged prefer karenge?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, hum aapke budget mein hi best itinerary banate hain — aur early booking mein flights 20-30% saste milte hain jo total cost kam kar deta hai.",
            "abhi_nahi": "Theek hai sir, par peak season slots jaldi bhar jaate hain — ek free itinerary aur quote banwa lijiye, dates aur cost clear ho jaayegi.",
            "soch_ke": "Zaroor sochiye sir, main ek detailed day-wise itinerary aur all-inclusive quote bhej deta hoon — saamne dekh ke decide karna aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, compare karna sahi hai — hum same dates ke liye hotels, flights aur inclusions ki breakdown bhej sakte hain, aap khud judge karein.",
            "bharosa": "Bilkul sir, hum IATA registered agent hain aur 500+ families is saal travel karwa chuke hain — reviews aur bookings sab verifiable hain.",
        },
        "value_lines": [
            "Visa, flights, hotels, transfers, sightseeing — ek price mein sab, koi hidden charge nahi.",
            "24/7 travel support — destination pe koi problem ho toh team turant available hai.",
        ],
        "closing": "Toh sir, ek free custom itinerary aur quote banwa lijiye — destination aur dates bata dein, aaj hi bhej deta hoon?",
    },
    "packers_movers": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — shifting ke liye aapne inquiry ki thi, abhi 1 minute baat ho sakti hai?",
        "discovery": [
            "Shifting kab karni hai — dates confirm hain?",
            "Kitne BHK ka saman hai, aur kahan se kahan shift karna hai?",
            "Car bhi shift karni hai ya sirf household?",
            "Storage ki zaroorat padegi kya transit mein?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par hum full packing, loading, transit insurance aur unloading sab include karte hain — chhupa hua charge zero, upfront price pakka milta hai.",
            "abhi_nahi": "Koi baat nahi sir, date aane pe confirm kar lena — bas pehle se quote le lein taaki rate lock ho jaye, peak season mein cost badhti hai.",
            "soch_ke": "Zaroor sochiye sir, main written quote bhej deta hoon aaj — items list share karein, pakka estimate ho jaayega.",
            "pehle_se_hai": "Achha sir, compare karna sahi hai — hum transit insurance, GPS tracking aur packing quality mein kya dete hain, ek baar detail dekh lein.",
            "bharosa": "Bilkul sir, hum IBA-approved mover hain aur saman ka full insurance milta hai — 1000+ verified reviews Google pe available hain.",
        },
        "value_lines": [
            "Full packing, transit insurance aur GPS tracking — saman 100% safe, delay zero.",
            "Fixed price quote pehle — shifting ke baad koi extra bill nahi aayega.",
        ],
        "closing": "Toh sir, exact items list share karein aur quote confirm kar dein — shifting date pakki hai toh slot book kar deten hain abhi?",
    },
    "hotels_mice": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — corporate event ya MICE booking ke liye aapko contact kiya tha, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Event kab ka hai aur kitne delegates expect kar rahe hain?",
            "Conference hall chahiye ya full offsite package — stay plus meals?",
            "Budget per head roughly kitna hai?",
            "Any specific AV setup ya catering requirement hai?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par hum corporate rates aur custom packages dete hain — per head cost aur inclusive add-ons ke saath comparison karein, value clearly dikhegi.",
            "abhi_nahi": "Theek hai sir, par dates ke aas-paas availability tight ho jaati hai — ek tentative hold le lete hain, cancel karna free hai.",
            "soch_ke": "Zaroor sochiye sir, main ek detailed proposal aur site visit arrange kar sakta hoon — hall aur setup khud dekh ke comfortable rahenge.",
            "pehle_se_hai": "Achha sir, ek comparison quote lene me kya jaata hai — AV, catering aur service quality pe clear fark dikhega.",
            "bharosa": "Bilkul sir, hum 100+ corporate events har saal handle karte hain — client references aur past event photos share kar sakte hain.",
        },
        "value_lines": [
            "Dedicated event manager, custom catering aur full AV setup — aap event pe focus karein, logistics humara kaam.",
            "Corporate billing, GST invoice aur group room rates — company ke liye convenient sab ek jagah.",
        ],
        "closing": "Toh sir, ek site visit aur proposal fix karein — is hafte ek half-hour call ya property tour arrange kar sakte hain?",
    },
    "digital_marketing": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — digital marketing aur online leads ke baare mein baat karni thi, abhi 2 minute de sakte hain?",
        "discovery": [
            "Abhi Google ya Meta ads chal rahe hain, ya organic pe hain?",
            "Monthly marketing budget roughly kitna hai?",
            "Leads aa rahe hain ya sirf visibility chahiye?",
            "Kaunsa channel best work kiya hai aapke liye ab tak?",
        ],
        "objections": {
            "mehenga": "Sir, ek qualified lead ki value sochein — ₹15-25K agency fees ek bhi converted customer mein nikal aati hai. Hum ROI guarantee ke saath kaam karte hain.",
            "abhi_nahi": "Theek hai sir, tab tak ek free website aur Google audit karwa lijiye — where you are vs where you could be, data clearly dikhega.",
            "soch_ke": "Zaroor sochiye sir, main ek free audit report bhej deta hoon — current performance aur exact gaps saamne aa jaayenge.",
            "pehle_se_hai": "Achha sir, ek audit aur comparison karwa lein — lead quality, cost per lead aur ROAS mein fark dikhna chahiye.",
            "bharosa": "Bilkul sir, hum kisi bhi client ka case study aur results share kar sakte hain — kaam se pehle 1-month trial bhi offer karte hain.",
        },
        "value_lines": [
            "ROI-focused campaigns — har rupee ka performance track hota hai, monthly report milti hai.",
            "SEO plus paid ads dono — organic + paid channel se leads dono jagah se aate hain.",
        ],
        "closing": "Toh sir, pehle ek free audit aur call fix karein — aaj ya kal, 30 minute mein current gaps aur roadmap clear ho jaayega?",
    },
    "ca_legal": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — business registration ya GST/tax compliance ke liye aapne inquiry ki thi, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Company register karna hai — Private Ltd, LLP ya Proprietorship?",
            "GST registration already hai ya abhi lena hai?",
            "Accounting aur ITR koi handle kar raha hai ya aap khud karte hain?",
            "Koi specific compliance issue chal raha hai abhi?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par non-compliance ka penalty aur notice ka stress zyada mehnga padta hai — hum transparent fixed fees mein sab handle karte hain.",
            "abhi_nahi": "Theek hai sir, par government deadlines aur notices wait nahi karte — ek free consultation le lijiye, kya urgent hai pata chal jaayega.",
            "soch_ke": "Zaroor sochiye sir, ek free 15-minute consultation mein scope aur cost dono clear ho jaayenge — koi commitment nahi.",
            "pehle_se_hai": "Achha sir, ek second review lena sahi hai — kabhi kabhi ek filing mein chhoti galti bhi notice trigger karti hai.",
            "bharosa": "Bilkul sir, hum ICAI-registered CAs hain aur client references aur past filings sab verifiable hain.",
        },
        "value_lines": [
            "Company registration se leke annual compliance — ek hi team, koi kaam chhootega nahi.",
            "Dedicated CA, response within 24 hours aur digital filings — physical office ke bina sab ho jaata hai.",
        ],
        "closing": "Toh sir, ek free 15-minute consultation fix karein — aaj ya kal, exact requirement aur cost clear ho jaayegi?",
    },
    "restaurant_cafe": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapke restaurant ki online visibility aur orders badhane ke baare mein baat karni thi, abhi 2 minute denge?",
        "discovery": [
            "Abhi Zomato, Swiggy ya Google pe listed hain?",
            "Dine-in plus delivery dono hain ya sirf ek?",
            "Social media pe active hain ya mein pehli baar soch rahe hain?",
            "Monthly marketing pe kuch budget hai ya abhi zero?",
        ],
        "objections": {
            "mehenga": "Sir, ek table ya 5 extra orders per day se jo revenue aata hai, hamaara poora monthly fee cover ho jaata hai — low risk, high return.",
            "abhi_nahi": "Theek hai sir, tab tak ek free Google Business audit karwa lijiye — aapka restaurant search mein kahan hai abhi, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, main ek free audit report bhej deta hoon — Zomato rating improvement aur Google ranking gap clearly dikhega.",
            "pehle_se_hai": "Achha sir, agency se compare karein — hum content ke saath review management aur AI inquiry follow-up bhi karte hain, agency sirf post deti hai.",
            "bharosa": "Bilkul sir, similar restaurants ke results aur reviews share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Festive posts, menu highlights, Zomato review replies aur Google ranking — ek package mein sab.",
            "AI se reservation aur delivery inquiry follow-up — missed order zero, repeat customer zyada.",
        ],
        "closing": "Toh sir, pehle free Google aur Zomato audit karwa lein — 15 minute mein exact score aur improvement plan saamne aa jaayega, kab convenient hai?",
    },
    "automobile_service": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — car service center ki online visibility aur service bookings badhane ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Abhi workshop Google pe search mein dikhta hai — koi Google reviews hain?",
            "Bookings kaise aate hain — walk-in, phone ya online?",
            "Periodic service reminder clients ko bhejte hain ya manually track karte hain?",
            "Multi-brand hai ya brand-specific authorized center?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra service booking per day se monthly fee nikal aati hai — aur regular customers ka lifetime value kaafi bada hota hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google audit karwa lijiye — kitne searches miss ho rahe hain aur review score kahan hai, sab data saamne aayega.",
            "soch_ke": "Zaroor sir, main ek free audit report bhej deta hoon — aap wahan actual numbers dekh ke decide karein.",
            "pehle_se_hai": "Achha sir, compare karna sahi hai — service reminders aur AI inquiry follow-up koi aur de raha hai kya? Woh bhi check karein.",
            "bharosa": "Bilkul sir, similar workshops ke Google ranking aur review improvement results share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Automatic service reminders — customers waqt pe aate hain, business consistent rehta hai.",
            "Google reviews aur local SEO — workshop area mein number 1 dikhne lagta hai.",
        ],
        "closing": "Toh sir, pehle free Google audit karwa lein — exact gaps aur next steps 15 minute mein clear ho jaayenge, kab convenient hai?",
    },
    "photography_studio": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — photography studio ya videography bookings badhane ke baare mein baat karni thi, abhi 2 minute denge?",
        "discovery": [
            "Kaunse events cover karte hain — weddings, corporate, product?",
            "Bookings mostly referral se aate hain ya online inquiry bhi hoti hai?",
            "Instagram ya portfolio website hai — inquiries kahan se aati hain?",
            "Peak season mein kitne bookings per month handle karte hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra wedding booking per month hamaari poori fees cover kar deta hai — aur off-season mein bhi inquiries consistently aane lagte hain.",
            "abhi_nahi": "Koi baat nahi sir, ek free portfolio audit karwa lijiye — Instagram aur Google pe aapka studio kaise dikhta hai, honest feedback milega.",
            "soch_ke": "Zaroor sochiye sir, main ek free audit bhej deta hoon — portfolio visibility aur inquiry conversion mein exact gap saamne aayega.",
            "pehle_se_hai": "Achha sir, ek comparison karein — inquiry follow-up aur booking automation dono koi karta hai kya currently?",
            "bharosa": "Bilkul sir, similar studios ke results aur before-after booking stats share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Portfolio showcase, Instagram growth aur inquiry follow-up automation — sirf referral pe depend nahi rehna padega.",
            "Booking confirmation aur reminder — client experience smooth, no-show zero.",
        ],
        "closing": "Toh sir, ek free portfolio aur online presence audit fix karein — 15 minute mein exact gaps clear ho jaayenge, kab suit karega?",
    },
    "pharmacy_medical": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — pharmacy ya medical store ki online visibility aur home delivery orders ke baare mein baat karni thi, abhi 2 minute?",
        "discovery": [
            "Abhi home delivery service hai ya sirf walk-in?",
            "Google Business listing hai, aur reviews kuch hain?",
            "WhatsApp pe orders aate hain ya koi platform use karte hain?",
            "Single store hai ya chain?",
        ],
        "objections": {
            "mehenga": "Sir, area mein jo customers online order place karte hain unhe nearest pharmacy nahi milti — ek listing aur WhatsApp order system se unhe aap mil sakte hain, cost minimum hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google audit karwa lijiye — area mein kitne searches ho rahe hain aur aap miss kar rahe hain, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, main ek free audit aur demo bhej deta hoon — concrete number dekh ke decide karna aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, jo system hai usse compare karein — customer reminder aur repeat order automation milti hai?",
            "bharosa": "Bilkul sir, similar medical stores ke results aur reviews share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Google listing plus WhatsApp ordering — area ke online customers automatically aapko find karte hain.",
            "Refill reminders aur prescription follow-up — repeat customers consistently aate rehte hain.",
        ],
        "closing": "Toh sir, ek free Google audit fix karein — 15 minute mein exact opportunity saamne aayegi, kab convenient hai?",
    },
    "furniture_decor": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — furniture ya home decor showroom ki online visibility aur walk-in badhane ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Showroom hai ya online bhi sell karte hain?",
            "Custom furniture ya readymade collection?",
            "Abhi Google ya Instagram pe kuch visible hain?",
            "Zyada customers referral se aate hain ya search se?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra showroom visit per day se monthly fee easily nikal aati hai — aur repeat aur referral customers mein bhi kaafi difference aata hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google aur Instagram audit karwa lijiye — exactly kahan opportunity hai, data clearly dikhaayenge.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — aap concrete numbers dekh ke decide karein.",
            "pehle_se_hai": "Achha sir, compare karein — catalog showcase, AI inquiry follow-up aur review management sab ek jagah koi karta hai?",
            "bharosa": "Bilkul sir, similar showrooms ke results share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Catalog online showcase aur Google visibility — customers ghar se shortlist karke aate hain, walk-in quality better hoti hai.",
            "Festival offer posts aur inquiry follow-up automation — peak season mein inquiries miss nahi hoti.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact gaps aur action plan clear ho jaayega, kab suit karega?",
    },
    "kirana_supermarket": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — kirana store ya supermarket ki online ordering aur visibility ke baare mein baat karni thi, abhi 2 minute?",
        "discovery": [
            "Abhi home delivery service hai ya sirf walk-in?",
            "WhatsApp pe orders aate hain?",
            "Google Business listing hai — area mein search mein dikhte hain?",
            "Monthly turnover roughly kitna hai?",
        ],
        "objections": {
            "mehenga": "Sir, area mein jo ghar baithe order karna chahte hain unhe nearest store nahi milti — ek WhatsApp order system aur Google listing se unhe aap mil sakte hain, cost kaafi low hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google audit karwa lijiye — area mein kitne searches miss ho rahe hain woh dikhaayenge.",
            "soch_ke": "Zaroor sochiye sir, main ek free demo aur audit bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, jo system hai usse compare karein — customer offer notifications aur repeat order system milti hai?",
            "bharosa": "Bilkul sir, similar stores ke results share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "WhatsApp ordering plus Google listing — area ke regular customers automatically aapko prefer karte hain.",
            "Weekly offer notifications — footfall aur average basket size dono badhte hain.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein opportunity clear ho jaayegi, kab convenient hai?",
    },
    "travel_agency": {
        "opening": "Hello sir, main [Company] se [Name] bol raha hoon — domestic travel aur pilgrimage tour packages ke baare mein baat karni thi, abhi 2 minute denge?",
        "discovery": [
            "Domestic tours karte hain — Kedarnath, Shirdi, Vaishno Devi?",
            "Group tours hain ya family-custom packages bhi?",
            "Bookings kaahan se aate hain — walk-in, referral ya online?",
            "Peak season mein kitne groups handle karte hain approximately?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra group booking per month se hamaari fees nikal aati hai — off-season mein bhi consistent inquiries aane lagte hain online se.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google aur WhatsApp presence audit karwa lijiye — opportunity data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — aap numbers dekh ke decide karein.",
            "pehle_se_hai": "Achha sir, ek comparison karein — inquiry follow-up automation aur WhatsApp group booking koi karta hai currently?",
            "bharosa": "Bilkul sir, similar travel agencies ke results share kar sakte hain — ek free month trial pe bhi baat ho sakti hai.",
        },
        "value_lines": [
            "Tour package showcase online aur WhatsApp inquiry follow-up — referral pe depend nahi rehna padega.",
            "Festival aur holiday season offer posts — peak season pehle hi bookings full ho jaati hain.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact opportunity aur plan clear ho jaayega, kab suit karega?",
    },
    "gift_stationery": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — gift shop ya stationery store ki online visibility aur corporate gifting leads ke baare mein baat karni thi, abhi 2 minute?",
        "discovery": [
            "Retail walk-in hai ya corporate gifting orders bhi aate hain?",
            "Online store ya social media pe active hain?",
            "Festivals aur occasions pe special offers run karte hain?",
            "Bulk orders ke liye koi pricing hai?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par corporate gifting ek order se hi monthly cost nikal sakta hai — Diwali aur Christmas season mein bulk orders consistently aate hain online se.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google aur Instagram audit karwa lijiye — festival season se pehle visibility set ho jaaye toh kaafi difference aata hai.",
            "soch_ke": "Zaroor sochiye sir, main ek free audit bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, corporate gifting lead generation aur bulk inquiry follow-up koi karta hai currently?",
            "bharosa": "Bilkul sir, similar gift stores ke results share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Festival offer posts aur corporate gifting catalog online — bulk orders automatically aane lagte hain.",
            "AI inquiry follow-up — missed corporate gifting order zero, conversion better hoti hai.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact opportunity clear ho jaayegi, kab convenient hai?",
    },
    "hospital_appointments": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — hospital ya clinic ki appointment booking aur patient follow-up ke baare mein baat karni thi, abhi 2 minute denge?",
        "discovery": [
            "Specialty kya hai — general, ortho, eye, skin?",
            "Appointments phone pe hote hain ya online booking bhi hai?",
            "Missed appointments aur no-shows kitne hote hain?",
            "New patients kaahan se aate hain — referral ya Google search?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra appointment per day se monthly fee easily nikal aati hai — aur no-show reduction se doctor ka time aur revenue dono improve hota hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google aur online presence audit karwa lijiye — area mein kitne patients search karte hain aur aap miss karte hain, data aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — concrete numbers dekh ke decide karein.",
            "pehle_se_hai": "Achha sir, automated appointment reminders aur patient follow-up calls koi karta hai currently?",
            "bharosa": "Bilkul sir, similar clinics ke results aur patient satisfaction improvement share kar sakte hain.",
        },
        "value_lines": [
            "Automated appointment reminders — no-show rate 40-50% tak kam hoti hai, doctor ka schedule filled rehta hai.",
            "Google visibility aur AI inquiry follow-up — new patient acquisition consistent rehta hai.",
        ],
        "closing": "Toh sir, ek free audit aur demo fix karein — 15 minute mein exact gaps aur ROI clear ho jaayega, kab suit karega?",
    },
    "skin_dermatology": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — dermatology ya skin clinic mein high-value treatments ke patients badhane ke baare mein baat karni thi, abhi 2 minute?",
        "discovery": [
            "Acne, anti-aging, laser ya hair — kaunse treatments zyada hote hain?",
            "New patients kaahan se aate hain — Google, Instagram ya referral?",
            "Consultation patients mein kitne high-value procedures book karte hain?",
            "Social media pe before-after cases post karte hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra laser ya PRP session per week se hamaari poori fees easily cover ho jaati hai — before-after results dikhne se conversion rate kaafi badhta hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google aur Instagram audit karwa lijiye — current visibility aur patient acquisition gap saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, before-after content strategy aur AI inquiry follow-up koi karta hai currently?",
            "bharosa": "Bilkul sir, similar skin clinics ke results aur patient growth data share kar sakte hain.",
        },
        "value_lines": [
            "Before-after reels aur skin tip posts — Instagram se high-value consultation patients consistent aate hain.",
            "AI inquiry follow-up — consult booking mein no-show khatam, conversion better hoti hai.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact opportunity aur next steps clear ho jaayenge, kab suit karega?",
    },
    "finance_advisory": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — mutual fund, SIP ya wealth planning ke baare mein inquiry aai thi, abhi 2 minute baat ho sakti hai?",
        "discovery": [
            "Investments already chal rahe hain ya pehli baar shuru karna hai?",
            "Goal kya hai — retirement, child education, ya wealth creation?",
            "Monthly roughly kitna invest karna comfortable rahega?",
            "Risk appetite — safe FD-jaisa ya thoda market-linked?",
        ],
        "objections": {
            "mehenga": "Sir hamari advisory free hai pehle — SEBI-registered advisory mein clearly explained returns aur charges milte hain, hidden fee zero.",
            "abhi_nahi": "Theek hai sir, par SIP ki power compounding se hai — jitni jaldi shuru ho utna zyada growth. Ek free review se ideal start time pata chal jaayega.",
            "soch_ke": "Zaroor sochiye sir, main ek free financial snapshot banata hoon — current investments ka actual return vs potential clearly dikhega.",
            "pehle_se_hai": "Achha sir, portfolio review karwa lein — abhi jo hai uska actual return aur diversification theek hai kya, ek second opinion sahi rahega.",
            "bharosa": "Bilkul sir, hum SEBI-registered hain aur all recommendations documented hoti hain — aap khud verify kar sakte hain, koi pressure nahi.",
        },
        "value_lines": [
            "Goal-based planning — sirf products nahi, aapki actual financial goals ke liye sahi path.",
            "Transparent fees, SEBI-registered aur documented advice — sab kuch clearly aapko pata rehega.",
        ],
        "closing": "Toh sir, ek free 20-minute financial review fix karein — current position aur best next step clear ho jaayega, kab convenient hai?",
    },
    "edtech_creators": {
        "opening": "Hello sir, main [Company] se [Name] bol raha hoon — online course ya coaching content creators ke liye student acquisition aur monetization ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Kaunsa subject ya skill teach karte hain — aur kahan — YouTube, Instagram, ya koi platform?",
            "Abhi free content se paid course mein convert kaise karte hain?",
            "Monthly roughly kitne students enroll hote hain?",
            "Funnel mein kahan leak ho raha hai — awareness, interest ya conversion?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra paid enrollment per week se monthly cost easily nikal aata hai — automated funnel ek baar set karo, baar baar kaam karta hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free funnel audit karwa lijiye — inquiry se enrollment conversion mein exact gap saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, jo system hai usse compare karein — AI follow-up aur engagement automation ka fark clearly dikhega.",
            "bharosa": "Bilkul sir, similar creators ke results aur enrollment growth data share kar sakte hain — ek free trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Lead capture, automated follow-up aur paid conversion funnel — ek baar setup, constantly chalta rehta hai.",
            "AI se personalized follow-up — trial students paid mein convert zyada hote hain.",
        ],
        "closing": "Toh sir, ek free funnel audit fix karein — 15 minute mein exact leakage aur fix clearly dikhega, kab suit karega?",
    },
    "cloud_kitchen": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — cloud kitchen ya tiffin service ki online orders aur Swiggy/Zomato visibility ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Swiggy aur Zomato dono pe listed hain, ya sirf ek?",
            "Monthly roughly kitne orders hote hain?",
            "Average order value kitni hai?",
            "Rating aur reviews current mein kya hai?",
        ],
        "objections": {
            "mehenga": "Sir, ek extra 10 orders per day se monthly fee easily nikal aati hai — rating improvement aur better listing se organic orders automatically badhte hain.",
            "abhi_nahi": "Koi baat nahi sir, ek free Swiggy/Zomato aur Google audit karwa lijiye — exact ranking aur opportunity data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, ek comparison karein — review management aur Instagram food content dono koi karta hai currently?",
            "bharosa": "Bilkul sir, similar cloud kitchens ke before-after order growth share kar sakte hain.",
        },
        "value_lines": [
            "Zomato/Swiggy listing optimization aur food reels — organic visibility aur orders consistently badhte hain.",
            "Review management aur quick response — rating badhne pe platform boost milta hai, cost zero.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact opportunity aur action plan clear ho jaayega, kab convenient hai?",
    },
    "ayurveda_wellness": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — Ayurveda clinic ya wellness center mein patients aur bookings badhane ke baare mein baat karni thi, abhi 2 minute?",
        "discovery": [
            "Panchakarma, Abhyanga ya general wellness — kaunse treatments zyada hote hain?",
            "New patients kaahan se aate hain — Google, referral ya social media?",
            "Consultation packages hain ya per-session?",
            "Online presence hai — Google listing aur Instagram?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra wellness package booking per week se hamaari monthly fee easily cover ho jaati hai — Ayurveda trust-based hai, sahi content se patients khud aate hain.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google aur social media audit karwa lijiye — exact visibility gap saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, ek comparison karein — treatment education content aur AI inquiry follow-up koi karta hai currently?",
            "bharosa": "Bilkul sir, similar Ayurveda centers ke patient growth results share kar sakte hain.",
        },
        "value_lines": [
            "Treatment education posts aur before-after results — trust badhta hai, premium wellness seekers consistently aate hain.",
            "AI inquiry follow-up aur appointment booking — first inquiry se confirmed booking tak conversion better hoti hai.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact opportunity aur next steps clear ho jaayenge, kab suit karega?",
    },
    "event_management": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — event management company ki leads aur corporate events bookings badhane ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Kaunse events specialize karte hain — weddings, corporate, birthday ya MICE?",
            "Bookings zyada referral se aate hain ya online inquiry bhi hoti hai?",
            "Peak season mein kitne events per month handle karte hain?",
            "Corporate clients ke liye dedicated sales team hai?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra corporate event booking se hamaari kaafi saari fees nikal aati hain — off-season mein bhi consistent leads online se aane lagte hain.",
            "abhi_nahi": "Koi baat nahi sir, ek free audit karwa lijiye — Google aur Instagram pe visibility kahan hai, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, ek comparison karein — event portfolio showcase aur AI corporate inquiry follow-up koi karta hai currently?",
            "bharosa": "Bilkul sir, similar event companies ke results aur booking growth data share kar sakte hain.",
        },
        "value_lines": [
            "Event portfolio showcase online aur corporate inquiry AI follow-up — referral pe depend nahi rehna padega.",
            "Festival aur season-specific packages push — inquiries consistently aane lagte hain.",
        ],
        "closing": "Toh sir, ek free audit fix karein — 15 minute mein exact opportunity aur plan clear ho jaayega, kab suit karega?",
    },
    "hardware_paint": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — hardware ya paint shop ki online visibility aur bulk/contractor leads ke baare mein baat karni thi, abhi 2 minute?",
        "discovery": [
            "Retail plus contractor supply dono hain ya sirf retail?",
            "Google Business listing hai — area mein search mein dikhte hain?",
            "Contractors aur builders ke liye koi loyalty ya credit scheme hai?",
            "Paint brands kaun se carry karte hain?",
        ],
        "objections": {
            "mehenga": "Samajhta hoon sir, par ek extra contractor account per month se hamaari fees easily nikal aati hai — bulk buyers Google se dhoondhte hain, listing sahi ho toh consistently aate hain.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google audit karwa lijiye — area mein kitne searches miss ho rahe hain, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, ek free audit report bhej deta hoon — numbers saamne aaye toh decision aasaan ho jaata hai.",
            "pehle_se_hai": "Achha sir, ek comparison karein — contractor loyalty program promotion aur seasonal offer posts koi karta hai currently?",
            "bharosa": "Bilkul sir, similar hardware stores ke Google ranking improvement aur lead growth share kar sakte hain.",
        },
        "value_lines": [
            "Google Business optimization — contractor aur builder searches mein pehle dikhna shuru ho jaata hai.",
            "Seasonal offer posts aur contractor loyalty scheme promotion — repeat bulk buyers consistently aate hain.",
        ],
        "closing": "Toh sir, ek free Google audit fix karein — 15 minute mein exact opportunity aur action plan clear ho jaayega, kab convenient hai?",
    },
    # ====================================================================== #
    # HOME/SERVICE NICHE SCRIPTS (added with wizard business types)
    # ====================================================================== #
    "tiffin_service": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapki tiffin service ki online visibility aur naye monthly customers ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Abhi monthly subscriptions kaise aate hain — word of mouth, WhatsApp ya online?",
            "Kitne customers ko roz tiffin jaati hai aur kitne slots bache hain?",
            "Zomato/Swiggy pe listed hain ya sirf local area mein hi kaam karte hain?",
            "Office ya home delivery — konsa segment bada hai?",
        ],
        "objections": {
            "mehenga": "Sir, ek extra monthly subscription per week se poora monthly fee cover ho jaata hai — aur slots bhi fixed rehte hain, risk nahi.",
            "abhi_nahi": "Koi baat nahi sir, tab tak ek free Google audit karwa lijiye — aapki service area mein kitne log tiffin dhoondh rahe hain, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, main ek free audit report bhej deta hoon — online visibility aur inquiry flow ka exact gap clearly dikhega.",
            "pehle_se_hai": "Achha sir, compare karein — hum review management aur WhatsApp inquiry follow-up bhi karte hain, sirf post nahi.",
            "bharosa": "Bilkul sir, similar tiffin services ke results share kar sakte hain — ek free month trial pe bhi baat kar sakte hain.",
        },
        "value_lines": [
            "Menu posts, Google reviews aur WhatsApp orders — monthly subscriptions consistently aate hain.",
            "AI se naye inquiry ka turant follow-up — sirf bharose pe nahi, system pe naye customers.",
        ],
        "closing": "Toh sir, pehle free Google audit karwa lein — 15 minute mein exact opportunity clear ho jaayegi, kab convenient hai?",
    },
    "gents_salon": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapke salon ki online visibility aur naye walk-in customers ke baare mein baat karni thi, abhi 2 minute denge?",
        "discovery": [
            "Abhi bookings kaise aate hain — walk-in, WhatsApp ya Google pe search karke?",
            "Google reviews kitne hain aur kab update kiye aakhri baar?",
            "Men grooming — haircut, beard, facial — konsi service sabse zyada chalti hai?",
            "Festival ya weekend pe offers karte hain ya nahi?",
        ],
        "objections": {
            "mehenga": "Sir, 2-3 extra walk-in customers per day se poora monthly fee nikal jaata hai — salon mein repeat customer hi business hai.",
            "abhi_nahi": "Koi baat nahi sir, ek free Google audit karwa lijiye — 'salon near me' searches mein aap kitne peechhe hain, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, main free audit bhej deta hoon — review score aur visibility gap clearly dikhega.",
            "pehle_se_hai": "Achha sir, compare karein — hum review collection aur booking follow-up bhi automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul sir, similar salons ke before-after results share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Before-after reels, offers aur Google reviews — 'salon near me' mein top pe aa jaate hain.",
            "WhatsApp booking + reminder — no-show zero, repeat visits zyada.",
        ],
        "closing": "Toh sir, pehle free Google audit karwa lein — exact gaps aur next steps 15 minute mein clear ho jaayenge, kab convenient hai?",
    },
    "tuition_classes": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapki tuition classes ke liye naye admission inquiries ke baare mein baat karni thi, 2 minute denge?",
        "discovery": [
            "Kis class aur subject padhate hain — 5th-10th, maths/science, ya board prep?",
            "Admissions kaise aate hain — referral se ya parents Google/Justdial pe dhoondhte hain?",
            "Kitne students hain abhi aur kitne seats khaali hain?",
            "Online classes bhi karte hain ya sirf offline?",
        ],
        "objections": {
            "mehenga": "Sir, ek extra student per month se fees cover ho jaati hai — aur seats fill hote hi value clear dikh jaati hai.",
            "abhi_nahi": "Koi baat nahi sir, tab tak ek free Google audit karwa lijiye — aapke area mein kitne parents 'tuition near me' dhoondh rahe hain, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, main free audit report bhej deta hoon — visibility aur admission inquiry flow ka gap clearly dikhega.",
            "pehle_se_hai": "Achha sir, compare karein — hum result posts aur parent review collection bhi automate karte hain, sirf advertising nahi.",
            "bharosa": "Bilkul sir, similar institutes ke admission growth results share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Result posts, parent reviews aur Google ranking — admission season mein pehle dikhte hain.",
            "AI se har admission inquiry ka turant follow-up — parents ko koi doosra institute pehle na pakad le.",
        ],
        "closing": "Toh sir, pehle free Google audit karwa lein — admission season se pehle visibility fix ho jaayegi, kab convenient hai?",
    },
    "play_school": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapke play school ke naye admission inquiries ke baare mein baat karni thi, abhi 2 minute denge?",
        "discovery": [
            "Nursery/LKG/UKG admission season kaise manage karte hain — form se ya parent visits?",
            "Aapke area mein kitne play schools hain aur aap kya alag karte hain?",
            "Google pe parents aapko kaisa dikhte hain — reviews aur photos hain?",
            "WhatsApp pe parent inquiries ka follow-up karte hain?",
        ],
        "objections": {
            "mehenga": "Sir, ek extra admission per season se poori annual fee cover ho jaati hai — parents pehle hi admission karwana chahte hain.",
            "abhi_nahi": "Koi baat nahi sir, admission season shuru hone se pehle free Google audit karwa lijiye — parents kya dhoondh rahe hain, data saamne aayega.",
            "soch_ke": "Zaroor sochiye sir, main free audit bhej deta hoon — aapka play school search mein kaisa dikhta hai, exact picture milega.",
            "pehle_se_hai": "Achha sir, compare karein — hum parent reviews aur campus photos ki visibility bhi automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul sir, similar play schools ke admission season results share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Campus photos, parent reviews aur admission offers — season se pehle visibility ready.",
            "AI se har parent inquiry ka turant follow-up — admission form kabhi thanda nahi padta.",
        ],
        "closing": "Toh sir, admission season se pehle free Google audit karwa lein — exact gaps 15 minute mein clear, kab convenient hai?",
    },
    "salon_spa": {
        "opening": "Namaste madam/sir, main [Company] se [Name] bol raha hoon — aapke area mein salon ki nayi offers aur bridal packages ke baare mein batana tha, bas 30 second?",
        "discovery": [
            "Abhi salon ki marketing kaise hoti hai — khud Instagram pe post karte hain ya koi handle karta hai?",
            "Google pe 'salon near me' search karne par aapka salon dikhta hai kya — reviews hain?",
            "Bridal ya party packages kya offer karte hain, aur kaunse season me bookings peak hoti hain?",
            "Before-after photos ya reels banate hain kya customers ke?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par ek do extra bridal bookings se poori monthly cost cover ho jaati hai — pehle free Google audit karwa lijiye, exact gap dikh jaayega.",
            "abhi_nahi": "Koi baat nahi, abhi sirf free audit karwa lein — aapka salon Google/Insta pe kaise dikhta hai, 15 minute mein clear ho jaayega.",
            "soch_ke": "Bilkul sochiye, main free audit bhej deta hoon — reviews, reels, 'salon near me' visibility, sab ka picture milega.",
            "pehle_se_hai": "Achha, phir compare karein — hum before-after reels aur review collection bhi automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar salons ke bookings growth ke real examples share kar sakte hain — aap khud decide karenge.",
        },
        "value_lines": [
            "Before-after reels aur bridal offers — Insta pe dikho to bookings khud aati hain.",
            "Google reviews collect karke 'salon near me' pe rank badhao.",
        ],
        "closing": "Toh madam/sir, free Google audit karwa lein — aapka salon online kaise dikhta hai, 15 minute mein exact picture milega, kab convenient hai?",
    },
    "gym_fitness": {
        "opening": "Namaste sir/madam, main [Company] se [Name] bol raha hoon — aapke gym ke naye membership offers ke baare mein batana tha, bas 30 second baat kar lein?",
        "discovery": [
            "Abhi naye members kaise aate hain — walk-in, referral ya koi marketing?",
            "Google pe 'gym near me' search karne par aapka gym dikhta hai kya — reviews hain?",
            "Joining offers ya seasonal plans chalate hain kya (January/Diwali rush)?",
            "Transformation photos ya workout reels banate hain kya?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par ek do extra memberships se poori cost cover ho jaati hai — pehle free audit karwa lijiye, gap dikh jaayega.",
            "abhi_nahi": "Koi baat nahi, abhi free Google audit karwa lein — aapka gym online kaise dikhta hai, 15 minute mein clear ho jaayega.",
            "soch_ke": "Zaroor sochiye, main audit bhej deta hoon — reviews, reels, 'gym near me' visibility ka poora picture milega.",
            "pehle_se_hai": "Achha, compare karein — hum transformation reels aur review collection automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar gyms ke membership growth examples share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Transformation reels aur joining offers — naye members Insta se aate hain.",
            "Google reviews se 'gym near me' pe rank badhao, walk-ins badho.",
        ],
        "closing": "Toh sir/madam, free Google audit karwa lein — aapka gym online kaise dikhta hai, 15 minute mein exact gaps clear, kab convenient hai?",
    },
    "boutique_fashion": {
        "opening": "Namaste madam, main [Company] se [Name] bol raha hoon — aapki boutique ke naye collection aur festive offers ke baare mein batana tha, bas 30 second?",
        "discovery": [
            "Abhi boutique ki marketing kaise hoti hai — khud Instagram pe post karte hain?",
            "Naye collection ke photos/reels banate hain kya, aur kaunse season me sabse zyada sale hoti hai?",
            "Google pe 'boutique near me' search karne par dikhte hain kya — reviews?",
            "WhatsApp pe regular customers ke liye offers bhejte hain kya?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par ek festive collection se hi poori cost recover ho jaati hai — pehle free audit karwa lijiye, gap dikh jaayega.",
            "abhi_nahi": "Koi baat nahi, abhi free Google audit karwa lein — aapki boutique online kaise dikhti hai, 15 minute mein clear.",
            "soch_ke": "Bilkul sochiye, main audit bhej deta hoon — Instagram visibility, reviews aur festive offers ka poora picture milega.",
            "pehle_se_hai": "Achha, compare karein — hum collection reels aur WhatsApp offers automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar boutiques ke festive sale growth examples share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "New collection reels aur festive posters — Insta pe dikho to customers aate hain.",
            "WhatsApp offers se repeat customers wapas aate hain.",
        ],
        "closing": "Toh madam, free Google audit karwa lein — aapki boutique online kaise dikhti hai, 15 minute mein exact picture milega, kab convenient hai?",
    },
    "laundry_dryclean": {
        "opening": "Namaste sir/madam, main [Company] se [Name] bol raha hoon — aapke laundry ke naye offers aur home-pickup service ke baare mein batana tha, bas 30 second?",
        "discovery": [
            "Abhi laundry ki marketing kaise hoti hai — khud Instagram pe post karte hain ya word-of-mouth?",
            "Google pe 'laundry near me' ya 'dry cleaning near me' search karne par dikhte hain kya — reviews?",
            "Home pickup/delivery service dete hain kya — society zones me?",
            "Festival season (Diwali, shaadi) me special offers chalate hain kya?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par ek do home-pickup customers se poori cost cover ho jaati hai — pehle free audit karwa lijiye, gap dikh jaayega.",
            "abhi_nahi": "Koi baat nahi, abhi free Google audit karwa lein — aapki laundry online kaise dikhti hai, 15 minute mein clear.",
            "soch_ke": "Bilkul sochiye, main audit bhej deta hoon — reviews, offers aur 'laundry near me' visibility ka poora picture milega.",
            "pehle_se_hai": "Achha, compare karein — hum home-pickup offers aur review collection automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar laundries ke customer growth examples share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Home pickup/delivery offers — societies aur office zones se orders aate hain.",
            "Google reviews se 'laundry near me' pe rank badhao.",
        ],
        "closing": "Toh sir/madam, free Google audit karwa lein — aapki laundry online kaise dikhti hai, 15 minute mein exact gaps clear, kab convenient hai?",
    },
    "electronics_repair": {
        "opening": "Namaste sir, main [Company] se [Name] bol raha hoon — aapke mobile/electronics repair ke naye offers aur doorstep service ke baare mein batana tha, bas 30 second?",
        "discovery": [
            "Abhi repair business ki marketing kaise hoti hai — khud Instagram/Google pe?",
            "Google pe 'mobile repair near me' search karne par aapka shop dikhta hai kya — reviews?",
            "Doorstep repair ya home service dete hain kya, aur warranty dete hain?",
            "Kaunse repairs sabse zyada aate hain — screen, battery, ya AC/electronics?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par ek do extra repairs se poori cost cover ho jaati hai — pehle free audit karwa lijiye, gap dikh jaayega.",
            "abhi_nahi": "Koi baat nahi, abhi free Google audit karwa lein — aapki shop online kaise dikhti hai, 15 minute mein clear.",
            "soch_ke": "Bilkul sochiye, main audit bhej deta hoon — reviews, offers aur 'mobile repair near me' visibility ka poora picture milega.",
            "pehle_se_hai": "Achha, compare karein — hum doorstep offers aur review collection automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar shops ke repair growth examples share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Doorstep repair aur warranty offers — log 'mobile repair near me' se aate hain.",
            "Google reviews se trust badhao, repair inquiries badho.",
        ],
        "closing": "Toh sir, free Google audit karwa lein — aapka repair shop online kaise dikhta hai, 15 minute mein exact gaps clear, kab convenient hai?",
    },
    "bakery_sweets": {
        "opening": "Namaste sir/madam, main [Company] se [Name] bol raha hoon — aapki bakery ke festive offers aur naye menu items ke baare mein batana tha, bas 30 second?",
        "discovery": [
            "Abhi bakery ki marketing kaise hoti hai — khud Instagram pe post karte hain ya word-of-mouth?",
            "Google pe 'bakery near me' ya 'cake shop near me' pe dikhte hain kya — reviews?",
            "Festive season (Diwali, shaadi) me sweet boxes ya custom cakes lete hain kya?",
            "WhatsApp pe orders/repeat customers kaise aate hain — manually handle karte ho?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par festive season me ek custom cake/sweet box order se invest recover ho jaata hai — pehle free audit karwa lijiye.",
            "abhi_nahi": "Koi baat nahi, abhi free Google audit karwa lein — aapki bakery online kaise dikhti hai, 15 minute mein clear.",
            "soch_ke": "Bilkul sochiye, main audit bhej deta hoon — menu, offers aur 'bakery near me' visibility ka poora picture milega.",
            "pehle_se_hai": "Achha, compare karein — hum festive offers aur WhatsApp order flow automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar bakeries ke festive-order growth examples share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Festive sweet boxes aur custom cake offers — party aur shaadi orders repeat hote hain.",
            "Google reviews se 'bakery near me' pe rank badhao.",
        ],
        "closing": "Toh sir/madam, free Google audit karwa lein — aapki bakery online kaise dikhti hai, 15 minute mein exact gaps clear, kab convenient hai?",
    },
    "jewellery_store": {
        "opening": "Namaste sir/madam, main [Company] se [Name] bol raha hoon — aapki jewellery store ke festive collection aur offers ke baare mein batana tha, bas 30 second?",
        "discovery": [
            "Abhi jewellery store ki marketing kaise hoti hai — khud Instagram pe post karte hain ya word-of-mouth?",
            "Google pe 'jewellery shop near me' pe dikhte hain kya — reviews?",
            "Wedding/festive season me special collections ya offers chalate hain kya?",
            "Gold schemes ya exchange offers chalate hain kya — repeat customers kaise aate hain?",
        ],
        "objections": {
            "mehenga": "Samajh sakta hoon, par wedding/festive season me ek do bade orders se investment recover ho jaati hai — pehle free audit karwa lijiye.",
            "abhi_nahi": "Koi baat nahi, abhi free Google audit karwa lein — aapki store online kaise dikhti hai, 15 minute mein clear.",
            "soch_ke": "Bilkul sochiye, main audit bhej deta hoon — collection, offers aur 'jewellery shop near me' visibility ka poora picture milega.",
            "pehle_se_hai": "Achha, compare karein — hum festive offers aur gold-scheme posts automate karte hain, sirf post nahi.",
            "bharosa": "Bilkul, similar stores ke festive-season growth examples share kar sakte hain — real data saamne hoga.",
        },
        "value_lines": [
            "Festive collection aur gold-scheme offers — wedding season me walk-ins double hote hain.",
            "Google reviews se trust badhao, 'jewellery shop near me' pe rank karo.",
        ],
        "closing": "Toh sir/madam, free Google audit karwa lein — aapki store online kaise dikhti hai, 15 minute mein exact gaps clear, kab convenient hai?",
    },
    # ====================================================================== #
    # GENERAL FALLBACK — baaki saare niches (modular_kitchen, hair_transplant,
    # immigration, custom niches, etc.) yahi use karte hain.
    # ====================================================================== #
    "general": {
        "opening": UNIVERSAL_AGENT_INTRO,
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
