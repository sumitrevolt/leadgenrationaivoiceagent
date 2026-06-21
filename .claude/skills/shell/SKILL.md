---
name: shell
description: Execute literal shell command when user invokes /shell. Use only for explicit /shell requests — run command as-is without rewriting.
disable-model-invocation: true
---
# Shell (literal execution)

1. Text after `/shell` = exact command.
2. Run immediately (Bash tool / terminal).
3. Do not "improve" the command first.
4. Empty `/shell` → ask which command.

## LeadGen gotchas

- Windows: Git ssh `C:\PROGRA~1\Git\usr\bin\ssh.exe` for VPS
- OpenSSH broken → Git ssh only
- Complex one-liners → `.bat` file + log Read
- VPS smoke → `python scripts/x.py` via ssh, not inline `&`

Report exit code + important stdout/stderr briefly.
