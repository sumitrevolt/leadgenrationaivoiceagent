# Content Creation & Lead Generation Architecture

## Overview
A local-first, GPU-accelerated pipeline for automated high-quality content production and lead conversion.

## 1. Video Production Stack (The Foundation)
- **Scripting:** Mistral/Groq/Cerebras (via local API wrappers).
- **Voiceover (TTS):** EdgeTTS (hi-IN-SwaraNeural) - high-quality, free, natural.
- **Visuals (Generative):** Stable Diffusion XL (Local/Stable-Diffusion-WebUI) for B-Roll; Pollinations (API) for dynamic imagery.
- **Editing:** `MoviePy` (Python) for automated programmatic composition (highly scalable for local GPU rendering).
- **Subtitles:** Whisper (Groq-hosted/Local) → Auto-burnt into video via `ffmpeg`.

## 2. Automation Workflow
- **Pipeline:** Orchestrated by local Celery/Redis tasks (mirroring the project's existing backend architecture).
- **Input:** Raw business info/niche data -> Script Generator -> Generator -> Composite Engine (MoviePy).
- **Local GPU PC:** Hosts the heavy rendering engine (`render_node`).

## 3. Format Optimization
- **Dimensions:** Automated `ffmpeg` profiles for 9:16 (vertical), 1:1, 16:9.
- **Captions:** Whisper transcript exported to `.srt` -> styled via `ffmpeg` drawtext/subtitles filter.
- **Thumbnails:** Stable Diffusion XL + text overlay via `Pillow`.

## 4. Scheduling
- **Engine:** Redis-backed `Celery Beat` scheduling.
- **Distribution:** Integration via platform-specific APIs or headless browsers (for platforms without robust public APIs).

## 5. Lead-Gen Wiring
- **Conversion:** Call-to-action (CTA) inside video (visual/audio) -> QR code/vCard redirect -> `LeadsGenAI` landing page (Form capture).
- **Automation:** Form submission → webhook → CRM/WhatsApp/Email drip (WhatsApp via WAHA).

## 6. Rendering & Transfer Architecture
- **Render Node:** Local PC with RTX GPU.
- **Transfer:** `rsync` / `rclone` to VPS.
- **Agent Oversight:** Webhook triggers on VPS notify agent (via `ntfy`) for approval.

---
*Implementation Plan: Start with script automation + voice generation, then scale to programmatic video composition.*
