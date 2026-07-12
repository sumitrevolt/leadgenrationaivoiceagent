#!/usr/bin/env bash
set -euo pipefail

# Create isolated local worktrees for the three OmniRoute lanes.
# Local-only: no commit, push, deploy, or production access.

repo_root="${OMNI_REPO_ROOT:-$(git rev-parse --show-toplevel)}"
worktree_root="${OMNI_WORKTREE_ROOT:-$HOME/src/leadgenrationaiagent-worktrees}"
base_ref="${OMNI_BASE_REF:-main}"

cd "$repo_root"
mkdir -p "$worktree_root"

for lane in research implement review; do
  path="$worktree_root/$lane"
  branch="codex/omni-$lane"
  if [[ -e "$path" ]]; then
    echo "exists: $path (leaving it unchanged)"
    continue
  fi
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    git worktree add "$path" "$branch"
  else
    git worktree add -b "$branch" "$path" "$base_ref"
  fi
  echo "created: $lane -> $path [$branch]"
done

echo "Worktrees ready under: $worktree_root"
git worktree list
