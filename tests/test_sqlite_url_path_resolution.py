"""Regression tests for the sqlite URL path resolution in app/models/base.py.

Background (2026-09-25 CI failure, `Pytest Tests` on main b5d806fe):
`tests/test_dev_control_plane.py::test_create_task_record_is_idempotent` failed
under `pytest -n auto` with

    sqlite3.OperationalError: unable to open database file
    engine = Engine(sqlite:////home/runner/work/.../tmp/leadgen_test_gw1.db)

tests/conftest.py builds a per-worker URL from tempfile.gettempdir(), i.e.
`sqlite+aiosqlite:////tmp/leadgen_test_gw1.db` on Linux. The sync-engine
resolver used to strip the leading "/" and rebase the result onto the cwd, so an
ABSOLUTE path silently became `<cwd>/tmp/...`. A fresh checkout has no `tmp/`
directory, so sqlite could not create the file. Windows never showed it because
`C:/...` has no leading slash to strip — the bug was Linux/CI-only.

These tests pin the three URL shapes the resolver must distinguish. They assert
on the pure resolution rule, so they run on any platform and never touch a real
database.
"""

from __future__ import annotations

import os
import re
import textwrap
from pathlib import Path

import pytest

BASE_PY = Path(__file__).resolve().parents[1] / "app" / "models" / "base.py"


def _resolve(sync_url: str, cwd: str) -> str:
    """Run the REAL resolution block lifted out of app/models/base.py.

    The block is executed rather than reimplemented so the test cannot drift away
    from production behaviour. It is lifted by locating the comments that
    already bracket it, so a refactor of surrounding code does not break the test
    as long as the rule itself stays.
    """
    src = BASE_PY.read_text(encoding="utf-8")
    start = src.index("            # Ensure relative paths")
    end = src.index("            # Sync engine = migrations")
    block = textwrap.dedent("\n".join(line[12:] for line in src[start:end].splitlines()))
    ns: dict[str, object] = {"sync_url": sync_url}
    old_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        exec(compile(block, str(BASE_PY), "exec"), ns)  # noqa: S102
    finally:
        os.chdir(old_cwd)
    return str(ns["sync_url"])


def _path_of(url: str) -> str:
    assert url.startswith("sqlite:///")
    return url[len("sqlite:///") :]


@pytest.fixture
def fake_cwd(tmp_path: Path) -> Path:
    """A cwd with no `tmp/` subdirectory — mirrors a fresh git checkout."""
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.mark.skipif(os.name == "nt", reason="POSIX absolute-path semantics; CI is Linux")
def test_posix_absolute_url_is_not_rebased_onto_cwd(fake_cwd: Path) -> None:
    """THE CI BUG: sqlite:////tmp/x.db must stay /tmp/x.db, not <cwd>/tmp/x.db."""
    resolved = _path_of(_resolve("sqlite:////tmp/leadgen_test_gw1.db", str(fake_cwd)))
    assert resolved == "/tmp/leadgen_test_gw1.db", (
        "absolute sqlite URL was rebased onto the cwd; a fresh checkout has no "
        "tmp/ dir so sqlite raises 'unable to open database file'"
    )


def test_relative_url_is_still_rebased_onto_cwd(fake_cwd: Path) -> None:
    """Relative URLs keep their documented behaviour: resolved against cwd."""
    resolved = _path_of(_resolve("sqlite:///data/leadgen.db", str(fake_cwd)))
    assert resolved == str(fake_cwd / "data" / "leadgen.db")
    assert os.path.isabs(resolved)


@pytest.mark.skipif(os.name != "nt", reason="Windows absolute-path semantics")
def test_windows_absolute_url_is_not_rebased_onto_cwd(fake_cwd: Path) -> None:
    """`sqlite:///C:/Temp/x.db` is already absolute and must be left alone."""
    resolved = _path_of(_resolve("sqlite:///C:/Temp/x.db", str(fake_cwd)))
    assert resolved.lower().startswith("c:/temp/x.db")


def test_non_sqlite_urls_are_untouched(fake_cwd: Path) -> None:
    """Postgres (and any other driver) must pass through byte-identical."""
    pg = "postgresql+psycopg2://user:pw@db:5432/leadgen"
    assert _resolve(pg, str(fake_cwd)) == pg


def test_resolver_does_not_strip_leading_slash() -> None:
    """Guards the exact regression: no unconditional lstrip of the path.

    Asserts on the source text so the bug cannot return via a re-introduced
    `rel_path[1:]`-style strip even if some future edit keeps the tests green.
    """
    src = BASE_PY.read_text(encoding="utf-8")
    block = src[src.index("            # Ensure relative paths") :]
    assert not re.search(r"rel_path\s*=\s*rel_path\[1:\]", block), (
        "leading-slash strip reintroduced — that is what broke absolute sqlite URLs"
    )
