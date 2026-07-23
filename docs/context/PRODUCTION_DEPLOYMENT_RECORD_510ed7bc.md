# Production deployment record — `510ed7bc`

## Outcome
Video Review Stage 3 was deployed successfully and production is healthy at exact SHA `510ed7bc1c7834892f81b9db092d1febb50dad48`. The release is runtime-proven; the customer cohort remains fail-closed pending owner authentication and the one-client Jiya canary.

## Source
- Implementation commit: `a4547e05ad20ef8b0a8321f23e33c94043b61645`
- Pull request: #97, merged
- Merge/deploy SHA: `510ed7bc1c7834892f81b9db092d1febb50dad48`

## CI and deployment
- Gate-only merge run completed successfully before deployment.
- Operator-gated deployment run: `30002538121`
- Workflow URL: `https://github.com/sumitrevolt/leadgenrationaivoiceagent/actions/runs/30002538121`
- Gate, immutable image build/push, transactional migration step, five-service recreate, and readiness gate succeeded.
- Deployment log emitted `DEPLOY OK sha=510ed7bc1c7834892f81b9db092d1febb50dad48` at `2026-07-23T11:33:03Z`.
- Rollback: not used.
- `DEPLOY_ENABLED=false` after dispatch; deployment gate is disarmed.

## Runtime proof
At `2026-07-23T11:41:18Z`:
- `/health`: HTTP 200, status healthy, environment production, exact full SHA.
- `/health/ready`: HTTP 200, status healthy; database, Redis, LLM configuration, disk, and memory checks green.
- `app`, `worker`, `scheduler`, `worker_heavy`, and `worker_video`: exact image SHA and exact `APP_VERSION`, all running, restart count 0.
- Redis: celery=0, `dlq:failed_tasks`=0, `dlq:dead`=0, `dlq:resolved`=9.
- Vendored Chart.js and `/sw.js`: HTTP 200.
- Unauthenticated `/api/customer/videos`: HTTP 401, as required.

## Safety proof
- `PLATFORM_DIAL_DAILY=0`
- `VIDEO_CUSTOMER_REVIEW_ENABLED=0`
- `VIDEO_DAILY_SCHEDULER_ENABLED=0`
- `VIDEO_WHATSAPP_REVIEW_ENABLED=0`
- `WHATSAPP_AUTO_SEND=0`
- Video social/Postiz rollout flags unset/OFF
- No external send, publish, call, billing mutation, duplicate record, or production queue mutation observed.

## Authenticated canary boundary
The existing admin tab held stale privileged DOM but its Jiya impersonation request returned HTTP 401. Reload required fresh super-admin login. Password/2FA and direct production `.env` mutation are owner-controlled boundaries, so the customer cohort was not enabled and the authenticated Jiya MP4 canary was not claimed.

## Next action
Owner authenticates in the handed-off Admin Login tab and uses the owner-managed configuration path to enable only the review master flag plus `jiya-makeover` allowlist. Then run one read-only Preview canary while all WhatsApp, publish/social, scheduler, and calling switches stay OFF.
