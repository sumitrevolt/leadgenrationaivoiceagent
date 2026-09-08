"""Tests for the DPDP privacy module (app/platform/dpdp.py).

Offline + isolated: koi network/DB nahi (include_db=False). File-stores
tmp_path pe monkeypatch. Style: tests/test_parity_conversion.py jaisa.
"""

import asyncio
import json
import os


# --------------------------------------------------------------------------- #
# helpers — har test apne tmp stores pe chalta hai
# --------------------------------------------------------------------------- #
def _patch_stores(tmp_path, monkeypatch):
    from app.platform import dpdp

    stores = {
        "inquiries": str(tmp_path / "inquiries.jsonl"),
        "prospects": str(tmp_path / "prospects.jsonl"),
        "widget_chats": str(tmp_path / "widget_chats.jsonl"),
    }
    monkeypatch.setattr(dpdp, "_STORES", stores)
    monkeypatch.setattr(dpdp, "_CRM_DIR", str(tmp_path / "crm"))
    monkeypatch.setattr(dpdp, "_AUDIT_FILE", lambda: str(tmp_path / "dpdp_audit.jsonl"))
    monkeypatch.setattr(dpdp, "_REQUESTS_FILE", lambda: str(tmp_path / "dpdp_requests.jsonl"))
    return dpdp, stores


def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")


# --------------------------------------------------------------------------- #
# normalization + hashing
# --------------------------------------------------------------------------- #
def test_norm_and_subject_hash():
    from app.platform import dpdp

    assert dpdp._norm_phone("+91 98765-43210") == "9876543210"
    assert dpdp._norm_phone("09876543210") == "9876543210"
    assert dpdp._norm_phone("12345") == ""
    assert dpdp._norm_email(" Ravi@X.COM ") == "ravi@x.com"
    assert dpdp._norm_email("not-an-email") == ""
    # hash stable across formats + plaintext leak nahi
    h1 = dpdp.subject_hash("+919876543210", None)
    h2 = dpdp.subject_hash("98765 43210", None)
    assert h1 == h2 and len(h1) == 64
    assert "9876543210" not in h1


def test_match_formats_and_chat_text():
    from app.platform import dpdp

    # alag formats + chat text ke andar likha number bhi match
    assert dpdp._match({"phone": "+91 9876543210"}, "9876543210", "")
    assert dpdp._match({"text": "mera number 98765 43210 hai"}, "9876543210", "")
    assert dpdp._match({"from": "Ravi@X.com", "subject": "hi"}, "", "ravi@x.com")
    assert not dpdp._match({"phone": "9000000000"}, "9876543210", "")
    assert not dpdp._match({"ts": "2026-06-10T00:00:00"}, "9876543210", "")
    # defensive
    assert not dpdp._match(None, "9876543210", "")
    assert not dpdp._match({"a": 1}, "", "")


# --------------------------------------------------------------------------- #
# discovery + export
# --------------------------------------------------------------------------- #
def test_scan_and_export(tmp_path, monkeypatch):
    dpdp, stores = _patch_stores(tmp_path, monkeypatch)
    _write_jsonl(
        stores["inquiries"],
        [
            {"name": "Ravi", "phone": "+919876543210", "message": "solar"},
            {"name": "Other", "phone": "+919000000001", "message": "gym"},
        ],
    )
    _write_jsonl(stores["widget_chats"], [{"role": "user", "text": "call 9876543210"}])
    # crm sub-store bhi cover hota hai
    _write_jsonl(str(tmp_path / "crm" / "client1.jsonl"), [{"name": "Ravi", "phone": "9876543210"}])

    res = dpdp.scan_stores(phone="98765 43210")
    assert res["ok"] is True
    assert res["stores"] == {"inquiries": 1, "widget_chats": 1, "crm/client1.jsonl": 1}
    assert res["total_records"] == 3
    # preview masked — full number kahin nahi
    assert "9876543210" not in json.dumps(res["preview"])

    exp = asyncio.run(dpdp.export_subject(phone="9876543210", include_db=False))
    assert exp["ok"] is True and exp["total_records"] == 3
    assert exp["records"]["inquiries"][0]["name"] == "Ravi"  # export FULL hota hai
    # audit me sirf hash
    audit = (tmp_path / "dpdp_audit.jsonl").read_text(encoding="utf-8")
    assert "9876543210" not in audit and "export" in audit

    # bina subject = error
    assert dpdp.scan_stores()["ok"] is False
    assert asyncio.run(dpdp.export_subject(include_db=False))["ok"] is False


# --------------------------------------------------------------------------- #
# erasure — dry-run default, atomic + .bak, corrupt-line preserve
# --------------------------------------------------------------------------- #
def test_erase_dry_run_then_real(tmp_path, monkeypatch):
    dpdp, stores = _patch_stores(tmp_path, monkeypatch)
    rows = [
        {"name": "Ravi", "phone": "+919876543210"},
        "NOT-JSON-GARBAGE-LINE",
        {"name": "Other", "phone": "+919000000001"},
    ]
    _write_jsonl(stores["inquiries"], rows)
    before = (tmp_path / "inquiries.jsonl").read_text(encoding="utf-8")

    # dry run (default) — file untouched, no backup
    dry = asyncio.run(dpdp.erase_subject(phone="9876543210", include_db=False))
    assert dry["ok"] is True and dry["dry_run"] is True
    assert dry["stores"]["inquiries"]["removed"] == 1
    assert dry["total_would_remove"] == 1
    assert (tmp_path / "inquiries.jsonl").read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.bak_dpdp_*"))

    # real run — matching gone, garbage + other preserved, .bak created
    real = asyncio.run(dpdp.erase_subject(phone="9876543210", dry_run=False, include_db=False))
    assert real["ok"] is True and real["total_removed"] == 1
    assert real["stores"]["inquiries"]["removed"] == 1
    assert "backup" in real["stores"]["inquiries"]
    after = (tmp_path / "inquiries.jsonl").read_text(encoding="utf-8")
    assert "9876543210" not in after
    assert "NOT-JSON-GARBAGE-LINE" in after and "9000000001" in after
    baks = list(tmp_path.glob("inquiries.jsonl.bak_dpdp_*"))
    assert len(baks) == 1 and "9876543210" in baks[0].read_text(encoding="utf-8")
    # audit entries (dry + real), hash-only
    audit = (tmp_path / "dpdp_audit.jsonl").read_text(encoding="utf-8")
    assert "erase_dry_run" in audit and '"erase"' in audit
    assert "9876543210" not in audit


def test_erase_skips_unreadable_store(tmp_path, monkeypatch):
    dpdp, stores = _patch_stores(tmp_path, monkeypatch)
    # ek store path = DIRECTORY → open() fail → skip+report, koi crash nahi
    os.makedirs(stores["prospects"], exist_ok=True)
    _write_jsonl(stores["inquiries"], [{"phone": "9876543210"}])
    res = asyncio.run(dpdp.erase_subject(phone="9876543210", dry_run=False, include_db=False))
    assert res["ok"] is True
    assert "prospects" in res["skipped_stores"]
    assert res["total_removed"] == 1


# --------------------------------------------------------------------------- #
# request intake queue
# --------------------------------------------------------------------------- #
def test_request_intake_and_done(tmp_path, monkeypatch):
    dpdp, _ = _patch_stores(tmp_path, monkeypatch)
    bad = dpdp.record_request(phone="123")  # invalid subject
    assert bad["ok"] is False

    r1 = dpdp.record_request(phone="9876543210", req_type="erasure", note="delete karo")
    r2 = dpdp.record_request(email="ravi@x.com", req_type="weird-type")  # → access fallback
    assert r1["ok"] and r2["ok"] and r2["type"] == "access"

    pending = dpdp.list_requests(status="pending")
    assert len(pending) == 2
    assert pending[0]["id"] == r2["request_id"]  # newest first

    done = dpdp.mark_request_done(r1["request_id"], actor="sumit")
    assert done["ok"] is True
    assert len(dpdp.list_requests(status="pending")) == 1
    assert len(dpdp.list_requests(status="done")) == 1
    # repeat-done / unknown id graceful
    assert dpdp.mark_request_done(r1["request_id"])["ok"] is False
    assert dpdp.mark_request_done("nope")["ok"] is False


# --------------------------------------------------------------------------- #
# router importable (mount main session karega)
# --------------------------------------------------------------------------- #
def test_router_imports_and_routes():
    from app.api.privacy_ops import router

    paths = {r.path for r in router.routes}
    assert "/privacy/request" in paths
    assert "/privacy/requests" in paths
    assert "/privacy/find" in paths
    assert "/privacy/export" in paths
    assert "/privacy/erase" in paths
