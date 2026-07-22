# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Agent Runtime PR #72 — CI GREEN, PROD CANARY BLOCKED (auth)
- **ID:** WS-1
- **Branch / worktree:** `feat/agent-runtime-workforce-31` @ `leadgen-agent-runtime-31`
- **PR:** #72 draft, head `676c51a`, CI success, mergeable
- **Drift:** `SAFE_BEHIND_DOCS_ONLY` (prod `7ce4d979` → main `10a3996a` docs-only)
- **Local:** Pranav canary_proven
- **Prod Pranav workforce canary:** BLOCKED — OWNER AUTHORIZATION REQUIRED (merge+deploy)
- **Note:** Prod already has `AGENT_RUNTIME=1`/`SRE_AGENT=1` on **old** image (3 pilots only)
- **Next exact action:** Owner authorize merge of #72 + deploy; then single Pranav canary loop

---

## WS-2 Jiya delivery — PARKED

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
