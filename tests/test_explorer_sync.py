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


def test_files_refs_resolve():
    """Reverse-sync gate: every explicit `files:'x.py'` claim must be a real file."""
    html = es.EXPLORER.read_text(encoding="utf-8")
    missing = es.files_ref_audit(html)
    assert not missing, f"explorer `files:` refs not on disk: {missing}"


def test_explorer_sync_check_exit_zero():
    assert es.main(["--check"]) == 0


def test_plugins_tab_is_shareable_url():
    html = es.EXPLORER.read_text(encoding="utf-8")
    assert "params.get('tab')" in html
    assert "showPluginsPanel" in html
    assert "SB_TABS" in html


def test_live_sync_keeps_public_health_independent_from_admin_overlays():
    """An optional admin fetch/render failure must not become 'API unreachable'."""
    html = es.EXPLORER.read_text(encoding="utf-8")
    assert "const [healthR, summaryR] = await Promise.all([" in html
    assert "const adminRes = await Promise.allSettled([" in html
    assert "try { renderNodes(); } catch(e) {}" in html
