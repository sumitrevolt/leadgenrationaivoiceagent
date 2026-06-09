---
description: Session ka reusable pattern/gotcha extract karke SESSION_LOG.md ya naya .claude skill me save karo.
---
# /learn — reusable patterns capture karo

Koi non-trivial problem solve karne ke baad chalao. **Re-derive mat karna — capture karo** (token bachao).

## Kya extract karo
- **Gotcha → fix**: error → root cause → fix (reusable?). e.g. "Pollinations 402 → POLLINATIONS_TOKEN", "sandbox mount stale → Windows = truth", "first-route-wins → grep `@router` before adding".
- **Workaround**: library/API quirk, version-specific fix, SSH/cmd quoting trick (base64-over-ssh).
- **Pattern**: codebase convention, integration discipline (gated/inert-without-creds/never-raise).

## Kahan save
- **Chhota gotcha** → `docs/SESSION_LOG.md` + (hot ho to) 1-line CLAUDE.md "Critical Env Gotchas" me.
- **Reusable workflow** → naya `.claude/skills/<name>/SKILL.md` (frontmatter `name` + `description` with triggers; existing skills ka format match karo — `leadgen-ops`, `marketing-feature` dekho).

NOTE: project skills `.claude/skills/` me banao (repo files). Cowork ke managed-skills cache read-only hai — usme nahi.

Output: kahan save kiya + 1-line summary.
