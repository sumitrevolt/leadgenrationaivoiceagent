---
name: babysit
description: Keep a PR merge-ready by triaging comments, resolving conflicts, and fixing CI in a loop. Use when user says babysit PR, fix CI until green, or resolve review comments.
---
# Babysit PR (Claude Code)

Merge-ready tak loop. Tool: `gh` (GitHub CLI).

## Steps

1. **Status:** `gh pr view` · checks · review threads (unresolved only).
2. **Conflicts:** merge/rebase intelligently; intent clash → stop + ask user.
3. **Comments:** Bugbot/human — validate before fix; skip noise.
4. **CI:** fix only **this PR scope**; never weaken workflows to pass. Branch behind base → merge main first.
5. Push scoped fixes · re-watch until mergeable + green.

## LeadGen

- Windows git: `C:\PROGRA~1\Git\cmd\git.exe`
- Deploy verify after merge: `leadgen-ops` skill
- Never force-push main without explicit user OK
