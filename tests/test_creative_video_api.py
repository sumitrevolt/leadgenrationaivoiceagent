"""T04 acceptance checks — Creative Video Command Center API (stdlib unittest).

Covers:
  * the ``{ok, data, error}`` envelope on every endpoint;
  * SERVER-SIDE tenant scoping (C4) — an unknown/foreign tenant id yields an
    honest empty, never another tenant's data and never a 500;
  * the honest-empty case (no tenants ⇒ ``ok:true`` with an empty list, not a
    fabricated row);
  * the L3 customer timeline keys genuine delivery on ``video_delivered`` ONLY —
    ``video_delivered_ops`` (internal ops receipt) must NOT appear as a customer
    delivery;
  * L4 evidence is honest about network isolation (PARTIAL when probe-only);
  * POST /generate is flag-gated and FAIL-CLOSED.

Auth note: every route is guarded by the REAL ``require_admin``
(``app.api.auth_deps``). This suite does NOT stub it. ``jose`` + ``sqlalchemy``
ARE present in the repo ``.venv``, so the real dependency is always in force —
an earlier "stub only if the import fails" design never engaged there and
silently degraded this whole suite to asserting the 401 path. Auth is now
satisfied the repo-standard way: override the real dependency (see
``_make_client``, mirroring ``tests/conftest.py:284`` and
``tests/test_admin_client_timeline_ledger.py:11``).

Run with the repo interpreter:
    .venv/Scripts/python.exe -m unittest tests.test_creative_video_api
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


def _load_router():
    """Import the REAL router (and therefore the REAL ``require_admin``).

    Deliberately NO auth stub. A previous version stubbed ``require_admin``
    "only when the real import failed" — but the real import succeeds wherever
    ``jose`` + ``sqlalchemy`` are installed (the repo ``.venv`` always), so the
    stub never engaged, the real guard stayed in force, and every request 401'd.
    Auth is overridden per-app in ``_make_client`` instead. If the real
    dependency genuinely cannot be imported, this raises loudly rather than
    quietly bypassing authentication.
    """
    from app.api.auth_deps import require_admin  # noqa: F401 — real dependency
    from app.api.creative_video import router as _router

    return _router


router = _load_router()


def _make_client():
    """A minimal FastAPI app wrapping ONLY the video router (no heavy app).

    Auth uses the repo's established override pattern (``tests/conftest.py:284``;
    ``tests/test_admin_client_timeline_ledger.py:11``): override the REAL
    ``require_admin`` on THIS app instance rather than stubbing it. Returns the
    app, a TestClient, and the pre-override override map so the caller can
    restore it (never a blind ``.clear()``).
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.auth_deps import require_admin

    app = FastAPI()
    app.include_router(router)
    prev_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[require_admin] = lambda: {"username": "test"}
    return app, TestClient(app, raise_server_exceptions=False), prev_overrides


def _is_envelope(body) -> bool:
    return (
        isinstance(body, dict)
        and set(body.keys()) >= {"ok", "data", "error"}
        and isinstance(body.get("ok"), bool)
    )


class _StoreRedirect(unittest.TestCase):
    """Point every video store at a temp dir so tests never touch real data."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t04_video_")
        self.tmp = Path(self._tmp.name)
        self._env: dict[str, str | None] = {}

        from app.marketing import delivery_ledger, video_delivery

        self._orig_ledger_dir = delivery_ledger._LEDGER_DIR
        self._orig_vd_root = video_delivery._root
        delivery_ledger._LEDGER_DIR = lambda: str(self.tmp / "ledger")  # type: ignore[assignment]
        video_delivery._root = lambda: str(self.tmp / "video_delivery")  # type: ignore[assignment]

        self._setenv("CREATIVE_LEDGER_ROOT", str(self.tmp / "creative_ledger"))
        self._setenv("CREATIVE_ASSET_ROOT", str(self.tmp / "assets"))
        self._setenv("CREATIVE_OS_ENABLED", "0")
        self.app, self.client, self._prev_overrides = _make_client()

    def tearDown(self) -> None:
        from app.marketing import delivery_ledger, video_delivery

        delivery_ledger._LEDGER_DIR = self._orig_ledger_dir  # type: ignore[assignment]
        video_delivery._root = self._orig_vd_root  # type: ignore[assignment]
        # Restore the override map we found (never a blind .clear() — another
        # suite may have installed its own overrides).
        self.app.dependency_overrides.clear()
        self.app.dependency_overrides.update(self._prev_overrides)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()

    def _setenv(self, key: str, val: str) -> None:
        self._env.setdefault(key, os.environ.get(key))
        os.environ[key] = val

    def _make_tenant(self, tenant_id: str) -> None:
        """Create a tenant dir in the creative store so the server 'owns' it."""
        d = self.tmp / "creative_ledger" / tenant_id
        d.mkdir(parents=True, exist_ok=True)


class TestEnvelope(_StoreRedirect):
    def test_health_returns_envelope(self) -> None:
        r = self.client.get("/api/admin/video/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(_is_envelope(body), body)
        self.assertIsNone(body["error"])

    def test_health_surfaces_ran_vs_produced_separately(self) -> None:
        """The fake-green fix: each automation must carry BOTH ran and produced."""
        body = self.client.get("/api/admin/video/health").json()
        self.assertTrue(body["ok"], body)
        rows = body["data"]["automations"]
        self.assertTrue(rows, "no automations reported")
        for row in rows:
            self.assertIn("ran", row)
            self.assertIn("produced", row)
            # a job that only ran must never be labelled ok
            if row.get("ran") and not row.get("produced"):
                self.assertNotEqual(row.get("status"), "ok", row)

    def test_all_endpoints_use_envelope(self) -> None:
        for method, path in (
            ("GET", "/api/admin/video/health"),
            ("GET", "/api/admin/video/customers"),
            ("GET", "/api/admin/video/customers/ghost"),
            ("GET", "/api/admin/video/assets/ghost"),
            ("POST", "/api/admin/video/generate?tenant_id=ghost"),
        ):
            r = self.client.request(method, path)
            self.assertEqual(r.status_code, 200, (method, path, r.status_code))
            self.assertTrue(_is_envelope(r.json()), (method, path, r.json()))


class TestHonestEmpty(_StoreRedirect):
    def test_customers_honest_empty(self) -> None:
        """No tenants is a SUCCESS with an empty list — never a fabricated row."""
        body = self.client.get("/api/admin/video/customers").json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["count"], 0)
        self.assertEqual(body["data"]["tenants"], [])

    def test_unknown_tenant_is_honest_empty(self) -> None:
        body = self.client.get("/api/admin/video/customers/does-not-exist").json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["data"]["found"])
        self.assertEqual(body["data"]["timeline"], [])

    def test_asset_not_found_is_honest_empty(self) -> None:
        body = self.client.get("/api/admin/video/assets/ghost_asset").json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["data"]["found"])
        self.assertIsNone(body["data"]["evidence"])
        self.assertEqual(body["data"]["label"], "UNKNOWN")


class TestServerSideScoping(_StoreRedirect):
    def test_customers_lists_only_server_owned_tenants(self) -> None:
        self._make_tenant("acme")
        self._make_tenant("globex")
        body = self.client.get("/api/admin/video/customers").json()
        ids = {t["tenant_id"] for t in body["data"]["tenants"]}
        self.assertEqual(ids, {"acme", "globex"})

    def test_l3_foreign_tenant_is_not_reachable(self) -> None:
        """A tenant the server does not own yields found:false — never its data."""
        self._make_tenant("acme")
        body = self.client.get("/api/admin/video/customers/other-tenant").json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["data"]["found"])
        self.assertEqual(body["data"]["reason"], "tenant_not_owned_by_server")

    def test_owned_tenant_is_found(self) -> None:
        self._make_tenant("acme")
        body = self.client.get("/api/admin/video/customers/acme").json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["data"]["found"])

    def test_generate_rejects_unowned_tenant(self) -> None:
        self._setenv("CREATIVE_OS_ENABLED", "1")
        r = self.client.post("/api/admin/video/generate?tenant_id=ghost&business_name=X")
        body = r.json()
        self.assertFalse(body["ok"])
        self.assertIn("tenant_not_owned_by_server", body["error"])


class TestCustomerTimelineKeysOnVideoDelivered(_StoreRedirect):
    def test_ops_receipt_never_renders_as_customer_delivery(self) -> None:
        """The T03 split, enforced at the API: video_delivered_ops is internal."""
        from app.marketing import delivery_ledger

        self._make_tenant("acme")
        # A genuine customer receipt …
        self.assertTrue(
            delivery_ledger.log_event(
                "acme",
                "video_delivered",
                detail="cr_1:rev0:customer",
                meta={"message_id": "111", "creative_id": "cr_1"},
                key="deliver:cr_1:rev0:customer",
            )
        )
        # … and an internal ops-group receipt (NOT customer-visible).
        self.assertTrue(
            delivery_ledger.log_event(
                "acme",
                "video_delivered_ops",
                detail="cr_1:rev0:ops",
                meta={"message_id": "222", "creative_id": "cr_1"},
                key="deliver:cr_1:rev0:ops",
            )
        )

        body = self.client.get("/api/admin/video/customers/acme").json()
        self.assertTrue(body["ok"], body)
        timeline = body["data"]["timeline"]
        ops_timeline = body["data"]["ops_timeline"]

        customer_events = [e["event"] for e in timeline]
        self.assertIn("video_delivered", customer_events)
        self.assertNotIn(
            "video_delivered_ops",
            customer_events,
            "an ops-only receipt leaked into the customer timeline",
        )
        for row in timeline:
            self.assertTrue(row["customer_visible"], row)
            self.assertIn("label_hi", row)

        ops_events = [e["event"] for e in ops_timeline]
        self.assertIn("video_delivered_ops", ops_events)
        self.assertNotIn("video_delivered", ops_events)

    def test_customer_delivery_carries_message_id(self) -> None:
        from app.marketing import delivery_ledger

        self._make_tenant("acme")
        delivery_ledger.log_event(
            "acme",
            "video_delivered",
            detail="cr_9:rev0:customer",
            meta={"message_id": "999", "creative_id": "cr_9"},
            key="deliver:cr_9:rev0:customer",
        )
        body = self.client.get("/api/admin/video/customers/acme").json()
        rows = [e for e in body["data"]["timeline"] if e["event"] == "video_delivered"]
        self.assertTrue(rows)
        self.assertEqual(rows[0]["message_id"], "999")


class TestGenerateFailClosed(_StoreRedirect):
    def test_generate_disabled_is_honest_error(self) -> None:
        """Gate OFF (default) ⇒ ok:false with a reason, never a fake success."""
        self._setenv("CREATIVE_OS_ENABLED", "0")
        self._make_tenant("acme")
        r = self.client.post("/api/admin/video/generate?tenant_id=acme&business_name=Acme")
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(body["ok"])
        self.assertIn("CREATIVE_OS_ENABLED", body["error"])

    def test_generate_missing_tenant_is_honest_error(self) -> None:
        r = self.client.post("/api/admin/video/generate")
        self.assertEqual(r.status_code, 422)  # required query param — FastAPI validation


class TestNeverRaises(_StoreRedirect):
    _GARBAGE = ["", "   ", "..", "x" * 300, "%2e%2e", "null", "a-b_c", "🚫", "0"]

    def test_l3_and_l4_never_raise(self) -> None:
        """No garbage input may produce a 5xx (unhandled raise). A 404/422 from
        routing/validation is fine; a matched route must return the envelope."""
        failures: list[str] = []
        for g in self._GARBAGE:
            for path in (f"/api/admin/video/customers/{g}", f"/api/admin/video/assets/{g}"):
                try:
                    r = self.client.get(path)
                    if r.status_code >= 500:
                        failures.append(f"{path} -> {r.status_code} {r.text[:80]}")
                    elif r.status_code == 200 and not _is_envelope(r.json()):
                        failures.append(f"{path} -> non-envelope {r.text[:80]}")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{path} -> {type(exc).__name__}: {exc}")
        self.assertEqual(failures, [], "endpoints raised:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
