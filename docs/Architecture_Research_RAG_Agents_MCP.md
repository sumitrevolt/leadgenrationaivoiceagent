# Architecture Research — Per-Niche RAG, Multi-Agent, MCP Stack (June 2026)

Deep research (3 parallel streams, 35+ sources). Goal: har niche ka ALAG RAG,
har niche ke ALAG specialized agents, aur yeh sab orchestrate karne ke liye
best open-source repos + MCP servers + Claude skills.

---

## 1. "Graph wala" repo — LangGraph (orchestration ka winner)

**[langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)** — ~126k stars,
MIT, v1.0 stable (late-2025). Abhi ka de-facto standard for stateful multi-agent.

- Early 2026 me CrewAI ko overtake kiya; Klarna/Replit/Elastic production me use karte hain
- **Supervisor pattern** (prebuilt `langgraph-supervisor`): ek routing node niche/role ke
  hisab se sahi agent ko kaam deta hai — debuggable, hamare data-agent + leads-agent
  model pe perfect fit
- **Per-agent state + persistence**: `langgraph-checkpoint-sqlite` (dev) /
  `langgraph-checkpoint-postgres` (prod); `thread_id` = call/session — har call ka apna state
- **Gemini officially supported** (`langchain-google-genai`, Google ki apni docs me example)
- FastAPI integration pattern established (lifespan me checkpointer, graph `app.state` me)

**Verdict: adopt karo (Phase 2).** Hamara `agent_provisioner` jo 2 agents banata hai,
unko LangGraph supervisor ke nodes bana do — data-agent KB seed/enrichment node,
leads-agent calling/qualification node, supervisor niche ke hisab se route kare.

## 2. GraphRAG vs LightRAG vs simple vector — hamare KBs ke liye

| Repo | Stars | Indexing cost (500-pg corpus) | Hamare liye |
|---|---|---|---|
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | ~31.6k | $50–200, ~45 min | **OVERKILL — skip** |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | ~30k | ~$0.50, 3 min (1/100th cost, 70-90% quality) | Future — jab clients bade docs upload karein |
| Simple vector + keyword hybrid (current) | — | ~free | **Abhi ke liye sahi** |

Hamari niche KBs chhoti hain (~8 chunks/niche: facts, objections, pricing).
Graph-RAG ka payoff multi-hop reasoning across LARGE corpora me hai. Verdict:
**abhi simple vector+keyword, LightRAG tab jab client-docs bade hon, microsoft/graphrag kabhi nahi.**

## 3. Per-niche RAG architecture (multiple RAGs, isolated)

**Vector DB winner: [Qdrant](https://github.com/qdrant/qdrant)** — single Docker container,
<300MB RAM at our scale, p99 30-40ms (vs Chroma 100-200ms), official multitenancy guide.

**Critical design decision (Qdrant ki official guidance):** collection-per-niche MAT
karo — **EK collection `kb_main` + payload partitioning**:

```
point payload = { niche: "solar_residential", client_id: "c123"|null,
                  doc_type: "facts"|"objections"|"pricing", lang: "hinglish" }
```

- `niche` + `client_id` pe keyword index → har niche/client ka logically alag RAG
- 25 → 1000 niches = sirf naye payload values, **zero migration** (custom niches free me wire)
- **Fallback chain (deterministic):** client docs → niche docs → `general` → keyword index → static flow text (score < ~0.45 pe next tier)
- Implementation: `knowledge_base.py` me thin `QdrantIndex` (~80 lines), framework NAHI
  (LlamaIndex/LangChain retrieval yahan overhead — voice latency budget tight hai)
- **Routing:** 90% deterministic hai (agent ko provision-time pe niche pata hai);
  intra-niche intent routing (facts vs objection vs pricing) ke liye
  [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router) — no LLM call, local encoder

**Embeddings (Hinglish):** `intfloat/multilingual-e5-small` (118M, ONNX int8 ~150MB,
CPU-fast, Hindi covered; `query:`/`passage:` prefixes zaroori). bge-m3 quality-best lekin
1GB+ — VPS pe tight. Gemini embedding free tier (100 RPM/1000 RPD) sirf batch-ingest ke
liye, query-time pe nahi (quota project-wide — humne flash quota issue dekha hai).

## 4. Voice layer (jab live calling aaye)

- **[pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)** (~12k stars, BSD-2, v1.0):
  native Twilio Media Streams + FastAPI WebSocket transport, BYOK STT/TTS — hamare stack ka perfect fit
- **Pipecat + LangGraph combo proven** (Jan 2026 production writeups: Twilio+Pipecat+LangGraph)
- [livekit/agents](https://github.com/livekit/agents) — heavier self-host; [dograh-hq/dograh](https://github.com/dograh-hq/dograh) — architecture reference (FastAPI+Pipecat+MCP)

## 5. MCP servers — adopt-first top 5

| # | Server | Kaam |
|---|---|---|
| 1 | [tadata-org/fastapi_mcp](https://github.com/tadata-org/fastapi_mcp) | `FastApiMCP(app).mount()` → hamare admin endpoints (create_client, add_niche, provision-agents) **auto MCP tools** — Claude platform-admin ban jata hai, existing auth ke saath |
| 2 | [github/github-mcp-server](https://github.com/github/github-mcp-server) | Repo automation: issue→fix→PR→merge loop |
| 3 | [bytebase/dbhub](https://github.com/bytebase/dbhub) | SQLite **aur** Postgres dono — VPS prod DB inspect bina ssh ke |
| 4 | [@modelcontextprotocol/server-memory](https://www.npmjs.com/package/@modelcontextprotocol/server-memory) | Knowledge-graph memory — CLAUDE.md ka structured upgrade (entities/relations) |
| 5 | [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters) | Hamare LangGraph agents MCP tools consume karein (Sheets/HubSpot/GitHub as agent tools) |

Honorable: [qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) +
[chroma-core/chroma-mcp](https://github.com/chroma-core/chroma-mcp) (KB debug/ops ke liye;
**runtime call-path me MCP-hop latency mat lo** — in-process RAG rakho). Google Sheets:
`xing5/mcp-google-sheets`. HubSpot official remote MCP (GA Apr 2026). WhatsApp MCP
(`lharries/whatsapp-mcp`) sirf dev/demo — prod me Meta Cloud API hi.

## 6. Claude skills

- [anthropics/skills](https://github.com/anthropics/skills) + Skills Marketplace (~600 skills)
- Hamara pattern already sahi hai (`.claude/skills/hostinger-deploy/SKILL.md`) — extend karo:
  - **`leadgen-ops`**: prod_check→pytest→push→VPS pull+restart + journalctl triage codified
  - **`niche-onboarding`**: add niche→KB seed→web-call verify e2e

## 7. Skip list (research-backed)

CrewAI (production me log LangGraph migrate karte), AutoGen (maintenance mode Q1-2026),
Google ADK (Vertex cloud-gravity), microsoft/graphrag (overkill+costly), Weaviate/Milvus
(VPS pe heavy), LlamaIndex/LangChain-retrieval (voice latency overhead).
Plan-B orchestrator: OpenAI Agents SDK + LiteLLM (Gemini chalega).

## 8. Adoption roadmap

1. **Phase 1 (high-leverage, low-risk):** Qdrant Docker + `QdrantIndex` payload-partitioned
   RAG + e5-small ONNX embeddings; `fastapi_mcp` mount → Claude se platform manage
2. **Phase 2:** LangGraph supervisor — data/leads agents ko graph nodes banao,
   SQLite checkpointer; niche-wise prompts/RAG/flows already ready hain
3. **Phase 3 (telephony ke saath):** Pipecat + Twilio Media Streams + LangGraph frame-processor
4. **Phase 4 (jab client-docs bade hon):** LightRAG sirf un clients ke liye

---
*Research: 3 parallel agents, 35+ web searches; adversarial spot-checks on key claims.
Sab repos free/open-source, self-hosted VPS (4-8GB) compatible, Gemini-compatible.*
