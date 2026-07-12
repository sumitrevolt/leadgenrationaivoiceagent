# OmniRoute + tmux development setup

Status: local development only. This setup does not change the LeadGen production LLM/voice path, Docker Compose, VPS `.env`, Celery workers, or customer data flow.

## Architecture

```text
WSL2/Linux laptop
  tmux
   ├── OmniRoute (127.0.0.1:20128)
   ├── research/context lane
   ├── implementation lane
   └── tests/review lane

LeadGen production
  FastAPI -> existing app/voice_agent/free_ai.py
  Celery/Redis -> existing queues and workers
  OmniRoute -> absent
```

OmniRoute is used only as a coding-agent gateway. It must receive sanitized repository context, never production/customer/voice data. Its provider and compression claims require the benchmark below before adoption.

## One-time machine prerequisites

The preferred host is WSL2 with Ubuntu 24.04 or another maintained Linux distribution. Check from PowerShell:

```powershell
wsl.exe --status
wsl.exe --list --verbose
```

If no distribution is installed, install Ubuntu from an elevated PowerShell, restart if Windows requests it, then complete the Linux username setup:

```powershell
wsl.exe --install -d Ubuntu-24.04
```

Inside WSL:

```bash
sudo apt-get update
sudo apt-get install -y tmux curl git
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm install 22
nvm alias default 22
npm install -g omniroute
omniroute doctor
```

Use separate WSL worktrees under `~/src` for faster file I/O and one branch/worktree per lane:

```bash
bash scripts/omniroute-worktrees.sh
```

The helper creates `codex/omni-research`, `codex/omni-implement`, and
`codex/omni-review` under `~/src/leadgenrationaiagent-worktrees`. Existing
paths are left unchanged, so it is safe to run once per new machine.

## Start OmniRoute

```bash
omniroute
```

Keep it loopback-only at `http://127.0.0.1:20128`. Connect only development providers. Use `auto/coding` for coding, `auto/fast` for navigation, and compression `off` for sensitive or structured prompts.

Disable MCP, A2A, remote mode, cloud sync and public tunnelling for the first pilot.

## Start the three development lanes

From the repository root in WSL:

```bash
bash scripts/omniroute-worktrees.sh
export OMNI_PROJECT_ROOT="$HOME/src/leadgenrationaiagent-worktrees/implement"
export OMNI_RESEARCH_ROOT="$HOME/src/leadgenrationaiagent-worktrees/research"
export OMNI_IMPLEMENT_ROOT="$HOME/src/leadgenrationaiagent-worktrees/implement"
export OMNI_REVIEW_ROOT="$HOME/src/leadgenrationaiagent-worktrees/review"
bash "$(git rev-parse --show-toplevel)/scripts/omniroute-tmux.sh"
```

Use Node 22 LTS for OmniRoute. Its SQLite native dependency is sensitive to
Node ABI versions; if a fresh install was interrupted, reinstall OmniRoute
with install scripts enabled before running `omniroute doctor`.

The launcher creates one tmux session named `leadgen-omni` with three worktree panes plus a `gateway` window running OmniRoute under Node 22 LTS. It does not create branches, commit, push, deploy, or touch production. Re-running it repairs a missing gateway window.

```bash
tmux attach -t leadgen-omni
tmux kill-session -t leadgen-omni
```

Only one lane may edit a given file at a time. Research and review lanes are read-only by convention; implementation owns the patch. Human approval remains required for commit, push, deploy, send, call and billing actions.

## Benchmark gate

Run the same five to twenty sanitized coding tasks with and without OmniRoute. Record latency, input/output tokens, fallback count, test result, retries and human correction time. Accept only if quality is unchanged and measured token or elapsed-time improvement is at least 25%.

Do not benchmark with `.env`, customer leads, phone/email lists, recordings, WhatsApp IDs, database dumps, raw production logs or billing data.

## Production boundary and rollback

No `OMNIROUTE_*` variable belongs in the VPS production `.env`. Existing `free_ai.py`, provider circuit-breakers, voice compliance gates and Celery queues remain the production source of truth.

Rollback: stop the tmux session, unset the local OmniRoute endpoint, and return the coding tool to its previous provider configuration. No Docker recreate or production deploy is required.

## Current machine status

On 2026-07-12, WSL2 was enabled but no Linux distribution was installed. The Windows npm install attempt did not complete, so OmniRoute is not claimed as installed until `omniroute doctor` passes inside WSL.
