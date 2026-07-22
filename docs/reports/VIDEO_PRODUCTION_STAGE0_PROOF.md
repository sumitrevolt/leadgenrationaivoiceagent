# Video Production Cell — Stage 0 local proof (sanitized)

**Status:** Stage 0 locally verified; ready for PR review and controlled canary preparation.
**Not claimed:** production deploy, live WhatsApp, live Postiz publish, authenticated browser E2E, Jiya canary.

## How to regenerate

```powershell
.venv\Scripts\python.exe scripts\video_production_local_proof.py
```

Outputs land in gitignored `data/video_production_proof/` (basenames only in `proof_summary.json`).

## Expected shape (example)

| ratio | width | height | streams |
|-------|-------|--------|---------|
| 9:16 | 720 | 1280 | h264 + optional aac |
| 1:1 | 1080 | 1080 | h264 + optional aac |
| 16:9 | 1280 | 720 | h264 + optional aac |

Large MP4 binaries are **not** committed. EdgeTTS may be unavailable offline; silent-slide fallback still produces valid video.
