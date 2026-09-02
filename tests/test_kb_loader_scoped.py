"""ADR-104 Phase A4.2 — niche-scoped KB seeding (leaf loader).

Ye tests wo exact production defect pakadte hain: 4-niche QA run ne SAARE 39
niches seed kar diye the (`studying_abroad` samet, jo maanga hi nahi gaya tha),
kyunki `load_niche_faqs()` me koi niche filter tha hi nahi.

Backward-compat sabse zaroori hai: `bootstrap_default_kb()` ke 4 non-voice
caller (supervisor / api.data / agent_provisioner) bilkul waise hi chalein.

NOTE (test-writing me mila, code-verified): har niche ke facts DO jagah jaate
hain — uske apne namespace me AUR `_global` me (source=`niche:<key>`). Isliye
scoped-seed assertions me `_global` ko ignore karke dekha jaata hai ki koi
DOOSRA niche-namespace to nahi chhua.
"""

import pytest

from app.voice_agent import kb_loader

# Real NICHES keys (verified: catalog me 39 hain). `real_estate` JAAN-BOOJH KE
# nahi use kiya — wo QA ka default target hai par NICHES catalog me hai hi nahi.
NICHE_A = "insurance"
NICHE_B = "solar_residential"
NICHE_C = "ai_marketing"
NICHE_D = "interior_designers"


class FakeKB:
    """add_documents ko record karta hai — koi real embed/upsert nahi."""

    def __init__(self):
        self.calls = []  # (source, namespace, n_docs)

    def add_documents(self, docs, source="", namespace="_global", **kw):
        docs = list(docs or [])
        self.calls.append((source, namespace, len(docs)))
        return len(docs)

    def stats(self):
        return {"fake": True}

    def namespaces_touched(self):
        return {ns for _, ns, _ in self.calls}

    def niche_namespaces_touched(self):
        """`_global` chhod ke — kaunse niche namespaces chhue gaye."""
        return {ns for _, ns, _ in self.calls if ns != "_global"}

    def sources_touched(self):
        return {src for src, _, _ in self.calls}


def _all_niche_keys():
    from app.niches import NICHES

    return set((NICHES or {}).keys())


def test_niches_catalog_includes_studying_abroad():
    """`studying_abroad` prod me bina maange seed hua tha — membership pin karo.

    SIZE assert MAT karo: local repo me 39 keys the par production container me 42
    nikle (same code lineage) => NICHES runtime pe extend hota hai. Exact count pe
    test likhna prod ke against jhootha green/red dega.
    """
    keys = _all_niche_keys()
    assert len(keys) >= 39
    assert "studying_abroad" in keys


def test_legacy_no_filter_seeds_all_niches_and_global_faqs():
    """only=None => purana behaviour bilkul same (4 global callers isi pe hain)."""
    kb = FakeKB()
    total = kb_loader.load_niche_faqs(kb)

    assert total > 0
    assert "business_faq" in kb.sources_touched()
    assert "_global" in kb.namespaces_touched()
    missing = _all_niche_keys() - kb.namespaces_touched()
    assert not missing, f"legacy seed ne ye niches miss kiye: {sorted(missing)}"


def test_single_niche_scope_touches_only_that_niche():
    """THE regression: ek niche maango => koi doosra niche-namespace na chhue."""
    kb = FakeKB()
    kb_loader.load_niche_faqs(kb, only=NICHE_A)
    assert kb.niche_namespaces_touched() == {NICHE_A}


def test_single_niche_scope_does_not_touch_studying_abroad():
    """Production me dekha gaya exact symptom: unrelated niche seed ho gaya tha."""
    kb = FakeKB()
    kb_loader.load_niche_faqs(kb, only=NICHE_A)
    assert "studying_abroad" not in kb.namespaces_touched()


def test_four_niche_qa_scope_touches_exactly_those_four():
    """QA 4 niches maangta hai => theek 4 seed hon, 39 nahi."""
    kb = FakeKB()
    wanted = [NICHE_A, NICHE_B, NICHE_C, NICHE_D]
    kb_loader.load_niche_faqs(kb, only=wanted)

    assert kb.niche_namespaces_touched() == set(wanted)
    assert "studying_abroad" not in kb.namespaces_touched()
    # 39 - 4 = 35 niches ka koi kaam nahi hona chahiye
    assert len(kb.niche_namespaces_touched()) == 4


def test_scoped_seed_skips_global_business_faqs():
    """Scoped seed common business FAQs (niche-data nahi) skip kare.

    `_global` phir bhi chhuta hai kyunki niche ke apne facts wahan bhi jaate
    hain (source=`niche:<key>`) — wo scoped kaam ka hissa hai, extra fan-out nahi.
    """
    kb = FakeKB()
    kb_loader.load_niche_faqs(kb, only=NICHE_A)
    assert "business_faq" not in kb.sources_touched()


def test_unknown_niche_fails_fast_and_does_no_work():
    """Typo chupchaap '0 chunks seeded' me na badle."""
    kb = FakeKB()
    with pytest.raises(ValueError) as ei:
        kb_loader.load_niche_faqs(kb, only="not_a_real_niche")
    assert "not_a_real_niche" in str(ei.value)
    assert kb.calls == [], "invalid niche pe koi bhi write nahi hona chahiye"


def test_qa_default_target_real_estate_is_not_in_catalog():
    """Pre-existing drift (ADR-104 ke tests ne pakda): QA `real_estate` test karta
    hai par wo NICHES catalog me hai hi nahi => uska KB kabhi seed nahi ho sakta.
    Reply path ko isko gracefully degrade karna hoga, raise nahi."""
    from app.agents.staff import _qa_default_niches

    assert "real_estate" in _qa_default_niches()
    assert "real_estate" not in _all_niche_keys()


def test_unknown_niche_in_list_rejects_whole_batch_before_any_write():
    kb = FakeKB()
    with pytest.raises(ValueError):
        kb_loader.load_niche_faqs(kb, only=[NICHE_A, "bogus_niche"])
    assert kb.calls == []


def test_seed_niche_returns_redacted_structured_result():
    kb = FakeKB()
    r = kb_loader.seed_niche(kb, NICHE_A)

    assert r["ok"] is True
    assert r["niche"] == NICHE_A
    assert r["chunks"] > 0
    assert r["error_class"] is None
    assert isinstance(r["duration_s"], float)
    # sirf safe operational keys — koi doc text / prompt / customer data nahi
    assert set(r) == {"niche", "ok", "chunks", "duration_s", "error_class"}
    assert kb.niche_namespaces_touched() == {NICHE_A}


def test_seed_niche_invalid_returns_error_class_not_raise():
    kb = FakeKB()
    r = kb_loader.seed_niche(kb, "nope_not_here")
    assert r["ok"] is False
    assert r["error_class"] == "ValueError"
    assert r["chunks"] == 0
    assert kb.calls == []


def test_bootstrap_default_kb_still_full_seed(monkeypatch):
    """4 global callers (supervisor/api.data/agent_provisioner) ka contract intact."""
    kb = FakeKB()
    monkeypatch.setattr(kb_loader, "get_knowledge_base", lambda: kb)

    out = kb_loader.bootstrap_default_kb()

    assert out is kb
    assert "_global" in kb.namespaces_touched()
    assert not (_all_niche_keys() - kb.namespaces_touched()), (
        "bootstrap ab bhi saare niches seed kare"
    )
