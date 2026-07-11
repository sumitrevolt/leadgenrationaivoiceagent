# Product One — AI Video Creative Pipeline — Design Spec

- **Date:** 2026-07-10
- **Status:** Draft — user approved scope in conversation, proceeding to plan/build
- **Scope:** free-stack-only staged video-creative pipeline (5 v1 recipes) + dedicated `video` Celery queue/worker. Paid third-party video models explicitly OUT of scope.

## 0. Source

User pasted an "enterprise-grade" AI video creative pipeline spec: 11 conceptual agents (Script Writer, Storyboard, Brand, Motion Graphics, Avatar, Voice, B-roll, Caption, Music, Quality Review, Platform Optimizer), a weekly deliverable wishlist (4 premium reels, 8 branded shorts, 30 story videos, festival creatives, offer announcements, testimonial animations, Google review highlight videos, AI spokesperson videos, product showcase videos, local business promo videos) for Product One (AI Automated Marketing, ₹1,999/mo Main + ₹5,999/mo Combo). Also suggested paid video models (Runway/Luma/Pika/Kling AI/Hailuo AI/Hedra) and splitting creative labor across multiple LLMs (GLM/Kimi/Qwen/Gemini).

## 1. Inventory (code-verified, not doc-assumed)

- **Delivery today:** `product_one_delivery.py` promises, per billing-cycle-month: brand kit, 4 branded posters, 12 social posts, festival ideas, GBP suggestions, WhatsApp pack, review-reply drafts, monthly report. `packages.py` promises "AI video ads (Reels/Shorts) — har ~5 din naya video ready" — no weekly-volume or spokesperson/testimonial/product-showcase promise exists anywhere.
- **Video generation today:** `reel_video.py` (PIL colored-slide frames, word-wrapped text, brand *primary color only*, EdgeTTS `hi-IN-SwaraNeural` voiceover, ffmpeg concat → one 720×1280 MP4 template; heavy-CPU, worker-only per its own docstring). `avatar_video.py` = thin wrapper returning a Pollinations (`ai_image.video_url`, model `wan-fast`) clip URL + LLM script, gated on `POLLINATIONS_API_KEY`, not persisted server-side. `video_clips.py` cuts an *existing uploaded* video (repurposing, not generative). `gif_maker.py` = simple pulse/pop/blink text GIFs. `video_ad_cycle.py` = the real cadence engine: every `VIDEO_AD_INTERVAL_DAYS` (default 5) builds one `reel_video` MP4/active-client, routes through `content_approval`, publishes via Telegram/Postiz/WA-share on approval, with a revision loop. Invoked from `app/platform/team_scheduler.py` (not a dedicated `app/tasks/*.py` module) — i.e. it does **not** currently have its own named Celery queue; it runs as one of the scheduler's staff jobs.
- **Brand:** `brand_kit.py` persists per-client `{business_name, tagline, phone, colors, tone, logo_text}`; `brand_frames.py::resolve_brand()`/`compose_frame()` overlays logo+name+phone onto posters — proven for images, video only gets the brand *color* today (no logo overlay in video frames).
- **Reusable data sources:** `festivals.py` (Jun2026–Dec2027 calendar), `review_to_post.py`/`review_engine.py` (sentiment-gated review→quote extraction), `combo_packages.py`/offer data, `magic_resize.py` (image→4 social sizes, no video resize), `hashtags.py`.
- **Free-stack convention:** `ai_image.py` = Pollinations (flux images, wan-fast video, key-safety, disk cache, circuit-breaker). `tts.py` = EdgeTTS default (ElevenLabs/Azure optional-paid, Kokoro self-host inert fallback). No GLM/Kimi/Qwen provider is wired in `free_ai.py` today — the existing free chain is Mistral/Groq/Cerebras/Gemini/NVIDIA/SambaNova/OpenRouter; if OpenRouter's free tier happens to expose GLM/Kimi/Qwen models, `ScriptStage` can route to them as flavor, but this is an implementation-time detail, not a new provider integration.
- **Orchestration:** `app/agents/coordinator.py` has 6 existing multi-agent topologies (sequential blackboard handoff, parallel fan-out, Reflexion, hierarchical, AgentVerse, engineering-crew). New pipelines are wired as staged functions through `coordinate()`, not a new framework.
- **Celery queues today:** static `task_routes` = `{scraping, calling, reporting, sync, training}` (one `app/tasks/*.py` module each) + a dynamic `heavy` queue (flag `CELERY_HEAVY_QUEUE`, router-fn-gated) for ML/LLM/bulk staff-jobs, consumed by a dedicated `worker-heavy` service (`concurrency=1`, 2500m mem, 1.5 cpu) **only in `docker-compose.vps.yml`** — `docker-compose.prod.yml`/`docker-compose.yml` have no separate heavy worker; their single `worker` service drains `heavy` too. `tests/test_celery_queue_routing.py` enforces every compose file's worker `-Q` actually consumes every queue it's routed — a wrong/missing queue name silently orphans tasks in Redis forever (confirmed prior incident class, not hypothetical).

## 2. Scope decisions (made in conversation, not re-litigated here)

1. **Free-stack only.** Runway/Luma/Pika/Kling AI/Hailuo AI/Hedra are permanently out of scope for this pipeline — conflicts with the project's standing `CLAUDE.md` mandate ("Free stack only — koi paid AI service add nahi"). User confirmed explicitly over the alternative of parking it as a funded Phase-2.
2. **Architecture = dedicated video-worker isolation** (user's choice over the initially-recommended "extend in place" option). This means: staged pipeline (same stage decomposition either way) **plus** a genuinely separate `video` Celery queue + its own worker process — not sharing the existing `heavy` queue/`worker-heavy` (that's `concurrency=1` and explicitly starve-protected for ML/bulk jobs already; adding video there would create a new bottleneck, not remove one).
3. **"Premium/cinematic" is redefined for this stack, explicitly.** The free stack (PIL/Pollinations `wan-fast`/EdgeTTS/ffmpeg) cannot produce Runway/Kling-grade generative cinematography. What it CAN produce, and what this pipeline targets, is high-quality **motion graphics**: Ken-Burns pans/zooms over AI-generated stills, kinetic typography, animated icon/chart overlays, karaoke-style burned captions, music with auto-ducking. This line is written down so "cinematic" has one agreed meaning before anything ships.

## 3. Goals / Non-goals

**Goals**
- Every video gets the customer's brand (logo, colors, name, phone, website, rating, offer, location) applied — today only color is applied to video.
- Replace the single flat PIL-slide template with a staged, swappable pipeline where new asset types are *recipes* (config), not new code paths.
- Ship 5 v1 recipes that together cover the user's wishlist using only data sources that already exist in the codebase.
- Isolate CPU-heavy video rendering onto its own queue/worker so it can't starve (or be starved by) the rest of the platform — same problem class as 3 prior prod-downs from unbounded heavy work on shared processes.
- Every stage failure is visible and non-fatal where safe (cosmetic stages degrade gracefully); QA failures block auto-publish and route to the existing human approval gate, same as today.

**Non-goals (this spec — explicit backlog, §11)**
- Any paid video-generation API.
- True lip-synced/consistent AI spokesperson identity (v1 "spokesperson-lite" = existing `avatar_video.py` Pollinations clip, honestly labeled as lite).
- Product-showcase as a dedicated recipe (this platform's Product-One customers are local *service* businesses; architecture supports adding it once a product-based customer needs it).
- Hitting the pasted spec's literal weekly volume (4 reels + 8 shorts + 30 stories + …) — see §6.
- Multi-LLM creative division across GLM/Kimi/Qwen as named providers — `ScriptStage` uses the existing `free_ai` chain; specific model routing is an implementation detail, not a scope commitment.

## 4. Architecture — stages

New module `app/marketing/video_pipeline.py`. Each stage is a small function taking/returning a shared `CreativeBrief` dict; each stage logs one `delivery_ledger` event (§8). Orchestrated as a sequential blackboard handoff through `coordinator.py`, matching its existing topology rather than inventing one.

1. **Script** — `free_ai` LLM, niche+recipe-aware prompt → hook/story/CTA script + on-screen text cues, paced to the user's own beat structure (0–3s hook / 3–10s problem / 10–20s solution / 20–30s proof / last 5s CTA+brand).
2. **Storyboard-lite** — script → scene list: `{visual_type: kenburns_image | pollinations_clip | icon_chart_motion | logo_card, duration, on_screen_text}`. No separate storyboard image renders (cost control) — this is planning data, not pixels.
3. **Brand** — reuses `brand_frames.resolve_brand()` unchanged; makes logo+colors+name/phone/website/rating/offer/location tokens available to every downstream stage. This is the fix for video's current "color only" gap.
4. **Motion** — renders each storyboard beat: ffmpeg `zoompan` (Ken-Burns) over Pollinations `flux` stills, kinetic-typography text reveals, animated icon/chart overlays for the "solution"/"proof" beats. Replaces `reel_video`'s flat slide renderer; `reel_video.py` itself is not deleted (still callable directly for any existing caller) but stops being the terminal renderer for new pipeline output.
5. **Voice** — EdgeTTS, reusing the existing prosody-tuning pattern already proven in `voice_agent`.
6. **B-roll** — optional: one beat may use a Pollinations `wan-fast` clip instead of a Ken-Burns still. Rate-limited, and on failure/throttle falls back to the Ken-Burns path for that beat rather than failing the video.
7. **Caption** — burned, word-level-highlight captions synced to the Voice stage's audio (ffmpeg ASS subtitle burn).
8. **Music** — picks a mood/niche-tagged track from a small curated local royalty-free library (new: `data/music_beds/`), auto-ducks under voice via ffmpeg volume envelope. **Sourcing is explicitly out of this implementation's scope** — this repo/agent does not fetch or license audio. `data/music_beds/` ships empty; the stage checks for a matching file and no-ops (fail-open, §9) if none exists. Populating real CC0/royalty-free tracks (e.g. YouTube Audio Library, Pixabay Music) is a manual follow-up task, not blocking v1 — every video is correct with or without a bed.
9. **QA** — checklist: safe-margin/aspect-ratio, brand-color/logo presence, duration bounds, silence-gap check, basic grammar pass. The grammar pass is an existing-`free_ai`-LLM prompt call (reuses the Script stage's provider chain) — no new grammar-checking library or paid API. Fail → blocks auto-publish, routes to the existing `content_approval` gate (unchanged path). Pass → eligible for auto-publish same as today's `video_ad_cycle` flow.
10. **Platform-export** — extends `magic_resize`'s crop/pad pattern to video: 9:16 (Reels/Shorts/Stories), 1:1, 16:9 variants; reuses `hashtags.py` for per-platform captions.

`video_ad_cycle.py` keeps its scheduling/cadence/approval/publish role unchanged — it now calls the new pipeline's entry point instead of `reel_video.build_reel()` directly.

## 5. Recipes (v1)

The staged design makes each recipe a swap of the *script source* + *hero-visual stage*, reusing stages 3–10 unchanged:

| Recipe | Script/data source | Hero visual |
|---|---|---|
| Generic reel/short/story | Business/niche brief (today's default) | Ken-Burns + motion graphics |
| Festival creative | `festivals.py` calendar | Ken-Burns + motion graphics, festival theme |
| Review-highlight **/ testimonial** (same recipe — a testimonial *is* a review) | `review_to_post.py` / `review_engine.py` quote+rating+name | Quote-card motion graphic |
| Offer-announcement | `combo_packages.py` / offer data | Ken-Burns + motion graphics, offer-focused |
| Spokesperson-lite | Business/niche brief | `avatar_video.py`'s existing Pollinations clip (labeled "lite" in UI/report, not a true lip-synced presenter) |

Product-showcase: no dedicated recipe in v1 (see §3 non-goals) — the recipe schema supports adding one later with a product-photo input field.

## 6. Cadence

Stays **configurable, not hardcoded** to the pasted spec's weekly figures. Rationale: today's ~1 video/5 days/client already runs on a single shared VPS with ffmpeg flagged CPU-heavy in its own code; jumping straight to 40+ assets/week/customer before the new worker is load-proven is a real capacity risk, not a hypothetical one. v1 ships at the existing cadence with the upgraded pipeline + recipes; per-plan cadence (Starter vs Combo/Advanced) becomes a tunable config once real render-time/queue-depth data exists from production.

## 7. Infra — `video` Celery queue + worker

Mirrors the existing `heavy`/`worker-heavy` pattern exactly, as a 6th named queue alongside `{scraping, calling, reporting, sync, training}`:

- New `app/tasks/video_jobs.py` — Celery task `build_creative_video_task`, same shape as `app/tasks/scraping.py`/`calling.py`.
- `app/worker.py` — add `video` to the static `task_routes` dict (this is what `test_celery_queue_routing.py::test_statically_routed_queues_are_known` will need updating for).
- **`docker-compose.vps.yml`** (live deploy file): new `worker-video` service, same block shape as `worker-heavy` (`profiles: ["celery"]`, own `mem_limit`/`cpus`, `command: celery -A app.worker worker -Q video --concurrency=1`), gated by new flag `CELERY_VIDEO_QUEUE` (INERT default — unset means video tasks fall back to the default `celery` queue, i.e. today's behavior, so this ships safely before the new worker is even deployed).
- **`docker-compose.prod.yml` / `docker-compose.yml`** (no dedicated heavy worker in either): add `video` to their single `worker` service's `-Q` list, same as `heavy` is folded in there today.
- Test coverage: extend `test_celery_queue_routing.py` — `video` joins the static-routes assertion set; new `test_vps_worker_video_consumes_video_queue`; the two "plus heavy" union tests become "plus `{heavy, video}`".
- Real resource cost is small but real (one more container profile on an already-loaded VPS) — flagged here explicitly; headroom gets validated at deploy time, not blocked on here.

## 8. Data model / observability

No new database table. Reuses `app.marketing.delivery_ledger.log_event()` — new event vocabulary entries following the existing naming convention: `video_script_ready`, `video_render_started`, `video_qa_failed`, `video_qa_passed`, `video_published`. This extends the customer-visible "value timeline" the platform already has to cover video, the same way `product_one_delivery`/`delivery_ledger` already cover posters/posts. Publish path (Telegram/Postiz/WA-share) and the `content_approval` gate are unchanged — reused, not rebuilt.

## 9. Error handling

Fail-open on cosmetic stages: Music/Caption/B-roll failures log and the pipeline continues without that layer rather than failing the whole video. Fail-closed on QA: brand/margin/duration failures block auto-publish and route to human review — same policy shape this project already uses (fail-open for availability-sensitive systems, fail-closed for correctness/compliance-sensitive ones), applied here as "fail-open for enhancement layers, fail-closed for QA correctness."

## 10. Testing plan

- Unit: each stage function independently (pure input `CreativeBrief` → output), recipe config resolution, QA checklist rules, Ken-Burns/caption/ducking ffmpeg filter construction (command-string assertions, not full renders).
- Integration: one real end-to-end render at short duration/low resolution producing an actual MP4 in CI-safe time, for the generic recipe; one per remaining recipe asserting the correct script-source/hero-visual swap occurred.
- Infra: `test_celery_queue_routing.py` extensions (§7); `prod_check.py` service-name wiring check (protects against the known "wrong compose service name aborts the whole `up`" landmine).
- Regression: `test_video_ad_cycle.py` (existing) stays green — cadence/approval/publish behavior must be unchanged from the caller's point of view.

## 11. Definition of done / explicit backlog (not silently dropped)

**Done when:** 5 v1 recipes render through the staged pipeline with brand (logo+colors+contact+rating+offer+location) applied; video-rendering runs on the new `video` queue (flag-gated, safe default-fallback); QA blocks bad output from auto-publishing; existing `video_ad_cycle` cadence/approval/publish flow is unchanged from the outside; targeted pytest green; `prod_check.py` PASS; `check_secrets.py` clean; duplicate-route/queue-wiring grep clean.

**Explicit Phase-2 backlog (park here, don't rebuild-from-scratch later):**
- Paid video-model evaluation (Runway/Luma/Pika/Kling/Hailuo/Hedra) — only if/when a funded premium tier is a real business decision.
- True lip-synced/consistent-identity AI spokesperson.
- Product-showcase recipe, once a product-based (not service-based) customer exists.
- Cadence ramp beyond today's baseline, once render-time/queue-depth data from the new `video` queue exists in production.
- Multi-LLM creative-role routing (GLM/Kimi/Qwen) if/when those are confirmed reachable free (e.g. via OpenRouter) — currently unverified, not assumed.
