# FastAPI MCP Windows import repair

Goal: Windows `--no-deps` setup me FastAPI MCP import ko usable banana aur nested dependency failure ko truthful startup log me dikhana.

Approach: `pywin32` ko Windows-only lock entry ke roop me pin karna, MCP import-error classification ko small pure helper me rakhna, aur `app.main` ko exact missing module report karwana. Linux/VPS build marker ko skip karega; `/mcp` auth gate unchanged rahega.

Change-risk tier: Standard. Runtime startup integration touch hota hai, lekin MCP optional/fail-safe aur existing token/IP gate unchanged hai. Rollback: helper/main diff revert + Windows-only lock entry remove.

## File map

- `requirements.lock.txt`: Windows-only `pywin32` pin; main session only.
- `app/platform/mcp_import.py`: pure import-error classifier.
- `app/main.py`: classifier-backed truthful logging; main session only.
- `tests/test_mcp_import.py`: focused regression coverage.
- `progress.md`: Loop Engineer evidence ledger; main session only.

## Tasks

1. RED: classifier tests add karke missing top-level package aur nested `pywintypes` failure ke distinct messages assert karna.
2. GREEN: pure classifier implement karke `app.main` ke `ImportError` branch me wire karna.
3. Dependency: `pywin32==311; sys_platform == "win32"` lockfile me add karna aur local venv me install karna.
4. Verify: focused pytest, direct `FastApiMCP` import, `prod_check.py`, `check_secrets.py`, aur duplicate `/mcp` route grep.
5. Record: exact results `progress.md` Loop Run me append karna.

## Wiring

Koi naya route, env flag, scheduler hook, worker behavior, UI surface, ya auth behavior nahi. Existing `/mcp` token/IP fail-closed gate as-is rahega.
