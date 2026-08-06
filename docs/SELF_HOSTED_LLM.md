# Self-Hosted LLM Stack (own model — kisi tier pe nirbhar nahi)

**Maqsad:** apna LLM (Ollama) — UNLIMITED, no quota, no 429, no per-call cost. Free
cloud providers (groq TPD, gemini quota) exhaust hone par bhi project KABHI LLM-down
nahi. `free_ai.chat` me first-class provider ("ollama") — `OLLAMA_URL` set hote hi active.

## Architecture
```
free_ai.chat chain:
  [OLLAMA_PRIMARY=1] -> ollama (own GPU)        # pure self-reliance, fast
  mistral -> groq -> cerebras                   # fast cloud (jab up)
  -> ollama (own LLM)                           # reliable floor (cloud exhaust pe guaranteed)
  -> gemini/sambanova/openrouter                # flaky cloud last
```
- `OLLAMA_URL` unset = ollama provider inert (zero change, pure cloud).
- Provider OpenAI-compatible (`/v1`) — Ollama, vLLM, llama.cpp sab chalega.

## Option A — User PC GPU (RTX 3050 4GB) via tunnel  ⭐ recommended for fast/free
Best speed (GPU), zero cost. PC on = fast GPU LLM primary; PC off = cloud fallback (graceful).

**1. Ollama install (Windows, one-time):**
`winget install Ollama.Ollama`  (GPU auto-detect — RTX 3050 use hoga)

**2. Model pull (Hinglish-strong, fits 4GB VRAM):**
`ollama pull qwen2.5:3b-instruct`   (~2.3GB Q4; alt: `llama3.2:3b`)
Ollama Windows pe service ki tarah chalti hai → `http://localhost:11434`.

**3. VPS tak expose (secure tunnel, no port-forward):**
`winget install Cloudflare.cloudflared` phir:
`cloudflared tunnel --url http://localhost:11434`
→ ek public `https://<random>.trycloudflare.com` URL milega (free, no account).
(Stable URL ke liye: Cloudflare named tunnel ya `ngrok http 11434`.)

**4. VPS wire:**
`/opt/leadgen/.env` me:
```
OLLAMA_URL=https://<your-tunnel>.trycloudflare.com/v1
OLLAMA_MODEL=qwen2.5:3b-instruct
OLLAMA_PRIMARY=1          # own GPU LLM sabse pehle
OLLAMA_TIMEOUT_S=30
```
phir app recreate. Bas — ab project tumhari GPU se LLM chalata hai.

⚠️ **Note:** laptop on + tunnel running rehna chahiye. Sleep/off pe ollama-provider down → cloud fallback (graceful, no crash). 24×7 production ke liye: dedicated GPU box ya `deploy/compose/docker-compose.ollama.yml` (Option B) ya cloud GPU.

## Option B — VPS self-host (CPU-only, 4 core / 10GB)  — always-on, slower
`deploy/compose/docker-compose.ollama.yml` (CPU-limited Ollama container, same network):
```
docker compose -f deploy/compose/docker-compose.ollama.yml up -d
docker exec leadgen_ollama ollama pull qwen2.5:3b-instruct
```
`.env`: `OLLAMA_URL=http://ollama:11434/v1` (in-network). CPU inference ~3-6s/short reply
(content ke liye theek; voice ke liye marginal — isliye PRIMARY mat karo, fallback rakho).

## Verify
`curl $OLLAMA_URL/models` (models list) · `/api/growth/infra/llm` (live provider stats —
ollama ok-rate dikhega) · agent_tester (voice latency).

## Why this = "100% best system" (billionaire + automation-engineer)
- **Independence moat:** apna LLM = koi tier kabhi block nahi kar sakta.
- **Cost = 0** per call (sirf apna compute) → margins compound.
- **Hybrid:** fast cloud jab up + own-GPU guaranteed floor = best uptime + speed.
- **Data stays yours:** sensitive prompts apne hardware pe (privacy/DPDP edge).
