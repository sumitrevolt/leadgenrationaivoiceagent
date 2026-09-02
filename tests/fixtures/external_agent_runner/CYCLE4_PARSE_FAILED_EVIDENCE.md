# Cycle-4 independent review transport evidence (sanitized)

Facts are SEPARATE:

1. Process / transport: `exit_code=1`, classification `parse_failed:claude_review_not_json`
   (mission `msn_74bdc44bb5614913`, head `653663e4e465f74db83bb0d77aae741faeb689f0`).
2. Recovered structured verdict from Claude session transcript: `CHANGES_REQUIRED`
   (same mission ID / reviewed head). Recovery ≠ successful transport.

No secret-bearing raw CLI dump is stored in-repo. Bounded sanitized tails lived
under `%TEMP%/pr147_review_parse_fail_*.json` only.

Regression coverage: `tests/test_external_agent_runner_windows_security.py::test_review_recovery_separates_transport_and_verdict`
and `app/dev_control/external_agents/runner/review_parse.py`.
