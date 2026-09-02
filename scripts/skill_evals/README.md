# LeadGen skill CI gates

Deterministic, stdlib-only checks for the canonical `.claude/skills` catalog.
They do not call a model, use the network, or execute scanned skill content.

## Provenance

`skill_lint.py`, `skill_scanner.py`, and `run_trigger_evals.py` are vendored
from [`Shubhamsaboo/awesome-llm-apps`](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/779e9f9bcf87fa8cd95870a438b70b84e47d3173/agent_skills/evals/tools)
at commit `779e9f9bcf87fa8cd95870a438b70b84e47d3173`, under Apache-2.0. The complete
upstream licence is retained in `LICENSE.upstream`.

Vendored Python is normalized by this repo's Black/ruff hooks. Functional
LeadGen changes are limited to `run_trigger_evals.py`: explicit catalog/eval
roots, UTF-8 reads on Windows, and an `--only` ratchet mode. The repo-specific
orchestrator is `check_repo_skills.py`.

## Gate policy

The imported catalog already has legacy debt (2026-08-05 audit: 164 strict-lint
failures, 18 critical scanner findings, 11 description collisions). CI therefore
checks every added or modified skill strictly instead of pretending the old tree
is clean:

- structural lint runs with `strict=True`;
- any CRITICAL security finding blocks;
- the changed skill's description is compared with the full catalog;
- every newly added skill must include
  `scripts/skill_evals/cases/<skill>/trigger-cases.json`.

This is a monotonic ratchet: old debt cannot excuse new debt.

## Run

```bash
python scripts/skill_evals/check_repo_skills.py --base-ref <base-sha>
python scripts/skill_evals/check_repo_skills.py --skill <skill-name>
python scripts/skill_evals/check_repo_skills.py --skill <new-skill> --added <new-skill>
```

Exit codes: `0` clean/no relevant changes, `1` blocking finding, `2` usage or
Git-history error.
