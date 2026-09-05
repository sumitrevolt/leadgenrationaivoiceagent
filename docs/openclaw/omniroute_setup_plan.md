# OmniRoute Setup Plan: 14 Emails × 14 Combos × 42+ Free Providers

## Overview
Setup omniroute with 14 email accounts × 14 combos using 42+ free flagship AI providers. All providers offer free tiers per day/week/month. This configures all desktop apps (Hermes, Claude, WorkBuddy, Antigravity, OpenClaw) for proper network/routing with owner GUI visibility.

## Provider Summary (42 Flagship Free Models)

### Chinese Flagship Models (21 Providers)
1. SiliconFlow - DeepSeek-V4-Pro - 16K credits
2. Volcengine Ark - Doubao-Seed-2.0-Pro - 500K tokens
3. Zhipu AI - GLM-5.2 - 20M tokens
4. Meituan LongCat - LongCat-2.0 - 10M tokens
5. Alibaba Bailian - Qwen3.7-Max - 1M tokens
6. Baidu Qianfan - ERNIE-5.1 - 1M tokens
7. Tencent Cloud - Hunyuan-Hy3 - Free trial
8. MiniMax - MiniMax-M3 - Token credits
9. Kimi - Kimi-K3 - 15K credits
10. DeepSeek - DeepSeek-V4-Flash - 5M tokens
11. iFlytek Spark - Spark-X2 - Lite 1.5.1 calls/5h
12. StreamLake - KAT-Coder-Air-V2.5 - Lite 1.5.1 calls/5h
13. China Telecom - TeleChat3 - 25M tokens
14. SenseTime - SenseNova-6.7-Flash - 1500 calls/5h
15. DMXAPI - DeepSeek-V4 - $1 free
16. 01.AI - Yi-Lightning - Free credits
17. China Mobile - MoMA-300B - 25M tokens
18. DataEye - Aggregator-Flagship - 500 calls
19. Kunlun - Matrix-3.5 - Test credits
20. 360 AI - 360-AI-4.0 - Free trial
21. PPIO - DeepSeek-V4-Flash - 5K credits

### International Flagship Models (21 Providers)
22. Google AI Studio - Gemini-3.5-Flash - 1500 req/day
23. Groq - Llama-3.3-70B - 1000 req/day
24. OpenRouter - Auto-Router (free) - 50 req/day
25. Cloudflare - Llama-3.1-8B - 10K neurons/day
26. GitHub Models - GPT-4o - 50 req/day
27. NVIDIA NIM - Nemotron-3-Super-120B - 1000 credits
28. Cerebras - Llama-3.3-70B - 1M tok/day
29. Mistral - Mistral-Large-3 - 1B tokens/mo
30. Cohere - Command-R+ - 1000 req/mo
31. HuggingFace - Qwen-3.5-122B - Variable
32. Together AI - Llama-3.3-70B - $5 credits
33. LLM7.io - DeepSeek-V4-Flash - Free token
34. Ollama Cloud - Llama-3.3-70B - GPU-time based
35. AWS Bedrock - Claude-Sonnet-4 - $200 credits
36. Anyscale - Llama-3.1-405B - $100 credits
37. NCompass - Various - $100 credits
38. DigitalOcean - GenAI-Inference - $200 credits
39. Fireworks - Llama-3.3-70B - $1 credits
40. OctoAI - Various - $10 credits
41. Unify - Various - $10 credits
42. DeepInfra - Various - $1.80 credits

## Combo Role Assignment (12 Production Combos)

Each combo has 42 flagship models from 42 providers, ordered by role:

1. **leadgen-coding-primary** - Coding-focused (DeepSeek, Qwen, GLM, Llama priority)
2. **leadgen-coding-fast** - Speed-focused (Flash/Lite models first)
3. **leadgen-agent-ops** - Agentic (tool-use, reliability priority)
4. **leadgen-governor-review** - Reasoning (thinking models first)
5. **leadgen-repo-analysis** - Large context (100K+ context models)
6. **leadgen-test-generation** - Coding + instruction following
7. **leadgen-prospect-enrich** - Fast factual/research
8. **leadgen-outreach-email** - Writing + instruction following
9. **leadgen-marketing-content** - Creative + writing
10. **leadgen-seo-keyword** - Research + long context
11. **leadgen-swara-live** - Low latency conversational
12. **leadgen-free-first** - Maximum provider diversity

## Email/Combo Mapping (14 Emails × 14 Combos)

The 14 email accounts will each be configured with a subset of the 14 combos, providing redundancy and load distribution. Each email handles specific provider categories.

## Desktop App Integration

### 1. Hermes Desktop App
- Configure with FASTAPI_MCP_TOKEN (super_admin service-JWT: 1825d)
- Connect to leadgen MCP server (54 tools connected)
- Enable hotqueue/revenue-summary tools
- Set up telemetry for owner dashboard visibility

### 2. Claude Desktop App
- Configure API access via OmniRoute
- Set up routing to appropriate combo based on task type
- Enable model fallback chains

### 3. WorkBuddy Desktop App
- Integrate with omniroute provider pool
- Configure daily call caps and routing
- Set up compliance gates (DND, TRAI window)

### 4. Antigravity Desktop App
- Specialized for voice/telephony routing
- Configure Vobiz/SIP integration
- Set up call-state tracking

### 5. OpenClaw Desktop App
- Primary gateway configuration
- Memory/knowledge base integration
- Loop engineer mode orchestration

## Network & Routing Configuration

### Gateway Setup
- Gateway port: 18789 (loopback 127.0.0.1)
- Auth token: 2KB50FH46ltVD04w7XLWFjbVpA0WTvHeSuCQjuYz
- All provider connections routed through gateway
- Owner visibility via GUI with mouse tracking

### Provider Routing
- Each of 14 emails connects to specific provider groups
- Failover chains configured for each combo
- Rate limiting per provider (free tier boundaries)
- Circuit breaker configurations (60s→30min escalation)

### Compliance Gates
- DND scrub: fail-closed (lookup fail = promotional BLOCK)
- TRAI window: 9am-7pm IST calling
- DLT-approved: All cold outbound
- AI-disclosure at call start: "ek AI assistant"
- Consent ledger opt-out: instant cross-channel suppression

## Owner GUI Visibility

### Requirements
1. Owner can see mouse movements and actions in real-time
2. All config changes visible in GUI
3. Provider status shows per-email/per-combo
4. Routing decisions logged with timestamps
5. Failover events visible in real-time

### Implementation
- Use OpenClaw's built-in GUI dashboard (port 18789)
- Real-time provider health monitors
- Email/combo assignment visualization
- Routing decision logs
- Failover event summaries

## Daily Operations

### Email Rotation Schedule
- 14 emails rotating across 14 combos
- Each email handles ~3 providers per combo rotation
- Daily quota tracking per provider
- Automatic failover on 429/errors

### Monitoring
- Provider response times
- Success/failure rates per combo
- Email health status
- Owner dashboard updates

## Deployment Steps

1. **Configure 14 email accounts** in OmniRoute
2. **Assign 14 combos** to email groups
3. **Map 42 providers** to appropriate roles in each combo
4. **Set up desktop app integrations** (Hermes, Claude, WorkBuddy, Antigravity, OpenClaw)
5. **Configure gateway** with proper routing rules
6. **Enable owner GUI visibility** with real-time monitoring
7. **Test all provider connections** with free tier queries
8. **Set up compliance gates** (DND, TRAI, DLT)
9. **Deploy and verify** with owner present
10. **Train owner** on GUI usage and monitoring

## Success Criteria
- All 14 emails configured and operational
- All 14 combos functional with 42 providers each
- All 5 desktop apps (Hermes, Claude, WorkBuddy, Antigravity, OpenClaw) working
- Owner can see GUI with mouse tracking
- All compliance gates active
- No provider exceeds free tier limits
- Failover works automatically on errors

## Next Steps
1. Owner authenticates and grants access
2. Configure 14 email accounts in OmniRoute dashboard
3. Assign combos to email groups
4. Map all 42 providers with free tier assignments
5. Integrate 5 desktop apps with proper routing
6. Set up owner GUI with real-time visibility
7. Test and verify complete setup