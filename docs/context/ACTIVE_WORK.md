# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Delivery assurance operator surface — CLOSED (PARTIAL proof)
- **ID:** WS-1
- **Business outcome:** Admin can see missed/at-risk paid customers
- **Current state:** MERGED historically. Optional admin UI smoke only.

---

## WS-2 Jiya delivery assurance proof and operator recovery flow — PARKED
- **ID:** WS-2
- **Business outcome:** Jiya reaches honest `proof` / recoverable delivery gaps
- **Current state:** PARKED; human approve-drafts vs Meta still EXTERNAL
- **Next exact action:** Resume after OpenClaw PR merge or parallel human path

---

## WS-3 OpenClaw Daily Video Production Cell — LOCAL COMPLETE (flags OFF)
- **ID:** WS-3
- **Business outcome:** Daily enterprise videos per tenant with WhatsApp/dashboard approval before Postiz publish
- **Owner:** Platform / Sumit
- **Branch:** `feat/openclaw-daily-video-production`
- **Acceptance (Stage 0 local):**
  - Graphify reuse of video_ad_cycle/pipeline/approval/postiz ✅
  - Harness `video.*` tools registered (8) ✅
  - State machine + version-bound publish gate ✅
  - Feedback classifier (ambiguous ≠ approve) ✅
  - Real local renders 9:16/1:1/16:9 + ffprobe ✅
  - pytest 50 green + prod_check PASS ✅
  - Flags default OFF ✅
  - Prod deploy NOT done; WhatsApp/Jiya canary NOT done
- **Current state:** Deploy-ready code on feature branch; all VIDEO_* flags OFF
- **Next exact action:** User review → commit/PR when asked → Stage 2 own-brand canary only after explicit flag authorization
- **Out of scope this wave:** Remotion, paid APIs, platform_dial, Swara/voice edits
