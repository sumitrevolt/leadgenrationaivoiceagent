"""Force-pull a single frontend asset on the VPS, then rebuild the app container.

GUARDED. The command chain below starts with `git stash`, which removes the
live-mutated files under `data/` from the working tree — that is where the
invoice ledger, consent ledger, suppression ledgers and customer registry
currently live. `git pull` then follows. So this is a production-destructive
path even though its `git clean` is scoped to one frontend file.

The runtime-data preflight must succeed before ANY of it runs. There is no
bypass flag and no fallback that performs the mutation anyway.
"""

import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PREFLIGHT = SCRIPTS / "runtime_data_preflight.py"


def preflight_ok() -> bool:
    """Run the shared deny authority. Any non-zero exit blocks the deploy."""
    result = subprocess.run(
        [sys.executable, str(PREFLIGHT), "check-deploy"],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout or "")
    sys.stderr.write(result.stderr or "")
    return result.returncode == 0


def main() -> int:
    if not preflight_ok():
        # Deliberately NOT wrapped in try/except: a swallowed denial would be
        # indistinguishable from an approval.
        print(
            "\nFATAL: runtime-data preflight DENIED this deployment.\n"
            "       `git stash` below would remove live mutable state from the\n"
            "       working tree while it still lives inside the Git checkout.\n"
            "       See the blocker list above."
        )
        return 90

    cmds = [
        "cd /opt/leadgen",
        "git stash",
        "git clean -fd frontend/explorer.html",
        "git pull origin main",
        "docker compose -f docker-compose.vps.yml build app 2>&1 | tail -8",
        "docker compose -f docker-compose.vps.yml up -d --no-deps app",
        "sleep 18",
        'curl -s https://leadsgenai.in/health | python3 -c "import sys,json; '
        "d=json.load(sys.stdin); print('HEALTH:', d.get('environment'), d.get('status'))\"",
    ]
    full = " && ".join(cmds)
    # nosec B602 - pre-existing design: `cmds` is a fixed literal list with no
    # interpolation and no caller input, and the `&&` chaining requires a shell.
    # Flagged only because this file changed to ADD the preflight guard above;
    # the shell usage itself is untouched and carries no injection surface.
    result = subprocess.run(full, shell=True, capture_output=True, text=True)  # nosec B602
    print(result.stdout[-3000:] if result.stdout else "")
    print(result.stderr[-1000:] if result.stderr else "")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
