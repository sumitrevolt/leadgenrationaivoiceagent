"""Durable-memory write boundary — inventory conformance + bypass tests.

Review P1: guarding the facade is not enough. Anything that can persist agent
memory must enforce governance ITSELF, because callers can (and do) reach the
underlying writers directly. This suite:

  1. validates `docs/memory/DURABLE_WRITERS.json` against the real code, and
  2. calls each PUBLIC writer directly (bypassing memory_stack) with the
     do-not-remember authority damaged, proving each one refuses on its own.

If someone later adds a durable memory writer without a guard or an inventory
entry, (1) fails — that is the point.
"""

from __future__ import annotations

import asyncio
import importlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.prospective_memory import ProspectiveMemory

INVENTORY = Path("docs/memory/DURABLE_WRITERS.json")
GUARD_SYMBOLS = ("durable_writes_allowed", "guard_durable_write", "_write_decision", "check_write")


@pytest.fixture()
def broken_governance(tmp_path, monkeypatch):
    """DNR authority present but unreadable/corrupt + memory stack armed."""
    rules = tmp_path / "supp.jsonl"
    rules.write_text("{not json\n", encoding="utf-8")
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(rules))
    monkeypatch.setenv("MEMORY_GOVERNANCE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    monkeypatch.setenv("AGENT_MEMORY", "1")
    monkeypatch.setenv("WORKFORCE_MEMORY", "1")
    monkeypatch.setenv("WORKFORCE_MEMORY_DIR", str(tmp_path / "wfm"))
    monkeypatch.setenv("MEMORY_VAULT", "1")
    monkeypatch.setenv("AGENT_RECALL", "1")
    yield tmp_path


@pytest.fixture()
def prospective_store_wired(tmp_path, monkeypatch):
    """Give the L6 store a real (isolated) table so the test reaches the
    governance gate instead of short-circuiting on `available()`."""
    ps = importlib.import_module("app.platform.prospective_store")
    engine = create_engine(f"sqlite:///{tmp_path / 'prospective.db'}", future=True)
    ProspectiveMemory.__table__.create(bind=engine, checkfirst=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def _session():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr(ps, "_models", lambda: (ProspectiveMemory, _session))
    yield ps
    engine.dispose()


def _inventory() -> dict:
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


# ------------------------------------------------------- inventory conformance


def test_inventory_exists_and_is_wellformed():
    inv = _inventory()
    assert inv["writers"], "inventory must not be empty"
    required = {
        "layer",
        "file",
        "symbol",
        "storage_authority",
        "public_callers",
        "governance_guard",
        "tenant_scope",
        "result_behavior",
    }
    for w in inv["writers"]:
        assert required <= set(w), f"missing fields for {w.get('file')}"


def test_every_inventoried_writer_exists_and_is_guarded():
    for w in _inventory()["writers"]:
        path = Path(w["file"])
        assert path.exists(), f"inventory points at a missing file: {path}"
        src = path.read_text(encoding="utf-8")
        assert f"def {w['symbol']}" in src, f"{w['symbol']} not found in {path}"
        if w["governance_guard"] == "NOT_GUARDED_BY_DESIGN":
            # an exclusion must justify itself in the same record
            assert len(w["result_behavior"]) > 60
            continue
        assert any(g in src for g in GUARD_SYMBOLS), f"{path} has no governance guard"


def test_no_unlisted_memory_writer_module_is_unguarded():
    """Heuristic sweep: known memory modules must be listed or excluded."""
    inv = _inventory()
    listed = {w["file"] for w in inv["writers"]} | {e["file"] for e in inv["explicit_exclusions"]}
    candidates = [
        "app/platform/memory_stack.py",
        "app/platform/prospective_store.py",
        "app/platform/workforce_memory.py",
        "app/platform/memory_vault.py",
        "app/platform/skill_library.py",
        "app/agents/agent_recall.py",
        "app/voice_agent/agent_memory.py",
        "app/voice_agent/knowledge_base.py",
        "app/ml/vector_store.py",
    ]
    missing = [c for c in candidates if Path(c).exists() and c not in listed]
    assert not missing, f"memory modules missing from the inventory: {missing}"


# ------------------------------------------------- direct (bypass) enforcement


def test_prospective_store_refuses_directly(broken_governance, prospective_store_wired):
    ps = prospective_store_wired
    out = ps.enqueue("tenantA", "rohan", "remember card 4111111111111111", in_minutes=5)
    assert out["ok"] is False and out.get("deferred") is True
    assert "4111111111111111" not in json.dumps(out)


def test_workforce_memory_refuses_directly(broken_governance):
    wm = importlib.import_module("app.platform.workforce_memory")
    out = wm.remember("swara", "lead card 4111111111111111")
    assert out["ok"] is False and out.get("deferred") is True
    assert "4111111111111111" not in json.dumps(out)


def test_episodic_memory_refuses_directly(broken_governance):
    am = importlib.import_module("app.voice_agent.agent_memory")
    out = asyncio.get_event_loop().run_until_complete(
        am.remember("lead-1", [{"role": "user", "content": "card 4111111111111111"}])
    )
    assert out["stored"] == 0 and out.get("deferred") is True


def test_skill_library_refuses_directly(broken_governance):
    sl = importlib.import_module("app.platform.skill_library")
    out = sl.record_lesson("outreach", "lead 9876543210 prefers evenings")
    assert out["ok"] is False and out.get("deferred") is True


def test_agent_recall_refuses_directly(broken_governance):
    ar = importlib.import_module("app.agents.agent_recall")
    out = ar.record("decision", "we called 9876543210 today")
    assert out["ok"] is False and out.get("deferred") is True


async def test_background_promotion_path_refuses(broken_governance):
    mv = importlib.import_module("app.platform.memory_vault")
    out = await mv.sync_if_enabled()
    assert out["ok"] is False and out.get("deferred") is True


def test_outage_creates_no_suppression_audit_and_no_deletion(broken_governance, tmp_path):
    """An outage is not a suppression: no matched_hash, and no destructive forget."""
    gov = importlib.import_module("app.platform.memory_governance")

    decision = gov.check_write("tenantA", text="lead 9876543210 said yes")
    assert decision["decision"] == gov.DECISION_DEFERRED
    assert decision["code"] == gov.DEFER_CODE

    forgotten = gov.forget("tenantA")
    assert forgotten["ok"] is False and forgotten.get("deferred") is True

    audit_file = tmp_path / "audit.jsonl"
    blob = audit_file.read_text(encoding="utf-8") if audit_file.exists() else ""
    assert "matched_hash" not in blob or '"matched_hash": ""' in blob
    assert "9876543210" not in blob


def test_healthy_governance_still_allows_and_rules_still_suppress(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(tmp_path / "supp.jsonl"))
    monkeypatch.setenv("MEMORY_GOVERNANCE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("MEMORY_STACK_ENABLED", "1")
    gov = importlib.import_module("app.platform.memory_governance")

    assert gov.check_write("tenantA", text="normal note")["decision"] == gov.DECISION_ALLOW
    gov.suppress("tenantA", "pattern", r"credit\s*card")
    d = gov.check_write("tenantA", text="my credit card")
    assert d["decision"] == gov.DECISION_SUPPRESSED
    assert d["code"] == "MEMORY_WRITE_SUPPRESSED_BY_RULE"


def test_flag_off_keeps_every_lane_on_the_legacy_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_SUPPRESSION_PATH", str(tmp_path / "supp.jsonl"))
    (tmp_path / "supp.jsonl").write_text("{not json\n", encoding="utf-8")
    monkeypatch.delenv("MEMORY_STACK_ENABLED", raising=False)
    gov = importlib.import_module("app.platform.memory_governance")

    assert gov.durable_writes_allowed()["ok"] is True
    assert gov.guard_durable_write("tenantA", text="x")["decision"] == gov.DECISION_ALLOW
