# VIDEO_PRODUCTION_LICENSES — free/open stack only

| Component | License / terms | Notes |
|-----------|-----------------|-------|
| FFmpeg / ffprobe | LGPL/GPL (build-dependent); Gyan essentials used locally | Final encode authority; args never shell-interpolated from customer text |
| Pillow | HPND | Frame composition |
| EdgeTTS | MIT (existing project dep) | **Network adapter** (Microsoft speech endpoint) — free, no paid key, **not fully local**. Timeout/fail → silent-slide fallback via `reel_video._tts` returning False; video still renders without voiceover |
| libx264 / AAC via ffmpeg | As per FFmpeg build | CPU encode; no paid cloud render |
| Project music beds `data/music_beds/` | Operator must drop royalty-free tracks only | Empty by default; niche sanitized against path traversal |
| Customer logos/photos | Tenant-owned; require consent | No face-swap / unauthorized clone |
| Pollinations / paid video SaaS | **NOT used** by this cell | Forbidden by product mandate |

Pinned: use existing `requirements.lock.txt` — no new paid deps introduced by ADR-132.

## TTS truth (ADR-132)

Authoritative encode path is local FFmpeg. EdgeTTS is an **optional free network adapter**.
When TTS fails or is unavailable, segments use fixed-duration silent video (no voice) — already the
pipeline default when `has_audio` is false. Do not market this stack as "fully offline TTS".
