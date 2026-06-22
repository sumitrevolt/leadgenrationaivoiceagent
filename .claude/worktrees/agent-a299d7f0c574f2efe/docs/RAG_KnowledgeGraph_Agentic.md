# Knowledge-Graph RAG + Agentic RAG (2026-06-08)

Do naye RAG upgrades, dono **opt-in + defensive + free-stack** (free_ai LLM + fastembed).
Existing vector KB (`knowledge_base.py`, Qdrant) ko replace NAHI karte — uske SAATH chalte hain.

## 1) Knowledge-graph RAG — LightRAG  (`app/voice_agent/graph_rag.py`)
- **Kyun LightRAG (HKUDS)**: lightweight entity/relation graph banata hai, **incremental append** (poora rebuild nahi), aur GraphRAG se **bahut kam LLM calls** (Microsoft GraphRAG hundreds-of-calls = hamari free quota udaa deta → rejected). Graphiti ko Neo4j server chahiye (extra infra) → abhi skip.
- **Kab use karo**: jab answer relationships/causality pe depend kare — client ka pura business profile, multi-fact niche knowledge, "is cheez ka us cheez se kya link hai". Plain vector KB single-fact lookup ke liye theek hai; graph cross-fact synthesis ke liye.
- **Fit**: LLM = `free_ai.chat` (Cerebras→Groq), embeddings = wahi fastembed (`_get_qdrant_embedder`, 384-dim) jo Qdrant KB use karta — ek hi embedding space. Per-namespace graph store: `data/lightrag/<namespace>` (e.g. `client:42`, `niche:solar_residential`).
- **Enable**: `pip install lightrag-hku` + `USE_LIGHTRAG=1` + provider key. Then:
  ```python
  from app.voice_agent.graph_rag import get_graph_rag
  await get_graph_rag().ainsert(business_profile_text, namespace="client:42")
  res = await get_graph_rag().aquery("Client ka USP + target area?", namespace="client:42")  # mode: hybrid/local/global/naive
  ```
- Defensive: dep/init/query error → `{ok:False, answer:""}` → caller vector KB pe fallback kare. Never raises.
- **Note**: LightRAG insert LLM-intensive hai (entity extraction) — isliye one-time client/niche seeding pe chalao, har call pe nahi. Test web-call/text pe pehle (free).

## 2) Agentic RAG — CRAG loop  (`app/agents/agentic_rag.py`)
- **Kya**: self-correcting retrieval — `retrieve → grade relevance → (weak ho to) query rewrite + retry → grounded generate`. Plain RAG ek baar retrieve karke maan leta; yeh agent **check + correct** karta hai (production CRAG pattern).
- **Fit**: **koi naya dep nahi** — `knowledge_base.retrieve` (Qdrant/Chroma/keyword) + `free_ai.chat` (grade/rewrite/generate). Sab async, defensive.
- **Enable**: `USE_AGENTIC_RAG=1` (+ provider key — uske bina bhi best KB hit return karta hai, sirf grading/rewrite skip). Then:
  ```python
  from app.agents.agentic_rag import get_agentic_rag
  res = await get_agentic_rag().answer("solar subsidy kitni milti hai?", namespace="niche:solar_residential")
  # -> {ok, answer, grounded, used_query, rewrites, sources}
  ```
- **Wahan wire karo jahan abhi `kb.retrieve`/`grounded_answer` use hota** (telecaller_brain KB-grounding, web-call, /api/agents). Better answers on vague/misspelled queries (rewrite), kam hallucination (grade-gate).

## How they fit together
- **Agentic RAG** = retrieval ki *quality* (grade + correct) over the fast vector KB → har turn ke liye sasta + accurate. **Default upgrade candidate**.
- **LightRAG** = retrieval ki *depth* (graph) for relationship-heavy queries → heavier, targeted use (client profile / deep niche KB).
- Combo (future): agentic loop me ek "graph" branch — agar vector hits weak ho to LightRAG `aquery` pe fallback.

## Enable order (test FREE pehle)
1. `USE_AGENTIC_RAG=1` → web-call/text pe `scripts/agent_tester.py` se compare (no extra cost, no new dep). Achha lage → telecaller_brain me wire.
2. `pip install lightrag-hku` + `USE_LIGHTRAG=1` → ek client/niche seed karke `aquery` test → phir provisioning me graph-seed add.
Sab voice/answer changes: FREE web-call pe tune, phone sirf final.
