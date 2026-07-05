"""env_reference_sync.py — refresh docs/ENV_REFERENCE.md env-key index from code.

ENV_REFERENCE.md ke top ka prose HAND-CURATED hai (title, "values kabhi nahi"
note, .env.example pointer). Yeh tool sirf AUTO markers ke beech ka KEY INDEX
regenerate karta hai — code hi single source:

  * app/**/*.py me `os.getenv("KEY")` / `os.environ.get("KEY")` / `os.environ["KEY"]`
  * app/config.py Settings ke pydantic fields (field `foo_bar` → env FOO_BAR;
    explicit alias=/validation_alias honor hota hai)
  * app/api/automation_flags.py ka AUTOMATION_FLAGS registry
  * .env.example ke `^KEY=` lines (documentation coverage cross-check)

  python scripts/env_reference_sync.py            # rewrite the index section
  python scripts/env_reference_sync.py --check     # exit 1 if out of date (CI gate)

NAMES only — is file me KABHI koi value nahi aati (secrets sirf .env me). Never
raises on the generate path (CI-safe). Template: scripts/sync_api_docs.py.
Gap: R-10 in docs/GAP_REGISTER_2026_07_05.md.
Windows venv: .venv\\Scripts\\python.exe scripts/env_reference_sync.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_MD = ROOT / "docs" / "ENV_REFERENCE.md"
ENV_EXAMPLE = ROOT / ".env.example"
START = "<!-- AUTO-ENV:START -->"
END = "<!-- AUTO-ENV:END -->"

# os.getenv("KEY") / os.environ.get("KEY") / os.environ["KEY"] — object prefix
# ko ignore karte hain (os / _os / config etc. sab match). Names = UPPER convention.
_GETENV_RES = (
    re.compile(r"""getenv\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    re.compile(r"""environ\.get\(\s*["']([A-Z_][A-Z0-9_]*)["']"""),
    re.compile(r"""environ\[\s*["']([A-Z_][A-Z0-9_]*)["']"""),
)

# Prose OUTSIDE the markers — sirf tab likha jaata hai jab file missing ho.
HEADER = "\n".join(
    [
        "# Environment Variable Reference",
        "",
        "> **AUTO-GENERATED** — edit via `scripts/env_reference_sync.py` "
        "(`--check` = CI drift gate). Table between the AUTO markers is "
        "overwritten; prose above/below is preserved.",
        ">",
        "> Full annotated template with guidance + defaults: "
        "[`.env.example`](../.env.example). Gap tracked as **R-10** in "
        "`docs/GAP_REGISTER_2026_07_05.md`.",
        ">",
        "> **VALUES kabhi is file me nahi aate — sirf key NAMES.** Secrets sirf "
        "`.env` (gitignored) me rehte hain; yeh reference sirf batata hai *kaun "
        "si* keys code padhta hai aur `.env.example` me documented hain ya nahi.",
        "",
    ]
)


def _scan_getenv() -> dict[str, set[str]]:
    """app/**/*.py scan → {KEY: {relative source files}} for env reads."""
    out: dict[str, set[str]] = {}
    app_dir = ROOT / "app"
    if not app_dir.is_dir():
        return out
    for p in app_dir.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = p.relative_to(ROOT).as_posix()
        for rx in _GETENV_RES:
            for m in rx.finditer(text):
                out.setdefault(m.group(1), set()).add(rel)
    return out


def _settings_fields() -> set[str]:
    """Pydantic Settings ke env-key names (field UPPER; alias honor)."""
    keys: set[str] = set()
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from app.config import Settings  # light import (no app.main)

        for name, fi in Settings.model_fields.items():
            alias = getattr(fi, "alias", None) or getattr(fi, "validation_alias", None)
            env_name = alias if isinstance(alias, str) else name
            keys.add(env_name.upper())
    except Exception:
        # Fallback: regex field annotations (4-space indented `name: type`).
        try:
            src = (ROOT / "app" / "config.py").read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"^    ([a-z][a-z0-9_]*)\s*:\s*", src, re.M):
                keys.add(m.group(1).upper())
        except OSError:
            pass
    return keys


def _example_keys() -> set[str]:
    """.env.example ke `^KEY=` lines."""
    keys: set[str] = set()
    if not ENV_EXAMPLE.exists():
        return keys
    for line in ENV_EXAMPLE.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^([A-Z0-9_]+)=", line)
        if m:
            keys.add(m.group(1))
    return keys


def _flag_keys() -> set[str]:
    """AUTOMATION_FLAGS registry (import; regex fallback)."""
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from app.api.automation_flags import AUTOMATION_FLAGS

        return {str(f).upper() for f in AUTOMATION_FLAGS}
    except Exception:
        keys: set[str] = set()
        try:
            src = (
                ROOT / "app" / "api" / "automation_flags.py"
            ).read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"([A-Z_][A-Z0-9_]*)"', src):
                keys.add(m.group(1))
        except OSError:
            pass
        return keys


def build_block() -> str:
    """Render the env-key index markdown (between AUTO markers)."""
    getenv_keys = _scan_getenv()
    settings_keys = _settings_fields()
    example_keys = _example_keys()
    flag_keys = _flag_keys()

    code_keys = set(getenv_keys) | settings_keys | flag_keys
    all_keys = code_keys | example_keys
    undocumented = code_keys - example_keys  # read in code, missing from .env.example
    example_only = example_keys - code_keys  # in .env.example, never read → possibly dead

    lines: list[str] = [
        START,
        "",
        f"## Env Key Index — auto-generated ({len(all_keys)} keys)",
        "",
        "> Regenerate: `python scripts/env_reference_sync.py` · Drift-check: "
        "`--check`. Edits between the AUTO markers are overwritten. "
        "**NAMES only — koi value yahan nahi.**",
        "",
        f"- **Total keys:** {len(all_keys)}",
        f"- **Undocumented in `.env.example`** (code me read, example me nahi): "
        f"{len(undocumented)}",
        f"- **Example-only** (`.env.example` me hai, code me kahin read nahi — "
        f"possibly dead): {len(example_only)}",
        "",
        "| KEY | read-via | in .env.example? | in flags registry? | source files |",
        "| --- | --- | --- | --- | --- |",
    ]
    for key in sorted(all_keys):
        in_getenv = key in getenv_keys
        in_settings = key in settings_keys
        if in_getenv and in_settings:
            via = "both"
        elif in_getenv:
            via = "getenv"
        elif in_settings:
            via = "settings"
        else:
            via = "-"
        srcs = set(getenv_keys.get(key, set()))
        if in_settings:
            srcs.add("app/config.py")
        src_cell = ", ".join(sorted(srcs)[:3]) or "-"
        in_ex = "yes" if key in example_keys else "no"
        in_fl = "yes" if key in flag_keys else "no"
        lines.append(f"| `{key}` | {via} | {in_ex} | {in_fl} | {src_cell} |")
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def _splice(current: str, block: str) -> str:
    if START in current and END in current:
        pre = current.split(START)[0].rstrip("\n")
        post = current.split(END, 1)[1].lstrip("\n")
        return pre + "\n\n" + block + ("\n\n" + post if post else "\n")
    # markers absent — append a fresh section after the curated header
    return current.rstrip("\n") + "\n\n---\n\n" + block + "\n"


def main(argv: list[str]) -> int:
    try:
        block = build_block()
    except Exception as e:  # never-raise (CI-safe)
        print(f"[env_reference_sync] skipped: {type(e).__name__}: {e}")
        return 0

    current = ENV_MD.read_text(encoding="utf-8") if ENV_MD.exists() else ""
    base = current if current.strip() else HEADER  # seed curated header on first run
    updated = _splice(base, block)

    if "--check" in argv:
        if current.strip() != updated.strip():
            print(
                "[env_reference_sync] docs/ENV_REFERENCE.md is OUT OF DATE — run: "
                "python scripts/env_reference_sync.py"
            )
            return 1
        print("[env_reference_sync] docs/ENV_REFERENCE.md env key index up to date")
        return 0

    ENV_MD.write_text(updated, encoding="utf-8")
    n = block.count("\n| `")
    print(f"[env_reference_sync] wrote {n} env keys into docs/ENV_REFERENCE.md (between AUTO markers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
