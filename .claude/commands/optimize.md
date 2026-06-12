---
description: Changed code ka async-safety + performance scan — event-loop blocking (humara #1 prod-down cause) pakdo.
---
# /optimize — async-safety + perf scan (LeadGen AI tailored)

Generic perf review NAHI — is project ke 3 prod-downs ka root cause EK hi class tha: **sync ML/IO event-loop pe** (qa-job boot ML, widget-chat sync kb.retrieve, embedder sync HF download). Yeh command wahi class systematically pakadta hai. Detail: skills `model-asset-bake`, `integration-engineering`.

## Steps
1. **Scope**: changed files (`git diff --name-only HEAD`) ya `$ARGUMENTS` me diya module.
2. **Danger-pattern grep** (async def / WS handler / route ke andar):
   - `kb.retrieve|KnowledgeBase|TextEmbedding|fastembed|torch|silero|from_pretrained` — sync ML load/call? → `asyncio.to_thread` + deadline (`wait_for`) + disable-switch zaroori.
   - `requests\.|httpx\.(get|post)\(` bina `await`/AsyncClient — sync HTTP on loop.
   - `time\.sleep\(` async function me → `asyncio.sleep`.
   - `open(.*\.(jsonl|json)\).*read|readlines` bade stores pe hot path me.
   - LLM/`free_ai` call bina `asyncio.wait_for` timeout ke (public endpoints = 25s max pattern).
3. **Checklist (har finding pe)**: thread-offload? hard deadline? fail-open/disable flag? model/asset image-baked? scheduler me ungated heavy job to nahi?
4. **Classic perf bhi dekho**: O(n²) loops over prospects/leads stores, repeat computation jo cache ho sakta (1hr cache pattern: weather_angle), N+1 DB queries.
5. **Output**: severity table (Critical = loop-block in public/WS path · High = scheduler heavy ungated · Medium = cacheable · Low = style) + exact fix snippet. Critical pe ship MAT karo.

**RULE yaad rakho**: public endpoint me KB/ML = thread + hard timeout. Har ML asset = image-bake + off-loop load + deadline + disable-switch.

`$ARGUMENTS`: optional file/module scope.

*Adapted from luongnv89/claude-howto (MIT) — project prod-down lessons pe re-written.*
