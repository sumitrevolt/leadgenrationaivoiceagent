# AI-Automation + Automated-Marketing repos (2026-06-08)

Teen naye free/CPU open-source helpers — sab **defensive + opt-in** (dep missing → safe
fallback, never crash). Koi env flag nahi; lib present + key present ho to chalte hain.

## AI automation — Instructor  (`app/llm/structured.py`)
- **Kya**: LLM se **typed + validated JSON** (Pydantic model) — auto-retry jab tak validate na ho. "Structured output = 2026 ka default."
- **Kyun**: abhi marketing/automation code LLM se JSON maangta + haath se parse karta → free model prose add kare ya field chhode to tootta. Instructor pin karta. Cerebras/Groq pe **JSON mode** se chalta (free_ai providers).
- **Use**:
  ```python
  from pydantic import BaseModel
  from app.llm.structured import extract
  class Post(BaseModel):
      caption: str; hashtags: list[str]
  p = extract(Post, system="Marketing writer", user="Diwali offer post for a salon")
  if p is None:  # dep/key missing -> existing template fallback
      ...
  ```
- **Wahan wire karo**: `post_generator`, `ads_copy`, `lead_scoring`, `competitor`, agentic_rag grading — jahan bhi LLM-JSON parse hota.

## Automated marketing — advertools  (`app/marketing/seo_tools.py`)
- **Kya**: SEO/SEM toolkit. `generate_keywords(products, modifiers)` → SEM keyword combos; `split_ad(text, slots)` → RSA-sized headlines/descriptions.
- **Kyun**: `ads_copy` / `seo_blog` / `gbp_text` ko programmatic keyword + ad-slot generation milta. pandas-based (already dep).
- **Use**:
  ```python
  from app.marketing import seo_tools
  kws = seo_tools.generate_keywords(["solar panels","solar installation"], ["price","subsidy","near me"])
  slots = seo_tools.split_ad("Best solar panels in Pune, 25-yr warranty, free site visit", (30,30,30,90,90))
  ```

## Prospect/competitor data — trafilatura  (`app/lead_scraper/web_extract.py`)
- **Kya**: highest-accuracy web main-text extractor + contact finder. `clean_text(html)` → asli about/services text; `find_contacts(html)` → emails + Indian phones.
- **Kyun**: prospector ka crude `_extract_email_from_website` upgrade — behtar email/phone + saaf business text (competitor analysis + LightRAG ko feed karne layak). benchmarks me readability/boilerpipe se aage.
- **Use**:
  ```python
  from app.lead_scraper import web_extract
  text = web_extract.clean_text(html)
  info = web_extract.find_contacts(html)   # {"emails":[...], "phones":[...]}
  ```
- **Wahan wire karo**: `prospector` (email/phone capture), `competitor` (clean competitor text), optional graph/agentic RAG ingestion.

## Notes
- Sab opt-in: VPS pe install ho gaye (verify ke saath), par koi existing code abhi inhe import nahi karta → zero runtime change jab tak wire na karo.
- Test FREE: web-call/text + `agent_tester.py` pe pehle, phone sirf final.
- Combo idea: `structured.extract` + agentic_rag → typed, grounded marketing content; `web_extract` + LightRAG → client website se knowledge-graph auto-seed.
