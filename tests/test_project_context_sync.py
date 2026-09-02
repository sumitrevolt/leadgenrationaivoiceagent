"""Contract tests for the persistent project-context layer (scripts/*context*).

Guards the three properties the layer promises: idempotent, secret-safe, and
degrades. Pure-stdlib — runs without the full app import.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import project_context as pc  # noqa: E402
import query_project_context as qc  # noqa: E402
import context_health as ch  # noqa: E402
import sync_project_context as sync  # noqa: E402


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #
def test_build_is_deterministic():
    a = pc.build_store()
    b = pc.build_store()
    assert a["meta"]["content_hash"] == b["meta"]["content_hash"]
    assert a["nodes"] == b["nodes"]
    assert a["edges"] == b["edges"]


def test_write_then_second_write_is_skipped(tmp_path):
    store = pc.build_store()
    sp = tmp_path / "ctx.json"
    snap = tmp_path / "snap.md"
    assert pc.write_store(store, sp, snap) is True  # first write happens
    assert sp.is_file() and snap.is_file()
    store2 = pc.build_store()
    assert pc.write_store(store2, sp, snap) is False  # unchanged -> skip


def test_dry_run_writes_nothing(tmp_path):
    sp = tmp_path / "ctx.json"
    rc = sync.main(["--dry-run", "--store", str(sp), "--snapshot", str(tmp_path / "s.md")])
    assert rc == 0
    assert not sp.exists()


# --------------------------------------------------------------------------- #
# Secret safety
# --------------------------------------------------------------------------- #
def test_redact_masks_common_secret_shapes():
    samples = [
        "sk-ABCDEF0123456789ABCDEF",  # nosecret — synthetic fixture, not a real key
        "AKIAIOSFODNN7EXAMPLE",  # nosecret — synthetic fixture
        "AIzaSyD-abc123_ABC456def789ghiJKL012mno",  # nosecret — synthetic fixture
        "ghp_ABCDEFabcdef0123456789ABCDEFabcdef01",  # nosecret — synthetic fixture
        "MISTRAL_API_KEY=abcdef0123456789xyz",  # nosecret — synthetic fixture
    ]
    for s in samples:
        assert pc._REDACTED in pc.redact(s), s


def test_store_contains_no_raw_secrets():
    store = pc.build_store()
    blob = json.dumps(store)
    forbidden = [
        re.compile(r"sk-[A-Za-z0-9]{16,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
        re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    ]
    for pat in forbidden:
        assert not pat.search(blob), f"raw secret shape leaked: {pat.pattern}"


def test_never_ingests_env_files():
    store = pc.build_store()
    for n in store["nodes"]:
        assert not n["source"].lower().startswith(".env"), n["source"]
    assert pc.read_text_safe(ROOT / ".env") == ""  # refuses .env even if present


# --------------------------------------------------------------------------- #
# Schema / relationships (the graph the prompt asked for)
# --------------------------------------------------------------------------- #
def test_expected_node_types_present():
    store = pc.build_store()
    types = {n["type"] for n in store["nodes"]}
    for expected in ("Project", "FeatureFlag", "ApiRoute", "Test"):
        assert expected in types, f"missing node type {expected}"


def test_belongs_to_project_edges_exist():
    store = pc.build_store()
    rels = {e["rel"] for e in store["edges"]}
    assert "BELONGS_TO_PROJECT" in rels
    # every node carries provenance
    for n in store["nodes"]:
        assert n["source"] and n["verified_sha"]


# --------------------------------------------------------------------------- #
# Query is bounded + health degrades safely
# --------------------------------------------------------------------------- #
def test_query_is_bounded():
    store = pc.build_store()
    hits = qc.query(store, "unity office flag", k=5)
    assert len(hits) <= 5


def test_health_check_runs_without_crash():
    r = ch.check()
    assert set(r) == {"graphify_binary", "code_graph", "project_context", "memory_fallback"}
    for v in r.values():
        assert "ok" in v and "detail" in v
