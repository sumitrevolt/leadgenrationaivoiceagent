#!/usr/bin/env bash
# Isolated candidate checkout for the release gates.
#
# WHY NOT JUST `git pull` FIRST
# -----------------------------
# Production ledgers — invoices, consent, suppression, the customer registry and
# 182 MB of DPDP call recordings — still live INSIDE /opt/leadgen. That is the
# whole reason `_runtime_data_guard.sh` must run before the first destructive
# Git command, and it is why the gates cannot be moved after the pull "just to
# make them run against the new code". Both requirements are real, and they look
# contradictory only while the candidate code and the live checkout are the same
# directory.
#
# So they are not. `git fetch` updates the object database and touches neither
# the live worktree nor a single data file; the candidate SHA is then checked
# out into its own detached worktree, well away from production state. The gates
# read the candidate source and the LIVE data, decide, and only after both say
# yes does /opt/leadgen move at all.
#
# The worktree is deliberately left in place when a gate denies: the next
# operator gets to inspect exactly what was rejected.

# candidate_fetch <repo> — object database only. No worktree, no data, no HEAD move.
candidate_fetch() {
  local repo="$1"
  echo "=== fetch origin (object database only — live checkout untouched) ==="
  git -C "$repo" fetch origin main || {
    echo "FATAL: git fetch failed — refusing to deploy on a stale object database."
    return 2
  }
}

# candidate_resolve <repo> <ref> — full 40-char sha, or non-zero.
candidate_resolve() {
  local repo="$1" ref="$2" sha=""
  sha="$(git -C "$repo" rev-parse --verify "${ref}^{commit}" 2>/dev/null)" || {
    echo "FATAL: '$ref' is not a commit in $repo after fetch." >&2
    return 2
  }
  printf '%s\n' "$sha"
}

# candidate_dir <repo> <sha>
candidate_dir() {
  local repo="$1" sha="$2"
  printf '%s/%s\n' "${CANDIDATE_ROOT:-${repo}-candidates}" "$sha"
}

# candidate_add <repo> <sha> — create (or reuse) the detached worktree and PROVE
# it is at the exact sha. A reused directory that drifted is a fail-closed
# condition, not something to repair silently.
candidate_add() {
  local repo="$1" sha="$2" dir=""
  dir="$(candidate_dir "$repo" "$sha")"

  if [ ! -d "$dir" ]; then
    mkdir -p "$(dirname "$dir")" || return 2
    git -C "$repo" worktree add --detach "$dir" "$sha" >/dev/null 2>&1 || {
      echo "FATAL: could not create candidate worktree at $dir" >&2
      return 2
    }
  fi

  local head=""
  head="$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)"
  if [ "$head" != "$sha" ]; then
    echo "FATAL: candidate worktree HEAD=$head but the release is $sha." >&2
    echo "       Refusing to gate one tree and deploy another." >&2
    return 2
  fi

  # A candidate that carries its own data/ would give the gates a view of an
  # empty, perfectly clean system that does not exist. The live data is mounted
  # over this path read-only by the gate runner; assert the mount point exists
  # so the bind cannot silently create a root-owned directory instead.
  mkdir -p "$dir/data" 2>/dev/null || true

  # Compose resolves the app service's `env_file: .env` against the project
  # directory, so a candidate build needs one. A SYMLINK, never a copy: the
  # production environment must exist in exactly one place, and a copied .env
  # left behind under /opt/leadgen-candidates would be a second, stale, secret-
  # bearing file nobody rotates.
  ln -sfn "$repo/.env" "$dir/.env" 2>/dev/null || true

  printf '%s\n' "$dir"
}

# candidate_remove <repo> <dir> — only on a fully successful release.
candidate_remove() {
  local repo="$1" dir="$2"
  [ -n "$dir" ] || return 0
  git -C "$repo" worktree remove --force "$dir" >/dev/null 2>&1 || true
}
