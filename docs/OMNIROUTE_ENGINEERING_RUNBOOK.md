# OmniRoute engineering runbook

_Current verified state: 2026-07-14._

## Boundary

OmniRoute 3.8.46 is a local WSL development gateway. It is not a production boot
dependency and is not approved for customer, voice, billing, CRM, compliance, or
automation traffic. LeadGen's production provider chain remains direct and continues
working when OmniRoute is stopped. `OMNIROUTE_ENABLED` stays OFF by default.

## Verified runtime

- Runtime: Node 22.23.1, OmniRoute 3.8.46; do not auto-upgrade to broken 3.8.47.
- Session: `leadgen-omni`, gateway window plus research/implement/review lanes.
- Dashboard/API: `http://127.0.0.1:20128`; LiveWS: loopback `127.0.0.1:20129`.
- API contract: `POST /v1/responses`; Chat Completions is not served.
- Memory: launchers export `OMNIROUTE_MEMORY_MB=2048`, verified by Doctor.
- Providers: Groq and Mistral have sanitized Responses smokes; Gemini is connected but
  its old 2.5 Flash catalog entry is retired and excluded from adapter routes.
- Adapter: `app/platform/omniroute_client.py`, explicit internal-sanitized task registry,
  one bounded fallback, default OFF, no production caller.

## Start and verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1
powershell -ExecutionPolicy Bypass -File scripts\omniroute-check.ps1
```

```bash
OMNI_HEALTHGUARD_WINDOW_SECONDS=20 bash scripts/omniroute-healthguard.sh
```

Healthy means one gateway process, version 3.8.46, API reachable, no reconnect storm,
and zero active LiveWS clients when no dashboard tab is open. Stale dashboard tabs can
create reconnect churn; close them and verify through one fresh tab.

## Credentials and safety

The admin enters passwords, keys, OAuth codes, OTPs, and recovery codes personally.
Never print or store their values in Git, docs, terminal history, screenshots, logs, or
Graphify. MCP and data-plane keys are referenced only through environment-variable names.
Only synthetic/public coding prompts may enter the local gateway.

## Rollback

1. Leave `OMNIROUTE_ENABLED=0`.
2. Stop the local gateway/tmux session if needed; LeadGen remains operational.
3. Restore the verified external backup under `/root/.omniroute_backups/` using the
   manifest in `docs/omniroute/ROLLBACK.md`.
4. Re-run the status and 20-second LiveWS checks.

Canonical detail:

- `docs/omniroute/ARCHITECTURE.md`
- `docs/omniroute/PROVIDER_MATRIX.md`
- `docs/omniroute/ROUTING_POLICY.md`
- `docs/omniroute/PRIVACY_AND_SECURITY.md`
- `docs/omniroute/OPERATIONS_RUNBOOK.md`
- `docs/omniroute/VERIFICATION_EVIDENCE.md`
