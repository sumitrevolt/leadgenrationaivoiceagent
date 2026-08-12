"""Code-upgrader patch status CLI (ops helper — SSH quoting se bachne ke liye).

Usage (VPS): docker exec leadgen_app python scripts/patch_status.py <patch_id> <status> [note...]
status = approved | rejected | applied
"""

import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: patch_status.py <patch_id> <approved|rejected|applied> [note]")
        return 1
    from app.agents import code_upgrader

    pid, status = sys.argv[1], sys.argv[2]
    note = " ".join(sys.argv[3:])
    print(code_upgrader.set_status(pid, status, note))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
