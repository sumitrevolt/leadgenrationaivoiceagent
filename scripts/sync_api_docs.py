"""sync_api_docs.py — refresh docs/API.md endpoint index from the live OpenAPI spec.

API.md is HAND-CURATED at the top (base URL, auth, rate limits, examples). This
tool regenerates ONLY the endpoint INDEX between AUTO markers from the FastAPI
app's own `app.openapi()` — so the curated prose stays, but the route list never
drifts from code (~750 routes). The full spec stays live at `/openapi.json`.

  python scripts/sync_api_docs.py            # rewrite the index section
  python scripts/sync_api_docs.py --check     # exit 1 if API.md is out of date (CI gate)

Generates from the app in-process (no running server). Never raises (CI-safe).
Windows venv: .venv\\Scripts\\python.exe scripts/sync_api_docs.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
API_MD = ROOT / "docs" / "API.md"
START = "<!-- AUTO-OPENAPI:START -->"
END = "<!-- AUTO-OPENAPI:END -->"
_METHODS = ("get", "post", "put", "patch", "delete")


def _spec() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))  # script-by-path puts scripts/ on path, not repo root
    from app.main import app  # heavy import — only when generating

    return app.openapi()


def build_index() -> str:
    """Render the endpoint index markdown (grouped by OpenAPI tag)."""
    spec = _spec()
    paths = spec.get("paths", {}) or {}
    groups: dict[str, list[tuple[str, str, str]]] = {}
    total = 0
    for path, ops in sorted(paths.items()):
        for method, op in (ops or {}).items():
            if method.lower() not in _METHODS:
                continue
            total += 1
            tags = op.get("tags") or ["(untagged)"]
            tag = str(tags[0])
            summary = (op.get("summary") or op.get("operationId") or "").strip()
            groups.setdefault(tag, []).append((method.upper(), path, summary))

    lines: list[str] = [
        START,
        "",
        f"## Endpoint Index — auto-generated from OpenAPI ({total} operations)",
        "",
        "> Regenerate: `python scripts/sync_api_docs.py` · Full live spec: `/openapi.json` · "
        "Interactive: `/docs`. Edits between the AUTO markers are overwritten.",
        "",
    ]
    for tag in sorted(groups):
        rows = sorted(groups[tag], key=lambda r: (r[1], r[0]))
        lines.append(f"### {tag}  ({len(rows)})")
        lines.append("")
        for method, path, summary in rows:
            lines.append(f"- `{method:<6}` `{path}`" + (f" — {summary}" if summary else ""))
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def _splice(current: str, block: str) -> str:
    if START in current and END in current:
        pre = current.split(START)[0].rstrip("\n")
        post = current.split(END, 1)[1].lstrip("\n")
        return pre + "\n\n" + block + ("\n\n" + post if post else "\n")
    # markers absent — append a fresh section at the end
    return current.rstrip("\n") + "\n\n---\n\n" + block + "\n"


def main(argv: list[str]) -> int:
    try:
        block = build_index()
    except Exception as e:  # never-raise (CI-safe)
        print(f"[sync_api_docs] skipped: {type(e).__name__}: {e}")
        return 0

    current = API_MD.read_text(encoding="utf-8") if API_MD.exists() else ""
    updated = _splice(current, block)

    if "--check" in argv:
        if current.strip() != updated.strip():
            print(
                "[sync_api_docs] API.md endpoint index is OUT OF DATE — run: python scripts/sync_api_docs.py"
            )
            return 1
        print("[sync_api_docs] API.md endpoint index up to date")
        return 0

    API_MD.write_text(updated, encoding="utf-8")
    n = block.count("\n- `")
    print(f"[sync_api_docs] wrote {n} endpoints into docs/API.md (between AUTO markers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
