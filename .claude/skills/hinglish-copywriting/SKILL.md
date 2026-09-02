---
name: hinglish-copywriting
description: Hinglish copy frameworks (AIDA/PAS/4U) + marketing psychology (loss aversion, social proof, anchoring, honest urgency) for own funnel (/pricing /demo /audit landing) AUR product prompt-templates (post_generator, proposal.py, sales_assistant.py — 39 builtin niches ka client-facing copy). Use jab "copy likho", "headline", "caption framework", "convincing banao", "psychology lagao", "copy weak hai" bole.
---

# Hinglish Copywriting + Psychology

Do jagah lagti hai: (1) **apna funnel** — landing/`pricing.html`/`audit`/`demo` copy; (2) **product prompts** — `app/marketing/post_generator.py`, `proposal.py`, `sales_assistant.py` jo 39 builtin niches (`app/niches.py` `content_focus`) ke liye client-facing copy banate. Framework wahi, audience alag.

## Frameworks (Hinglish idiom me)
- **AIDA**: Attention ("Bijli ka bill ₹0?") → Interest (specific fayda) → Desire (proof/social) → Action (1 CTA). Posts/landing ka default.
- **PAS**: Problem ("Customer call karta hai, aap miss kar dete ho") → Agitate ("woh seedha competitor ko call karta hai") → Solve ("AI 2-min me callback karta hai"). Cold/proposal ka default — Indian SMB pain-first sunta hai.
- **4U headlines**: Useful + Urgent + Unique + Ultra-specific. "Marketing improve karein" ❌ → "7 din me Google se pehli inquiry — ₹0 trial, phir ₹1,999/mo" ✓.
- **Style**: chhote sentences, active voice, numbers specific ("4 ghante → 15 min"), customer ki bhasha (jo woh WhatsApp pe bolta hai), ek section = ek idea, exclamation marks hatao.

## Psychology principles (ethically, India-tuned)
- **Loss aversion**: "Roz ke 5 missed calls = mahine ke ~₹15,000 ka dhandha gaya" (lead_tools calculator se REAL number) > "zyada kamao".
- **Social proof**: review stars, "X businesses", client testimonial Hinglish me — Indian SMB pehle bharosa, baad me payment. Proof fabricate KABHI nahi.
- **Anchoring**: "Human telecaller ₹10,000+/mahina — AI marketing ₹1,999 se" (voice product: "AI telecaller ₹4,999/mo, unlimited calls") · Combo/Advanced (₹5,999) highlighted (public = 2-tier; Growth ₹2,999 legacy-hidden).
- **Mental accounting**: "₹33/din — ek chai se kam". **Reciprocity**: free audit/demo pehle do, phir maango.
- **Risk-reversal**: "₹0 me 7 din try karo, cancel anytime" — regret-fear khatam.

## Do / Don't
| ✅ Karo | ❌ Mat karo |
|---|---|
| Festival/season-tie urgency ("Diwali se pehle profile ready") | Fake countdown / "sirf 2 seats bachi" jhooth |
| Real numbers (reviews, ₹, din) | "Best", "No.1", banawati stats |
| "Pehla result 7 din me" (deliverable promise) | "Guaranteed 10x leads" / "bundle dono ek saath" |
| Hinglish jaise bolte hain ("dhanda", "jhanjhat khatam") | Shuddh-Hindi ya corporate English jargon |
| 1 CTA per piece | 3 buttons, decision paralysis |
| Scarcity sirf genuine ho tab | Har post me "HURRY!!" |

## Prompt-template upgrade pattern
post_generator/proposal/sales_assistant prompts me framework NAAM se instruct karo ("PAS structure, ≤2 sentences/section, ek CTA, koi fake urgency nahi") + niche `content_focus` + honest-urgency rule inject. Change ke baad: `pytest tests/ -k "marketing_upgrades or competitor"` + 2-3 niches pe sample generate karke padho — bolne layak lage tabhi ship.

Adapted from coreyhaines31/marketingskills (copywriting + marketing-psychology, via VoltAgent/awesome-agent-skills)
