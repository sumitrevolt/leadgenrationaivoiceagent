# Production Go-Live Checklist

## Architecture
- [ ] Service boundaries documented.
- [ ] Workflow graph validated.
- [ ] Queue and scheduler maps created.
- [ ] External integrations wrapped behind internal services.

## Security
- [ ] RBAC verified.
- [ ] Secrets scanned.
- [ ] Webhook signatures verified.
- [ ] Rate limits configured.
- [ ] Audit logs enabled.

## Data
- [ ] Migrations tested.
- [ ] Backups configured.
- [ ] Restore tested.
- [ ] Critical indexes added.
- [ ] Deduplication verified.

## Automation
- [ ] All schedulers have locks.
- [ ] All queues have DLQ.
- [ ] All workflows have retry and timeout.
- [ ] All external side effects are idempotent.
- [ ] Dry-run mode works.

## Testing
- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] E2E tests pass.
- [ ] Load tests pass.
- [ ] Chaos tests executed.
- [ ] Production smoke test ready.

## Operations
- [ ] Dashboards ready.
- [ ] Alerts configured.
- [ ] Runbooks written.
- [ ] Incident process defined.
- [ ] Rollback plan documented.

## Certification
- [ ] Zero critical blockers.
- [ ] Production readiness score >= 90.
- [ ] CEO Agent approval.
