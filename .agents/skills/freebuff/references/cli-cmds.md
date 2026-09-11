# FreeBuff CLI — Command Reference

## Verified CLI Flags (freebuff v0.0.173)

```
Usage: freebuff [options] [command]

Arguments:
  command    Command to run (choices: "login")

Options:
  -v, --version          Print the CLI version
  --continue [conversation-id]  Continue from a previous conversation
  --cwd <directory>      Set the working directory (default: current directory)
  -h, --help             Show this help message
```

**There is NO `-z` flag. There is NO non-interactive/print mode.**
FreeBuff is a purely interactive TUI application. Every task requires an
active terminal session.

## Invocation Patterns

### Interactive session (the only real mode)
```
freebuff --cwd <project-dir>
```
Launches the TUI. Must use `terminal(background=true)` or `pty=true` in
Hermes. The session is fully interactive — send follow-up inputs via
`process(action='submit', session_id=..., data='...')`.

### Continue a previous session
```
freebuff --continue [conversation-id] --cwd <project-dir>
```
Resumes an existing conversation by ID. Must also use `pty=true`.

### Login (first run only)
```
freebuff login
```
Opens browser for authentication. One-time setup.

## Hermes Terminal Invocation

Because FreeBuff is interactive-only, always use PTY:

```python
from hermes_tools import terminal

# Interactive background session
proc = terminal("freebuff --cwd C:/path/to/repo", background=true, pty=true)
# Session_id for monitoring: proc['session_id']

# Send follow-up text after it starts
terminal(action='submit', session_id=proc['session_id'], data='add error handling')

# Check status
terminal(action='poll', session_id=proc['session_id'])

# Kill if needed
terminal(action='kill', session_id=proc['session_id'])
```

**Do NOT try `terminal("freebuff -z ...")`** — the flag does not exist and
the command will fail with a usage error.

## Known Limitations

- **No print/non-interactive mode**: Cannot pipe input or get output to stdout
  for one-shot tasks. Every invocation is a full TUI session.
- **No `--continue` with `-z`**: Resume flag only works in interactive mode.
- **Session persistence**: Conversations persist across terminal sessions but
  the TUI must be attached to interact.
- **Platform**: Windows, macOS, Linux (Node.js >= 16 required).

## Model Selection

FreeBuff presents a model picker on first launch. Models vary by region:
- **Full access** (US, CA, UK, EU, select countries): GLM 5.3 Flash, DeepSeek V4.1 Flash,
  GPT-5.6 Luna, MiMo 2.5, Solar Pro 4, Muse Spark 1.2
- **Limited mode** (elsewhere / VPN): GLM 5.3 Flash, DeepSeek V4.1 Flash,
  MiMo 2.5, Solar Pro 4 — 6 one-hour sessions/day, earn up to 7 via engagement
- **GLM 5.3 Flash** is always free and default — the safest choice
