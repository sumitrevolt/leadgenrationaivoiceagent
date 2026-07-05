"""data_store_inventory.py — build docs/DATA_STORES.md registry of gitignored data stores.

The app persists a LOT of state in gitignored ``data/*.jsonl`` / ``*.json`` / ``*.db`` /
``*.csv`` files that act as mini-databases (append-only ledgers, config toggles, caches —
plus PII/auth stores). There was NO registry (GAP R-17). This tool scans the source for
every code-referenced data store and regenerates ONLY the table between AUTO markers, so
the curated header prose stays but the inventory never drifts from code.

  python scripts/data_store_inventory.py            # rewrite the inventory table
  python scripts/data_store_inventory.py --check     # exit 1 if DATA_STORES.md is out of date (CI-safe)

stdlib-only, generates by scanning source text (no app import). Never raises (CI-safe).
Windows venv: .venv\\Scripts\\python.exe scripts/data_store_inventory.py

Migration is NOT this tool's job: jsonl->Postgres = migrate-when-volume (ADR / GAP R-33).
Retention / DPDP rules = data-retention-dpdp skill. Ye file sirf REGISTRY hai.
"""
from __future__ import annotations

import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "DATA_STORES.md"
START = "<!-- AUTO-DATASTORES:START -->"
END = "<!-- AUTO-DATASTORES:END -->"
SELF = pathlib.Path(__file__).resolve()

_EXTS = ("jsonl", "json", "db", "csv")

# A `data/...` path written as a standalone string literal (the quote must sit
# immediately before `data/` so prose/docstring mentions are NOT captured).
_QUOTED = re.compile(r"""["']data/([A-Za-z0-9_\-/{}.%:]+\.(?:jsonl|json|db|csv))["']""")
# Path("data") / "seg" [/ "seg" ...] chains — grab the trailing segment run.
_PATHJOIN = re.compile(r"""Path\(\s*["']data["']\s*\)((?:\s*/\s*["'][^"'/]+["'])+)""")
# os.path.join("data", "seg" [, ...]) — grab the segment args.
_OSJOIN = re.compile(r"""os\.path\.join\(\s*["']data["']\s*((?:,\s*["'][^"',]+["'])+)""")
_SEG = re.compile(r"""["']([^"']+)["']""")

# PII / compliance name-patterns → treat store as regulated data.
_PII = re.compile(
    r"consent|auth|totp|dpdp|customer|client_api_keys|recording|call_log|"
    r"transcript|lead|prospect",
    re.I,
)

# Filename-building patterns inside a file → infer the shard extension of a
# directory store (cheap; ignores unrelated `.json` imports).
_DIR_EXT = [
    re.compile(r"""\.glob\(\s*["']\*\.(jsonl|json|db|csv)"""),
    re.compile(r"""endswith\(\s*["']\.(jsonl|json|db|csv)"""),
    re.compile(r"""\+\s*["']\.(jsonl|json|db|csv)"""),
    re.compile(r"""f["'][^"']*\}\.(jsonl|json|db|csv)"""),
]


def iter_source_files():
    """Every tracked .py under app/ and scripts/ (skip __pycache__ + this script)."""
    for d in ("app", "scripts"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if "__pycache__" in p.parts or p.resolve() == SELF:
                continue
            yield p


def _module(p: pathlib.Path) -> str:
    """app/marketing/crm_lite.py -> app.marketing.crm_lite"""
    return p.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")


def _normalize(tail: str) -> str:
    """Collapse date-shard / f-string-brace variants into one canonical tail."""
    # f-string braces: {date:%Y-%m-%d} / {client_id} -> <date> / <client_id>
    def _brace(m: re.Match) -> str:
        name = m.group(1).strip().lower()
        return "<date>" if name in {"date", "day", "today", "ymd", "dt", "ts", "now"} else f"<{m.group(1).strip()}>"

    tail = re.sub(r"\{([^}:]+)(?::[^}]*)?\}", _brace, tail)
    # strftime runs: %Y-%m-%d -> <date>
    tail = re.sub(r"(?:%[-#0-9]*[A-Za-z][-_:./]?)+", "<date>", tail)
    # literal placeholders: YYYY-MM-DD / YYYYMMDD / YYYY -> <date>
    tail = re.sub(r"YYYY[-_]?(?:MM(?:[-_]?DD)?)?", "<date>", tail)
    # collapse adjacent <date> tokens
    tail = re.sub(r"<date>(?:[-_:]?<date>)+", "<date>", tail)
    return tail


def _classify(path: str) -> tuple[bool, str]:
    """(pii_likely, best-guess class for non-PII stores)."""
    if _PII.search(path):
        return True, "pii"
    n = path.lower()
    if any(k in n for k in ("cache", "cursor", "_state", "state.", "heartbeat", "baseline", "seen", "dnd")):
        return False, "cache"
    if any(k in n for k in ("config", "override", "settings", "_mode", "template", "packages", "pricing", "keys")):
        return False, "config"
    return False, "state"


def _dir_ext(txt: str):
    for rx in _DIR_EXT:
        m = rx.search(txt)
        if m:
            return m.group(1)
    return None


def scan() -> tuple[dict, int]:
    """Return {canonical_path: {ext, is_dir, pii, klass, refs:Counter}} and files-scanned count."""
    stores: dict[str, dict] = {}
    n_files = 0

    def _add(key: str, ext: str, module: str, is_dir: bool = False) -> None:
        pii, klass = _classify(key)
        s = stores.setdefault(key, {"ext": ext, "is_dir": is_dir, "pii": pii, "klass": klass, "refs": Counter()})
        # prefer a concrete extension over "dir" if any reference resolves one
        if s["ext"] == "dir" and ext != "dir":
            s["ext"] = ext
        s["refs"][module] += 1

    for p in iter_source_files():
        n_files += 1
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        module = _module(p)

        for m in _QUOTED.finditer(txt):
            tail = _normalize(m.group(1))
            ext = tail.rsplit(".", 1)[-1].lower()
            _add("data/" + tail, ext, module)

        # Directory stores keyed canonically as `data/<dir>/` so refs from
        # different files (some ext-inferable, some not) merge into ONE row.
        file_dir_keys: set[str] = set()
        for m in list(_PATHJOIN.finditer(txt)) + list(_OSJOIN.finditer(txt)):
            segs = _SEG.findall(m.group(1))
            if not segs:
                continue
            joined = "/".join(segs)
            last = segs[-1]
            if "." in last:
                # dotted filename — only in scope if it's one of our 4 extensions
                # (skip .txt/.wav/.png/.lock etc.)
                if last.rsplit(".", 1)[-1].lower() in _EXTS:
                    tail = _normalize(joined)
                    _add("data/" + tail, tail.rsplit(".", 1)[-1].lower(), module)
            else:
                # pure directory name → sharded store (data/<dir>/...)
                file_dir_keys.add("data/" + _normalize(joined) + "/")

        # Infer the shard extension ONLY when a file references exactly one
        # directory store — otherwise a stray `.jsonl` in a big multi-store file
        # (e.g. vobiz_stream mixing .wav recordings + .jsonl transcripts) would
        # mislabel a store. Ambiguous refs stay `dir` but still merge by key.
        inferred = _dir_ext(txt) if len(file_dir_keys) == 1 else None
        for key in file_dir_keys:
            _add(key, inferred or "dir", module, is_dir=True)

    return stores, n_files


def _refs_cell(refs: Counter) -> str:
    ordered = sorted(refs.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [m for m, _ in ordered[:3]]
    cell = ", ".join(f"`{m}`" for m in top)
    if len(ordered) > 3:
        cell += f" +{len(ordered) - 3}"
    return cell


def build_index() -> str:
    """Render the inventory table markdown (between AUTO markers)."""
    stores, n_files = scan()
    total = len(stores)
    pii_n = sum(1 for s in stores.values() if s["pii"])

    lines: list[str] = [
        START,
        "",
        f"## Inventory — auto-generated ({total} stores, {pii_n} PII-likely; scanned {n_files} source files)",
        "",
        "> Regenerate: `python scripts/data_store_inventory.py`. Edits between AUTO markers are overwritten.",
        "> `PII-likely?`: `⚠️ yes` = path name matches a compliance pattern "
        "(consent/auth/totp/dpdp/customer/lead/recording/transcript/prospect/client_api_keys) → "
        "treat as regulated data. Non-PII rows show best-guess class (`state`/`config`/`cache`). "
        "`notes` intentionally blank for owner annotation.",
        "",
        "| path | type | PII-likely? | referenced-by (top 3 modules) | notes |",
        "|---|---|---|---|---|",
    ]
    # PII stores float to the top, then alphabetical by path.
    for key in sorted(stores, key=lambda k: (not stores[k]["pii"], k)):
        s = stores[key]
        if s["is_dir"] and s["ext"] != "dir":
            display, typ = key.rstrip("/") + "/<shard>." + s["ext"], s["ext"]
        else:
            display, typ = key, s["ext"]
        flag = "⚠️ yes" if s["pii"] else s["klass"]
        lines.append(f"| `{display}` | {typ} | {flag} | {_refs_cell(s['refs'])} | |")
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


HEADER = """# Data Stores Registry (jsonl / json / db / csv mini-databases)

**Purpose:** The app persists a lot of state in gitignored `data/*.jsonl` / `*.json` / `*.db` /
`*.csv` files that behave as mini-databases (append-only ledgers, config toggles, caches — plus
PII/auth stores). There was **no registry** (GAP `R-17`). This file is that registry: one place to
see every code-referenced data store, whether it looks PII/compliance-sensitive, and which modules
own it.

**AUTO-GENERATED via `scripts/data_store_inventory.py`** — edits between the AUTO markers are
overwritten. Regenerate: `python scripts/data_store_inventory.py` · drift-check (CI-safe):
`python scripts/data_store_inventory.py --check`.

**Policy (NOT this file's job):** jsonl → Postgres migration = *migrate-when-volume* (ADR; see
`docs/GAP_REGISTER_2026_07_05.md` **R-33**, PARKED). Retention / DPDP purge rules live in the
`data-retention-dpdp` skill. **Ye file sirf REGISTRY hai** — schema/owner/retention ko yahan track
karo, migration nahi.

**Gaps:** `R-17` (build this inventory) · `R-33` (jsonl→Postgres, deferred) — `docs/GAP_REGISTER_2026_07_05.md`.

**Placeholder convention:** `<date>` = per-day partition (e.g. `%Y-%m-%d`) · `<shard>` =
per-id/per-day file inside a directory store · `<client_id>` etc. = f-string key. Date/shard-sharded
references are collapsed to one row. `type = dir` = directory store whose file extension couldn't be
inferred cheaply (may hold non-jsonl payloads such as `.wav` recordings).
"""


def _splice(current: str, block: str) -> str:
    if START in current and END in current:
        pre = current.split(START)[0].rstrip("\n")
        post = current.split(END, 1)[1].lstrip("\n")
        return pre + "\n\n" + block + ("\n\n" + post if post else "\n")
    return current.rstrip("\n") + "\n\n" + block + "\n"


def main(argv: list[str]) -> int:
    try:
        block = build_index()
    except Exception as e:  # never-raise (CI-safe)
        print(f"[data_store_inventory] skipped: {type(e).__name__}: {e}")
        return 0

    current = DOC.read_text(encoding="utf-8") if DOC.exists() else HEADER
    updated = _splice(current, block)

    if "--check" in argv:
        if not DOC.exists() or current.strip() != updated.strip():
            print("[data_store_inventory] DATA_STORES.md is OUT OF DATE — run: python scripts/data_store_inventory.py")
            return 1
        print("[data_store_inventory] DATA_STORES.md up to date")
        return 0

    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(updated, encoding="utf-8")
    n = block.count("\n| `")
    print(f"[data_store_inventory] wrote {n} stores into docs/DATA_STORES.md (between AUTO markers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
