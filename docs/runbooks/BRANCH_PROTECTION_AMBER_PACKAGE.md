# Branch-protection / ruleset package — AMBER (owner authorization required)

Date: 2026-07-26
Repo: sumitrevolt/leadgenrationaivoiceagent
PR context: #146 (draft) — do **not** apply without explicit owner go-ahead.

## Current state (verified)

Classic branch protection API:

```text
GET /repos/.../branches/main/protection → 404 "Branch not protected"
```

Active **repository ruleset** (this is the real floor):

| Field | Value |
|-------|-------|
| id | `19718692` |
| name | Protect main — PR + required CI |
| enforcement | `active` |
| target | `refs/heads/main` |
| PR rule | required_approving_review_count=**0** (single-owner compatible) |
| required checks | `Lint + syntax + secrets`, `prod_check + pytest`, `harness real-redis integration` |
| strict (branch up to date) | **true** |
| force push | blocked via `non_fast_forward` |
| branch deletion | blocked via `deletion` |
| conversation resolution | **false** |
| bypass actors | **none** (`current_user_can_bypass=never`) |

Exact successful check **names** observed on PR #146 head `1a6eb07…`:

- `Lint + syntax + secrets` (SUCCESS)
- `prod_check + pytest` (SUCCESS)
- `harness real-redis integration` (SUCCESS)
- `test` (SUCCESS) — **not** currently required by the ruleset
- `GitGuardian Security Checks` (SUCCESS) — **not** currently required
- `Trivy repo scan + SBOM` (SUCCESS)
- `enable-auto-merge` (SKIPPED on draft / no label) — correct

## Proposed optional hardening (AMBER — not applied)

Add the two already-green contexts that are not yet required, and turn on conversation resolution. Leave approving-review count at 0 for the single-owner personal repo.

```bash
# READ current first
gh api repos/sumitrevolt/leadgenrationaivoiceagent/rulesets/19718692 > /tmp/ruleset-19718692.before.json

# PUT updated rules (owner must run). Keep review_count=0.
gh api -X PUT repos/sumitrevolt/leadgenrationaivoiceagent/rulesets/19718692 \
  --input - <<'JSON'
{
  "name": "Protect main — PR + required CI",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "required_reviewers": [],
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {"context": "Lint + syntax + secrets"},
          {"context": "prod_check + pytest"},
          {"context": "harness real-redis integration"},
          {"context": "test"},
          {"context": "GitGuardian Security Checks"}
        ]
      }
    },
    {"type": "non_fast_forward"},
    {"type": "deletion"}
  ],
  "bypass_actors": []
}
JSON
```

### Expected effect

- `main` still requires a PR (no direct push via ruleset PR rule).
- Merge blocked until the five named checks are green and the branch is up to date.
- Unresolved review threads block merge.
- Force-push / branch deletion remain blocked.
- Auto-merge can only complete when those checks are green (still also needs a non-draft PR + `auto-merge` label).

### Rollback

```bash
gh api -X PUT repos/sumitrevolt/leadgenrationaivoiceagent/rulesets/19718692 --input /tmp/ruleset-19718692.before.json
```

### Impact on open PRs

Any open PR targeting `main` must pass the additional `test` and `GitGuardian Security Checks` contexts before merge. Draft PRs are unaffected until marked ready.

## Auto-merge workflow note

`.github/workflows/auto-merge.yml` enables GitHub auto-merge when the `auto-merge` label is present and the PR is not draft. With the active ruleset, GitHub will still wait for required checks — so an empty required-check floor is **not** the current state. A separate bounded mission could still harden the workflow to refuse enabling auto-merge when required contexts are empty; that change is intentionally **out of scope for PR #146**.
