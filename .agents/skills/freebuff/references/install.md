# FreeBuff — Installation & Setup Notes

## Install

```bash
npm install -g freebuff
```

Verifies to `%APPDATA%/Local/hermes/node/node_modules/freebuff/` on Windows
when installed via the Hermes npm namespace. The `freebuff` binary is on PATH.

## First Run

1. `freebuff login` — opens browser for authentication
2. After login, `freebuff --cwd <project>` to start working

## Profile Integration

- FreeBuff is a **separate CLI tool**, not a Hermes profile. It runs in the
  terminal and uses its own authentication and model selection.
- The skill `autonomous-ai-agents/freebuff` instructs Hermes agents how to
  delegate coding tasks to it.
- Compare with the coding-agent family:
  - `claude-code` — supports both `-p` (print/non-interactive) and interactive tmux
  - `codex` — supports both `codex exec` (one-shot) and interactive modes
  - `freebuff` — **interactive TUI only**

## Where FreeBuff Fits

FreeBuff is the **free** option in the coding-agent stack. It is appropriate
for routine coding tasks where cost is a concern. For one-shot automation
where a non-interactive mode is needed, prefer `claude-code -p` or `codex exec`.

## Troubleshooting

- **`freebuff` not found**: Ensure `%APPDATA%/Local/hermes/node` is on PATH.
  Verify with `which freebuff` or `freebuff --version`.
- **Login fails**: Check network access to `freebuff.com`. Corporate proxies
  may block the OAuth flow.
- **Model picker not appearing**: The free daily session limit may be reached
  (limited mode = 6 one-hour sessions/day). Wait or switch to GLM 5.3 Flash
  which is always unmetered.
- **Node version issues**: FreeBuff requires Node >= 16. Verify with
  `node --version`.
