---
type: Architecture
title: OmniRoute
description: Local-dev LLM gateway adapter — INERT on VPS unless flags ON.
tags: [omniroute, llm, free-stack]
timestamp: 2026-07-17T00:00:00Z
resource: app/platform/omniroute_client.py
---

# OmniRoute

- Local WSL gateway only by default; VPS flags OFF.
- Routes use free combo / auto-aliases (`leadgen-free-first` + fallbacks) — free-tokens mandate.
- **2026-08-16: `leadgen-project-best` = flagship-free 16-step chain (rebuild; old DeepSeek-only chain backed up at `/root/.omniroute/backup-combo-leadgen-project-best-before-flagship.json`)** — order: Antigravity Claude Opus 4.6 ×2 → Gemini 3.1 Pro ×2 (Antigravity/AGY) → Codex GPT-5.5 → Kiro Claude Haiku 4.5 → NVIDIA GLM-5.2 → Kiro GLM-5 → Gemini 3.1 Pro/3.5 Flash (direct) → gpt-oss-120b (Cerebras/Groq) → Mistral Large/Code → Groq Llama → Gemini Flash tail. Every step smoke-verified 200 on 2026-08-16 as local gateway/free-token aliases only; this is documentation of local OmniRoute routing, not a production paid-provider authorization. DSH (`C:\Users\Ratanshila\.dsh\settings.yaml`) binds this name — no config change needed.
- Dead/excluded until user action: GitHub Models (`gh/*`, quota exhausted ~15.6d), Vercel AI Gateway (`vcg/*`, needs credit card on file), cline/kimi-coding/openrouter/hfr (creds expired/exhausted), nvidia/deepseek-v4-pro (410 removed from NVIDIA roster), gemini/gemini-3-pro-preview (404 removed).
- Combo management = `POST /api/combos` (create), `DELETE /api/combos/{uuid}` (delete; CLI delete auth-broken), `GET /api/combos` — all with Manage API key (`Authorization: Bearer ${OMNIROUTE_MANAGE_API_KEY}`, stored in `api_keys` table).
- Provider label for combo IDs = `combo` (or resolved `provider/model`), not a fake provider name.
- **2026-08-23: bare-OpenAI-model landmine** — gateway pe koi `codex` provider connection NAHI hai (0/40); koi bhi bare OpenAI model-id (`gpt-5.6-sol`, `gpt-5.3-codex`) `/v1/responses` pe built-in `codex` provider pe resolve hokar `404 "No active credentials for provider: codex"` deta hai. Combo ids (`leadgen-project-best`) = 200. ChatGPT/Codex desktop app (`~/.codex/config.toml`, `[desktop]` section shared) ka top-level `model` isi wajah se `leadgen-project-best` pin kiya gaya — desktop restart zaroori hai config reload ke liye; codex exec end-to-end verified (CODEX_OMNI_OK, session 01a02dee).
- Fail-open: gateway miss → existing `free_ai` chain continues.
- Never send raw customer PII — `mask_customer_data` + `validate_no_secrets` before network.
