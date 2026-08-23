"""ADR-104 — bare metadata-only niche readiness tests.

Guards the measured design (addendum #6/#7):
  * readiness must NEVER go through `_get_qdrant_client()` / `_get_qdrant_embedder()`
    (measured >239s because it force-loads FastEmbed; bare ctor = 13.6ms)
  * filter must be namespace AND source="niche:<key>" — ns-only false-readies
  * `real_estate` (QA target, NOT a catalog key) must degrade, never raise
"""

import pytest

from app.voice_agent import kb_readiness as R


class FakeCount:
    def __init__(self, n):
        self.count = n


class FakeClient:
    """Records the filter it was given; never does real I/O."""

    def __init__(self, n=0, raises=None):
        self._n = n
        self._raises = raises
        self.calls = []

    def count(self, collection_name=None, count_filter=None, exact=None):
        self.calls.append({"collection": collection_name, "filter": count_filter, "exact": exact})
        if self._raises:
            raise self._raises
        return FakeCount(self._n)


def _conds(flt):
    """(key, value) pairs from a qdrant Filter — proves ns+source are both applied."""
    out = []
    for c in getattr(flt, "must", []) or []:
        out.append((getattr(c, "key", None), getattr(getattr(c, "match", None), "value", None)))
    return out


# ---------------- catalog / unsupported ---------------- #


def test_catalog_membership_not_hardcoded_size():
    """NOTE: catalog size is RUNTIME-VARIABLE — local repo showed 39 keys but the
    production container showed 42 (same code SHA lineage), so NICHES is extended at
    runtime. Never assert an exact count; assert membership."""
    keys = R.catalog_niches()
    assert len(keys) >= 39
    assert "studying_abroad" in keys
    assert R.is_supported_niche("insurance")
    assert not R.is_supported_niche("real_estate")


def test_unsupported_niche_returns_typed_result_without_client_or_raise():
    """`real_estate`: no exception, no seed, no Qdrant call at all."""
    fake = FakeClient(n=999)
    r = R.count_niche_catalog_points("real_estate", client=fake)

    assert r.supported is False
    assert r.state == R.STATE_UNSUPPORTED
    assert r.is_ready is False
    assert r.count == 0
    assert fake.calls == [], "unsupported niche must not query Qdrant"


def test_unsupported_niche_is_not_ready_via_gate():
    assert R.is_niche_ready("real_estate", client=FakeClient(n=5)) is False


def test_empty_and_none_niche_degrade_safely():
    assert R.count_niche_catalog_points("", client=FakeClient()).state == R.STATE_UNSUPPORTED
    assert R.is_niche_ready("bogus_xyz", client=FakeClient(n=100)) is False


# ---------------- readiness semantics ---------------- #


def test_populated_valid_niche_is_ready():
    r = R.count_niche_catalog_points("insurance", client=FakeClient(n=1674))
    assert r.state == R.STATE_READY
    assert r.is_ready is True
    assert r.count == 1674
    assert r.error_class is None
    assert r.duration_ms >= 0


def test_valid_but_empty_niche_is_not_ready():
    r = R.count_niche_catalog_points("insurance", client=FakeClient(n=0))
    assert r.state == R.STATE_NOT_READY
    assert r.is_ready is False


def test_qdrant_error_degrades_safely_with_error_class_only():
    r = R.count_niche_catalog_points("insurance", client=FakeClient(raises=TimeoutError("boom")))
    assert r.state == R.STATE_ERROR
    assert r.is_ready is False
    assert r.error_class == "TimeoutError"
    # no raw message leaked into the result
    assert "boom" not in repr(r)


def test_no_client_available_degrades_not_ready(monkeypatch):
    monkeypatch.setattr(R, "_bare_client", lambda: None)
    r = R.count_niche_catalog_points("insurance")
    assert r.state == R.STATE_ERROR
    assert r.error_class == "NoClient"
    assert r.is_ready is False


# ---------------- the exact filter (false-ready guard) ---------------- #


def test_filter_uses_both_namespace_and_source():
    """ns-only would false-ready (prod: insurance ns-only=3970 vs ns+source=1674)."""
    fake = FakeClient(n=1)
    R.count_niche_catalog_points("insurance", client=fake)

    conds = _conds(fake.calls[0]["filter"])
    assert ("namespace", "insurance") in conds
    assert ("source", "niche:insurance") in conds
    assert len(conds) == 2
    assert fake.calls[0]["exact"] is True


def test_filter_source_is_scoped_per_niche():
    fake = FakeClient(n=1)
    R.count_niche_catalog_points("studying_abroad", client=fake)
    conds = _conds(fake.calls[0]["filter"])
    assert ("namespace", "studying_abroad") in conds
    assert ("source", "niche:studying_abroad") in conds


def test_uses_the_shared_kb_main_collection():
    from app.voice_agent.knowledge_base import _QDRANT_COLLECTION

    fake = FakeClient(n=1)
    R.count_niche_catalog_points("insurance", client=fake)
    assert fake.calls[0]["collection"] == _QDRANT_COLLECTION


# ---------------- THE incident guard ---------------- #


def test_readiness_never_touches_embedder_or_bootstrapping_client(monkeypatch):
    """THE regression: measured >239s because _get_qdrant_client() force-loads FastEmbed.

    If readiness ever routes through it, we recreate the 39-niche incident on every turn.
    """
    import app.voice_agent.knowledge_base as KB

    called = []
    monkeypatch.setattr(KB, "_get_qdrant_client", lambda *a, **k: called.append("client"))
    monkeypatch.setattr(KB, "_get_qdrant_embedder", lambda *a, **k: called.append("embedder"))

    R.count_niche_catalog_points("insurance", client=FakeClient(n=9))
    R.count_niche_catalog_points("real_estate", client=FakeClient(n=9))
    R.is_niche_ready("solar_residential", client=FakeClient(n=9))

    assert called == [], f"readiness must never load embedder/bootstrap client, got {called}"


def test_module_does_not_import_bootstrap_symbols():
    """Static guard: the module must not reference the expensive/global entrypoints."""
    import inspect

    src = inspect.getsource(R)
    for banned in ("_get_qdrant_embedder", "bootstrap_default_kb", "_get_kb("):
        assert banned not in src.split('"""')[-1], f"{banned} must not be used in code"


def test_readiness_does_no_destructive_operations():
    """Fake client exposes ONLY count(); any create/delete attempt would AttributeError."""
    fake = FakeClient(n=5)
    r = R.count_niche_catalog_points("insurance", client=fake)
    assert r.is_ready
    assert all(set(c) == {"collection", "filter", "exact"} for c in fake.calls)


def test_client_singleton_reset_hook():
    R.reset_client_cache()
    assert R._CLIENT is None
    assert R._CLIENT_FAILED is False
