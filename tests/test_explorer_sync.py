"""Explorer graph ↔ codebase drift + connection health gate."""

from __future__ import annotations

from scripts import explorer_sync as es


def test_engine_modules_on_graph():
    a = es.audit()
    assert not a["miss_mods"], f"missing engine modules: {a['miss_mods']}"


def test_no_orphan_nodes_or_dangling_edges():
    html = es.EXPLORER.read_text(encoding="utf-8")
    ea = es.edge_audit(html)
    for view, r in ea.items():
        assert not r["dangling"], f"{view} dangling: {r['dangling']}"
        assert not r["orphans"], f"{view} orphans: {r['orphans']}"


def test_explorer_sync_check_exit_zero():
    assert es.main(["--check"]) == 0
