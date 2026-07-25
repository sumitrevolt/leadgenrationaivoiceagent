# ADR-143 — Creative Automation OS (governed extension of Video Production Cell)

**Date:** 2026-07-24
**Status:** ACCEPTED (code-present; production flags OFF)
**Supersedes:** nothing — extends ADR-140 / ADR-141 / ADR-142

## Context

LeadGen already has a working deterministic FFmpeg video pipeline (`video_pipeline`),
approval lifecycle (`video_ad_cycle` + `content_approval`), exact-revision publish gate
(`video_production/publish_gate`), Celery `video` queue, Owner OS authority, OmniRoute,
and Postiz. The product needs a governed **Creative Automation OS** for static posters,
carousels, reels/shorts, captions, thumbnails, exact approved revisions, and
performance-linked learnings — without replacing those seams or creating parallel stacks.

## Decision

1. Add `app/marketing/creative_os/` as the additive Creative Automation OS layer.
2. Canonical generation path remains: CreativeSpec → recipe → provider adapter →
   deterministic FFmpeg fallback → QA → exact-hash approval → Postiz (existing gate).
3. First real provider = `deterministic` (existing `video_pipeline.render_creative_video`).
4. Adapter skeletons only (fail-closed) for Qwen-Image, FLUX.1-schnell, Wan2.2, ComfyUI.
   LTX-2 / HunyuanVideo / FLUX.dev stay off the production allowlist.
5. New flags default OFF: `CREATIVE_OS_ENABLED`, `CREATIVE_PROVIDER_*`, GPU/lab flags.
6. Licence registry separates software licence vs model-weight licence; unknown = blocked.
7. Asset registry is tenant-scoped with SHA-256, consent, revocation.
8. Approval binds creative_id + revision + spec/output/caption/channel hashes.
9. Admin Creative Production cockpit extends existing admin/automation surfaces.
10. Performance learning is a data contract + recommendation seam only — never
    silent prompt mutation or auto-spend.
11. Calling remains HARD OFF; Marketing vs Voice products stay separate.

## Consequences

- Rollback: `CREATIVE_OS_ENABLED=0` (+ related `CREATIVE_*` flags OFF). Legacy
  video cell behaviour unchanged.
- Production activation requires owner authorization, hardware/licence preflight
  for GPU providers, and authenticated browser canary — not implied by merge.
- Phase 2 benchmark harness may land inert; no production weight downloads.

## Verification (local)

Targeted creative_os + video regression suites, `prod_check.py`, `check_secrets.py`.
No production deploy in the introducing PR unless separately authorized.
