# Content Pipeline — Production Contract

**Workflow ID:** `content.generation` · **Version:** 1 · **Owner:** Isha (Marketing Exec) + Dev (Data Analyst)
**Trigger:** daily 06:30 (blog) / 07:00 (client+self content) + on-demand → `team_scheduler`

## State machine
```
SEEDED(KB) → GENERATED → SCHEMA_VALIDATED → APPROVED → PUBLISHED/DISTRIBUTED  [terminal]
     │            │              │              │
     └────────────┴──────────────┴──────────────┴──► DRAFT_HELD (terminal — default, awaits human)
```
- **Default terminal = DRAFT_HELD** (ban-safe; no unsolicited auto-publish unless flag + approval).

## Step → module map (real code)
| Step | Module | Idempotency |
|---|---|---|
| KB seed | `marketing/auto_content.py` + Dev onboarding | client id + niche |
| Generate | `marketing/auto_content.py` (free LLM chain) + `seo_blog` | date + client + topic |
| Validate | Instructor structured output (`USE_STRUCTURED_CONTENT`) | content id |
| Approve | `marketing/content_approval.py` | content id |
| Publish | `social_engine.enqueue_publish()` (`SOCIAL_ENGINE`) / blog + IndexNow | content id |

## Validation & reliability
AI outputs schema-validated. Per-day dedupe (state file, success-only mark → retry next tick).
Boot-grace: heavy content job skips on a boot inside its window (restart-storm guard).

## Events
`content.generated` · `content.approved` (internal `agent_events`).

## Metrics & alerts
`agent_events` · content count/approval rate · SEO rank-tracker (Ravi) · ntfy on failure.

## Test matrix (E2E)
happy generate · KB-empty fallback · schema-invalid retry · approval gate · publish path ·
duplicate-day skip. Coverage: `test_seo_blog.py`, `test_marketing.py`, `test_social_page_kit.py`, `test_content`*.

## Runbook
[Provider Outage](../runbooks/RUNBOOK_PROVIDER_OUTAGE.md) · [Scheduler Failure](../runbooks/RUNBOOK_SCHEDULER_FAILURE.md).
