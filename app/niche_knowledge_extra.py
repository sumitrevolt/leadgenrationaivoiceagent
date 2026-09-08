"""
niche_knowledge_extra.py — DEPTH OVERLAY for per-niche KB (2026-06-14).
============================================================================
Base packs `niche_knowledge.NICHE_KNOWLEDGE` me hain. Yeh file un packs ko
EXTRA facts / benefits / objection-rebuttals se DEEP karti hai — append-only
(base ko overwrite nahi karti). niche_knowledge.py end me ise merge karta hai
(facts/benefits append + dedupe, objections update).

Naya niche enrich karna ho to yahan uska entry add karo — base pack waise hi
kaam karta rahega. Objection keys canonical hain (no_time/send_details/
just_browsing/busy/already_have/think_about_it/too_expensive/not_interested)
jo niche_knowledge ke synonym-resolver se resolve hote hain.

Frame: end-customer-facing niches (patient/student/investor ki bhasha) — factual,
warm, non-pushy; variable specifics pe "team exact detail confirm karwa degi".
"""

from __future__ import annotations

from typing import Any

EXTRA: dict[str, dict[str, Any]] = {
    "ayurveda_wellness": {
        "facts": [
            "Pehli consultation me aapki problem, history aur prakriti samajhte hain — phir hi treatment plan banta hai, ready-made nahi.",
            "Ayurveda dheere par jad se kaam karta hai — realistic timeline pehle batate hain, jhoothe '7 din me theek' waade nahi.",
            "Therapy ke saath diet aur lifestyle guidance bhi milti hai — sirf dawai nahi.",
            "Allopathy chal rahi ho to band karne ko nahi kehte — safe coordinate karte hain.",
        ],
        "benefits": [
            "Root-cause pe kaam — sirf symptom dabाना nahi",
            "Natural, side-effect kam — long-term wellness",
        ],
        "objections": {
            "no_time": "Pehli baar sirf 20-30 min ki consultation hai; baaki therapies aapke schedule ke hisab se plan ho jaati hain.",
            "think_about_it": "Bilkul sochiye — main ek consultation slot bhej deti hoon, doctor se baat karke aaram se decide karna.",
            "already_have": "Achhi baat — ek baar second opinion le lijiye, ho sakta aapke case me ayurveda complement kare. Koi pressure nahi.",
        },
    },
    "skin_dermatology": {
        "facts": [
            "Skin/hair issue ki exact wajah (hormonal, fungal, allergy) diagnose karke hi treatment dete hain — guesswork nahi.",
            "Results skin-type aur condition pe depend karte hain; realistic expectation aur sessions ka rough idea pehle batate hain.",
            "Procedures (laser/peel) certified dermatologist ki supervision me hote hain — safety pehle.",
        ],
        "benefits": [
            "Sahi diagnosis = sahi ilaaj, paisa waste nahi",
            "Expert supervision — safe procedures",
        ],
        "objections": {
            "too_expensive": "Treatment aksar package/EMI me hota hai, aur consultation me hi realistic cost + sessions bata dete hain — koi hidden charge nahi.",
            "think_about_it": "Koi jaldi nahi — pehle ek consultation me apni skin ki sahi wajah jaan lijiye, phir decide karna.",
            "not_interested": "Bilkul theek hai. Bas itna — kabhi skin/hair issue badhe to ek baar sahi diagnosis zaroor karwa lena.",
        },
    },
    "edtech_creators": {
        "facts": [
            "Placement/career support ya portfolio guidance bhi milti hai — sirf padhai nahi, aage ka raasta bhi.",
            "Live doubt sessions + recorded dono — class miss ho to phir dekh sakte ho.",
            "Content industry-updated rehta hai (jo skills/tools abhi job-market me chahiye).",
        ],
        "benefits": [
            "Seekhne ke saath career-outcome pe focus",
        ],
        "objections": {
            "send_details": "Zaroor — syllabus + free demo ka link WhatsApp pe bhej deti hoon. Pehle demo dekh lena, content khud bol dega.",
            "already_have": "Achha — ek baar humara free demo compare kar lijiye; practical projects/placement support behtar lag sakta. Koi commitment nahi.",
        },
    },
    "finance_advisory": {
        "facts": [
            "Advice qualified/registered advisors ke through hi — random tips nahi.",
            "Aapka paisa aapke hi demat/folio me rehta hai — hum kabhi apne account me nahi lete.",
            "Review periodic hota hai — market ya life-change pe plan adjust kar dete hain.",
        ],
        "benefits": [
            "Transparent, conflict-free advice — sirf product-selling nahi",
        ],
        "objections": {
            "send_details": "Zaroor bhejti hoon — par 2 min me aapke goal samajh loon to detail relevant hogi, generic nahi.",
            "just_browsing": "Bilkul, abhi samajh rahe hain — ek simple goal-snapshot bhej deti hoon, jab man kare aage badhna.",
            "not_interested": "Koi baat nahi. Bas itna — jaldi shuru ki chhoti SIP bhi compounding se badi banti hai; jab ready ho, yaad rakhna.",
        },
    },
    "hospital_appointments": {
        "facts": [
            "Urgent case ho to priority slot/guidance dete hain — aap bas batayein.",
            "Insurance/cashless ya estimate ki jaankari pehle clear kar dete hain taaki surprise na ho.",
            "Multi-department case me coordinate karke ek hi visit me zyada kaam karwa dete hain.",
        ],
        "benefits": [
            "Confusion-free — sahi doctor, sahi time, clear cost",
        ],
        "objections": {
            "send_details": "Zaroor — available doctors + timings WhatsApp pe bhej deti hoon. Aap symptom bata dijiye taaki sahi department suggest karoon.",
            "busy": "Samajhti hoon. Preferred din-time bata dijiye, main slot fix karke confirm bhej deti hoon.",
        },
    },
}
