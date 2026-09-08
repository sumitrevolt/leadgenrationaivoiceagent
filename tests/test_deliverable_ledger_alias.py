"""`customer_deliverables` advancement across the dual-id / pre-rename split.

Production 2026-08-06: Jiya Makeover has 20 deliverable rows, all `not_started`,
while 24 `content` automation runs succeeded and 149 content approvals exist.

Two independent exact-match failures in `sync_customer_deliverable_status`:

1. **client_id.** The two stores use different ids on purpose
   (`clients_store.resolve_client` docstring names `d79d690f61b3` vs
   `jiya-makeover`). `customer_deliverables.client_id` is an FK to Postgres
   `clients.id`, so rows are seeded under the BILLING id — while every writer
   that advances them passes the MARKETING id. Every other marketing-domain
   consumer got the canonicalisation retrofit; this writer was missed.

2. **deliverable_type.** `_LEGACY_DB_DELIVERABLE_TYPES` only renames in-place
   when the seeder re-runs for the same client+cycle. Rows seeded before the
   rename and never re-seeded still hold `social_post_draft` while callers pass
   `social_posts`.

Both failures return `False`, which every call site discards inside
`except Exception: pass`. The fix is read-side: expand the match. Nothing is
re-keyed and the seed still writes the FK-valid billing id.
"""

from __future__ import annotations

from app.marketing import product_one_delivery as pod

# The real production pair, kept verbatim so these tests stay tied to the actual
# 2026-08-06 finding. This is a TENANT ID, not a credential — the same value is
# already in `clients_store.resolve_client`'s docstring. detect-secrets flags it
# as a hex high-entropy string; allowlisted rather than obscured so the test
# still documents the case it exists for.
_BILLING_ID = "d79d690f61b3"  # pragma: allowlist secret
_MARKETING_ID = "jiya-makeover"


# --------------------------------------------------------------------------- #
# type alias expansion
# --------------------------------------------------------------------------- #
def test_type_candidates_include_legacy_names():
    got = pod._deliverable_type_candidates("social_posts")
    assert "social_posts" in got
    # TWO legacy rows collapse into this one current type
    assert "social_post_draft" in got
    assert "monthly_content_calendar" in got


def test_type_candidates_for_each_renamed_type():
    for legacy, current in pod._LEGACY_DB_DELIVERABLE_TYPES.items():
        assert legacy in pod._deliverable_type_candidates(current), (
            f"{legacy} must still match a writer passing {current}"
        )


def test_type_candidates_unknown_type_is_itself():
    assert pod._deliverable_type_candidates("invoice") == ["invoice"]


def test_type_candidates_blank_is_empty():
    assert pod._deliverable_type_candidates("") == []
    assert pod._deliverable_type_candidates("   ") == []


# --------------------------------------------------------------------------- #
# client id alias expansion
# --------------------------------------------------------------------------- #
def test_client_candidates_include_marketing_and_billing_ids(monkeypatch):
    """The real Jiya shape once the alias is linked."""
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "resolve_client",
        lambda _c: {"id": _MARKETING_ID, "billing_client_ids": [_BILLING_ID]},
    )
    got = pod._deliverable_client_id_candidates(_MARKETING_ID)
    assert _MARKETING_ID in got
    assert _BILLING_ID in got, "rows are seeded under the billing id — must match"


def test_client_candidates_dedupe(monkeypatch):
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "resolve_client",
        lambda _c: {"id": "abc", "billing_client_ids": ["abc", "abc"]},
    )
    assert pod._deliverable_client_id_candidates("abc") == ["abc"]


def test_client_candidates_degrade_to_exact_match_when_unlinked(monkeypatch):
    """Jiya's CURRENT prod state: billing_client_ids is empty. The code must not
    invent a link — it degrades to today's exact-match behaviour."""
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "resolve_client",
        lambda _c: {"id": "jiya-makeover", "billing_client_ids": []},
    )
    assert pod._deliverable_client_id_candidates("jiya-makeover") == ["jiya-makeover"]


def test_client_candidates_never_raise(monkeypatch):
    from app.marketing import clients_store

    def _boom(_c):
        raise RuntimeError("jsonl unreadable")

    monkeypatch.setattr(clients_store, "resolve_client", _boom)
    assert pod._deliverable_client_id_candidates("x") == ["x"]


def test_client_candidates_blank_is_empty():
    assert pod._deliverable_client_id_candidates("") == []


# --------------------------------------------------------------------------- #
# the writer now finds the row it always should have
# --------------------------------------------------------------------------- #
class _Row:
    def __init__(self, client_id, dtype):
        from app.models.customer_deliverable import DeliverableStatus

        self.client_id = client_id
        self.deliverable_type = dtype
        self.status = DeliverableStatus.NOT_STARTED
        self.billing_cycle_month = "2026-07"
        self.created_at = None
        self.updated_at = None
        self.delivered_at = None
        self.evidence_url = None
        self.evidence_payload = None
        self.owner = None
        self.error_message = None


class _Query:
    def __init__(self, rows, captured):
        self.rows = rows
        self.captured = captured

    def filter(self, *criteria):
        # record the IN-clause values so the test can assert alias expansion
        for c in criteria:
            try:
                self.captured.append(list(c.right.value))
            except Exception:
                pass
        return self

    def order_by(self, *_a):
        return self

    def first(self):
        return self.rows[0] if self.rows else None


class _Session:
    def __init__(self, rows, captured):
        self.rows = rows
        self.captured = captured

    def query(self, *_a, **_k):
        return _Query(self.rows, self.captured)


def _patch(monkeypatch, session):
    import contextlib

    import app.models.base as mb

    @contextlib.contextmanager
    def _ctx():
        yield session

    monkeypatch.setattr(mb, "get_db_session", _ctx, raising=False)


def test_sync_advances_row_stored_under_billing_id_and_legacy_type(monkeypatch):
    """End-to-end shape of the production bug: writer says
    (jiya-makeover, social_posts); row says (d79d690f61b3, social_post_draft)."""
    from app.marketing import clients_store
    from app.models.customer_deliverable import DeliverableStatus

    monkeypatch.setattr(
        clients_store,
        "resolve_client",
        lambda _c: {"id": _MARKETING_ID, "billing_client_ids": [_BILLING_ID]},
    )
    row = _Row(_BILLING_ID, "social_post_draft")
    captured: list[list[str]] = []
    _patch(monkeypatch, _Session([row], captured))

    ok = pod.sync_customer_deliverable_status(
        _MARKETING_ID, "social_posts", "pending_approval", evidence_payload={"generated_count": 3}
    )
    assert ok is True, "the row must now be found and advanced"
    assert row.status == DeliverableStatus.PENDING_APPROVAL

    flat = [v for group in captured for v in group]
    assert _BILLING_ID in flat, "billing id must be in the client_id IN-clause"
    assert "social_post_draft" in flat, "legacy type must be in the type IN-clause"


def test_sync_still_returns_false_when_no_row_exists(monkeypatch):
    """jsonl-only customers must keep degrading quietly — the writer's contract
    is update-only and must never create rows or raise."""
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "resolve_client", lambda _c: None)
    _patch(monkeypatch, _Session([], []))
    assert pod.sync_customer_deliverable_status("ghost", "social_posts", "delivered") is False


def test_sync_blank_args_short_circuit():
    assert pod.sync_customer_deliverable_status("", "social_posts", "delivered") is False
    assert pod.sync_customer_deliverable_status("cid", "", "delivered") is False
