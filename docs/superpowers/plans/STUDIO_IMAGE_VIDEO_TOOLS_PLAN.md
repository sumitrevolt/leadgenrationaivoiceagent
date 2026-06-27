# Plan — Customer Studio image/video tools (upload-based)

Status: PLAN (not built). Prereq for the last unwired free modules in the AI
Marketing Studio (currently 83 text/SVG tools live). See memory
`customer-ai-marketing-studio`.

## Why these are deferred
The 83 live Studio tools are text/SVG (no input file). The remaining free modules
need the CUSTOMER to upload an image/video, then we process and return it:
`magic_resize`, `gif_maker`, `bg_remove`, `sticker_pack`, `avatar_video`,
`reel_video`, `video_clips`, `jingle` (audio). The blocker is **upload + temp
storage + serve-back**, not the libraries.

## What already exists (grounded)
- `pillow==12.2.0` (PIL) — baked ✓ → magic_resize, gif_maker, sticker_pack work NOW.
- `av==17.1.0` (PyAV/ffmpeg) + `numpy` — baked ✓ → video tools have their codec layer.
- `edge-tts` — baked ✓ → jingle audio.
- MinIO/disk storage layer: `app/storage/minio_client.py` (`get_storage`, local-disk fallback) — EXISTS.
- `app/marketing/ai_image.py` already does disk-cache under `data/ai_images/` + a proxy endpoint pattern.
- MISSING dep: `rembg` (background removal model, ~heavy) — only bg_remove needs it; add to requirements or skip bg_remove in phase 1.

## The only real new piece: a safe upload→process→serve path
1. **Upload endpoint** `POST /api/customer/studio/upload` (require_customer, rate-limited):
   - Accept `multipart/form-data` single file.
   - VALIDATE: content-type allowlist (png/jpg/webp/mp4), magic-byte sniff (not just extension), max size (e.g. 8 MB image / 40 MB video), reject SVG-with-script.
   - Store under `data/studio_uploads/<client_id>/<uuid>.<ext>` (client-scoped dir; gitignored) via `get_storage`.
   - Return an opaque `upload_id` (not a path). NO direct path traversal.
2. **Process endpoints** take `upload_id` (not a path), resolve to the client's own file (IDOR check: client_id must own the upload_id), run the module in `asyncio.to_thread` with a hard deadline (heavy PIL/av off the event loop — project RULE), write output to `data/studio_outputs/<client_id>/`, return an `output_id`.
3. **Serve endpoint** `GET /api/customer/studio/file/{output_id}` (require_customer + ownership check) streams the result with correct content-type + `Content-Disposition: attachment`.
4. **TTL cleanup**: a small scheduled job purges `studio_uploads`/`studio_outputs` older than 24-48h (disk hygiene; reuse team_scheduler hygiene slot).

## Security checklist (MANDATORY — public-ish surface + payments platform)
- [ ] Magic-byte content sniff + extension allowlist (no `.svg`/`.html`/`.php`).
- [ ] Size caps + request timeout; reject zip-bombs / decompression bombs (PIL `Image.MAX_IMAGE_PIXELS`).
- [ ] Per-client storage namespace + ownership check on every read (IDOR).
- [ ] Strip EXIF/GPS from output images (privacy).
- [ ] Rate-limit uploads (e.g. 20/min/IP via existing `rate_limit`).
- [ ] Run heavy libs in `to_thread` + deadline + graceful failure (NEVER block event loop — 3 prod-downs lesson).
- [ ] `rembg` (if added) loaded off-loop + disable-switch flag; image-bake the model (model-asset-bake rule).

## Tool list (phase 1 = PIL-only, no new deps)
1. **magic-resize** — 1 image → IG square / story / FB / WhatsApp DP sizes (PIL).
2. **gif-maker** — text/frames → GIF (PIL).
3. **sticker-pack** — image → WhatsApp sticker set (PIL, 512×512 webp).
Phase 2 (heavier): bg-remove (needs `rembg`), reel-video / video-clips / avatar-video (av/ffmpeg, slow → background job + notify), jingle (edge-tts audio).

## Phasing & effort
- **Phase 0 (infra):** upload + serve + ownership + cleanup + security tests. ~M effort. THIS is the gate.
- **Phase 1:** wire magic-resize, gif-maker, sticker-pack (PIL, fast, sync-in-thread). ~S each once infra exists.
- **Phase 2:** add rembg + video/audio (async/background, slower UX, more testing). ~M-L.

## Recommendation
Do Phase 0 + Phase 1 first (3 image tools, no new deps, fast UX). Defer Phase 2
(video/bg-remove) until there's demand — video is slow + storage-heavy and most
local-SMB value is in the image tools. UI: same `STUDIO_TOOLS` config pattern, but
these tools get a file-input + a 2-step (upload → process) flow instead of the
text-form flow.
