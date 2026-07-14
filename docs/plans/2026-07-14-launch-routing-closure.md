# Launch routing closure plan

## Goal and approach

Close the remaining reproducible launch-day routing/tooling drift without enabling
OmniRoute for customer or production traffic. Repair the sanitized benchmark to use
OmniRoute 3.8.46's verified Responses API, make every one-command local launcher retain
the 2 GB memory setting, and refresh the generated API route index.

## Change-risk tier

Standard local-tooling and generated-documentation change. No public route, database,
provider credential, scheduler, customer data, or production feature flag is changed.
Rollback is reverting the scripts/docs while keeping `OMNIROUTE_ENABLED=0`.

## File map

| File | Change |
| --- | --- |
| `tests/test_omniroute_scripts.py` | Red-first contracts for Responses API and launcher memory parity. |
| `scripts/omniroute-benchmark.ps1` | Send sanitized Responses API payloads and read Responses usage fields. |
| `scripts/_leadgen_dev_up.sh` | Export `OMNIROUTE_MEMORY_MB=2048` in both gateway start paths. |
| `.gitattributes` | Keep the WSL launcher LF-only so direct Bash parsing stays valid. |
| `app/api/automation_flags.py` | Correct stale provider/runtime commentary; keep the flag default-OFF. |
| `docs/API.md` | Regenerate the route index using the repository sync script. |
| `progress.md` | Append verified loop evidence. |

## Tasks and proof

1. Add contracts that fail on `/v1/chat/completions`, Chat Completions payloads, or a
   one-command launcher missing the 2 GB export.
2. Apply the smallest script changes, normalize the WSL launcher to LF, and run the
   focused OmniRoute suite plus direct Bash/PowerShell syntax gates.
3. Run `scripts/sync_api_docs.py`, then prove `prod_check.py` no longer reports index drift.
4. Run the secrets scan, PowerShell parser, shell syntax checks, fresh 20-second WS guard,
   critical routing contracts, and public production health.
5. Selectively stage only this closure patch. Do not stage unrelated dirty work or data.

## Wiring and safety

No FastAPI decorator, router mount, scheduler job, worker route, `.env` value, or external
send/call changes. OmniRoute remains local, optional, loopback-only, and fail-open for
availability while privacy admission stays fail-closed.
