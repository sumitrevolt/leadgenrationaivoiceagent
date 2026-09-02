# AI Video-Ad Cycle (Marketing Product — naya feature)

**Kya:** Har ~5 din, har active marketing client ke liye AI khud **1 video ad**
banata hai → client ko **approval** ke liye jaata hai → client **approve** kare to
social media pe **auto-post**; client **"change chahiye"** bole to naya (revised)
video ban ke dobara approval jaata hai. Sab **free-stack + flag-gated (default OFF)**.

## Flow
1. **Generate** (scheduler, har 5 din/client): `video_ad_cycle.generate_for_client()`
   → `reel_video.build_reel()` (free: PIL frames + EdgeTTS voiceover + ffmpeg MP4)
   → caption (`post_generator`) → `content_approval.submit(type=video_ad)`
   → client ko WhatsApp 1-click approve/reject link (ban-safe, human-send).
2. **Approve** → `content_approval._decide` ka approve-hook → `on_approved()` →
   video "approved (publish-pending)" mark. Scheduler `publish_due()` channels pe bhejta.
3. **Change chahiye** (reject + note) → reject-hook → `on_changes_requested()` →
   "changes_requested" mark → scheduler `_regen_due()` note ke saath naya rev banata
   → fresh approval link. (max revisions: `VIDEO_AD_MAX_REVISIONS`, default 3.)
4. **Publish channels:** Telegram (free, native sendVideo) + **Postiz** (Facebook/
   Instagram/YouTube/LinkedIn — gated `POSTIZ_API_KEY`) + hamesha WhatsApp 1-click share.

## Files (sab additive, never-raise)
- **NEW** `app/marketing/video_ad_cycle.py` — orchestrator (generate/approve/publish/revise/run_cycle).
- **NEW** `app/marketing/postiz_publish.py` — Postiz public-API integration (FB/IG/YT/LinkedIn), gated.
- `app/marketing/content_approval.py` — approve-hook + reject-hook (video_ad → cycle).
- `app/platform/team_scheduler.py` — daily "content" job me `video_ad_cycle.run_cycle()`.
- `app/api/clientops.py` — admin routes: list / generate-now / request-changes.
- `app/api/automation_flags.py` — `VIDEO_AD_CYCLE` flag registered.
- **NEW** `tests/test_video_ad_cycle.py` — 8 tests (lifecycle, hooks, flag, never-raise).

## Enable kaise kare (VPS `.env`)
```
VIDEO_AD_CYCLE=1                 # master gate (default OFF = poora feature inert)
VIDEO_AD_INTERVAL_DAYS=5         # har kitne din me 1 video (default 5)
VIDEO_AD_MAX_REVISIONS=3         # max auto-revisions per change-request
VIDEO_AD_MAX_PER_RUN=10          # ek run me max videos (first-run flood guard)

# Telegram (free auto-channel): BotFather token + client record me telegram_chat_id
TELEGRAM_BOT_TOKEN=...

# Postiz (Facebook/Instagram/YouTube/LinkedIn auto-post):
POSTIZ_API_KEY=...               # Postiz settings -> API
POSTIZ_API_URL=https://api.postiz.com   # ya self-host URL
POSTIZ_INTEGRATIONS=fb_id,ig_id  # default channel ids (ya per-client `postiz_integrations`)
```
- Reel/ffmpeg/EdgeTTS pehle se stack me hain. Postiz key unset = woh channel inert (graceful).
- `build_reel` HEAVY hai → sirf scheduler/worker container me chalta (web nahi). Web sirf approval-mark.

## Admin API (require_admin)
- `GET  /api/clientops/video-ads?client_id=` — list (status: pending/approved/published/changes_requested).
- `POST /api/clientops/video-ads/generate` `{client_id}` — abhi ek video banao (background thread).
- `POST /api/clientops/video-ads/{approval_id}/request-changes` `{note}` — manual change-request.
- Customer approval = existing WhatsApp 1-click link (`/api/clientops/approve/{token}`).

## Verify (apne env me — yahan sandbox me app-deps nahi the)
```
python scripts/prod_check.py
pytest tests/test_video_ad_cycle.py -q
```
Note: logic stub-harness se 12/12 pass verified; har file AST-valid.

## TODO (optional, baad me)
- Customer portal (`/app/customer`) + admin (`/app/clients`) me video-ad approve/preview UI tab
  (abhi approval WA-link se, admin API se — UI tab add karna "complete" karega per CLAUDE.md).
- `.env.example` me upar wale keys document kar do.
