#!/usr/bin/env bash
set -euo pipefail

# SECURITY BOUNDARY: OmniRoute/free-provider workers never receive a repository
# worktree. Claude or ChatGPT creates and owns an isolated codex/<task> worktree,
# sends only a bounded sanitized context packet, and applies any accepted patch.
echo "REFUSED: OmniRoute worktree creation is disabled." >&2
echo "Use a Claude/ChatGPT governor-owned codex/<task> worktree instead." >&2
exit 2
