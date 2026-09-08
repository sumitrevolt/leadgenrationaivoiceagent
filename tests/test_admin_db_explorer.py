"""Tests for the read-only Admin DB Explorer (app/api/admin_db_explorer.py).

Council 2026-06-25 decision: Supabase-Studio alternative on OUR Postgres.
Risk surface = redaction + SQL-injection-safety + flag gate → tested here with an
in-memory sqlite schema (no dependency on the project DB).
"""

from __future__ import annotations

import datetime
import decimal
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

import app.api.admin_db_explorer as dbx


@pytest.fixture()
def fake_engine(monkeypatch):
    # StaticPool → ek hi shared in-memory connection (warna har connect = naya DB).
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as c:
        c.execute(
            text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, "
                "password_hash TEXT, api_key TEXT, created_at TEXT)"
            )
        )
        c.execute(
            text(
                "INSERT INTO users (name, password_hash, api_key, created_at) "
                "VALUES ('Asha','secrethash','sk_live_123','2026-06-25')"
            )
        )
        c.execute(
            text(
                "INSERT INTO users (name, password_hash, api_key, created_at) "
                "VALUES ('Ravi','h2','sk_live_456','2026-06-24')"
            )
        )
    monkeypatch.setattr(dbx, "_engine", lambda: eng)
    return eng


def test_import_safe():
    assert dbx.router is not None
    assert dbx.router.prefix == "/api/admin/db"


def test_is_sensitive():
    for col in [
        "password",
        "password_hash",
        "api_key",
        "apikey",
        "auth_token",
        "jwt_secret",
        "totp_secret",
        "webhook_signing",
        "private_key",
        "dsn",
    ]:
        assert dbx._is_sensitive(col), col
    for col in ["id", "name", "email", "created_at", "business_name", "phone", "niche"]:
        assert not dbx._is_sensitive(col), col


def test_jsonable():
    assert dbx._jsonable(None) is None
    assert dbx._jsonable("x") == "x"
    assert dbx._jsonable(5) == 5
    assert dbx._jsonable(True) is True
    assert dbx._jsonable(decimal.Decimal("1.5")) == 1.5
    assert dbx._jsonable(b"abc").startswith("<binary")
    iso = dbx._jsonable(datetime.datetime(2026, 6, 25, 1, 2, 3))
    assert iso.startswith("2026-06-25")
    u = uuid.uuid4()
    assert dbx._jsonable(u) == str(u)


def test_enabled_and_guard(monkeypatch):
    monkeypatch.delenv("ADMIN_DB_EXPLORER", raising=False)
    assert dbx._enabled() is False
    with pytest.raises(Exception):
        dbx._guard()
    monkeypatch.setenv("ADMIN_DB_EXPLORER", "1")
    assert dbx._enabled() is True
    dbx._guard()  # should not raise


def test_list_tables(fake_engine):
    res = dbx._list_tables()
    assert res["available"] is True
    names = [t["table"] for t in res["tables"]]
    assert "users" in names


def test_read_table_redacts(fake_engine):
    res = dbx._read_table("users", 10, 0, "id", False, True)
    assert res.get("status") is None
    assert res["total"] == 2
    assert "password_hash" in res["sensitive"]
    assert "api_key" in res["sensitive"]
    first = res["rows"][0]
    assert first["password_hash"] == "***redacted***"
    assert first["api_key"] == "***redacted***"
    assert first["name"] in ("Asha", "Ravi")
    assert res["read_only"] is True


def test_read_table_unknown_returns_404(fake_engine):
    res = dbx._read_table("nonexistent_table", 10, 0, None, True, True)
    assert res.get("status") == 404


def test_read_table_injection_safe(fake_engine):
    # Malicious table name not in introspection list → 404, never executed.
    res = dbx._read_table("users; DROP TABLE users", 10, 0, None, True, False)
    assert res.get("status") == 404
    # Bad order_by column ignored (not in col list) → query still safe.
    res2 = dbx._read_table("users", 10, 0, "id; DROP TABLE users", False, False)
    assert res2.get("status") is None
    # Table must still exist (no drop happened).
    res3 = dbx._read_table("users", 10, 0, None, True, True)
    assert res3["total"] == 2


def test_export_csv_redacts(fake_engine):
    res = dbx._export_csv("users", 100, "id", False)
    assert "csv" in res
    assert "password_hash" in res["csv"]  # column header present
    assert "***redacted***" in res["csv"]  # secret value redacted
    assert "secrethash" not in res["csv"]  # real secret NOT leaked
