"""Pure-python tests for the RAG A/B retrieval gate scoring/delta math.

NO network / DB / LLM / live Qdrant. The gate operates on a
`retrieve_fn(query, k) -> list[dict]` so we feed deterministic fake retrievers
and assert the recall/precision/delta + PASS/FAIL gate arithmetic.

Run:
  .venv\\Scripts\\python.exe -m pytest tests/test_rag_retrieval_ab.py -q
"""

from __future__ import annotations

import importlib.util
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "rag_retrieval_ab", os.path.join(_ROOT, "scripts", "rag_retrieval_ab.py")
)
ab = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ab)  # type: ignore


# --------------------------------------------------------------------------- #
# Fake retrievers — return labeled docs (by id) as {"text": ...} hits in order.
# --------------------------------------------------------------------------- #
def _hits(*doc_ids: str) -> list[dict]:
    return [{"text": ab.LABELED_DOCS[d], "score": 1.0, "source": "fake"} for d in doc_ids]


def fn_perfect(query: str, k: int) -> list[dict]:
    """Returns exactly the relevant docs for each labeled query."""
    for case in ab.LABELED_SET:
        if case["query"] == query:
            return _hits(*sorted(case["relevant"]))[:k]
    return []


def fn_empty(query: str, k: int) -> list[dict]:
    return []


def fn_noise_only(query: str, k: int) -> list[dict]:
    """Always returns the irrelevant marketing doc."""
    return _hits("marketing_noise")[:k]


def fn_first_query_only(query: str, k: int) -> list[dict]:
    """Relevant only for the first labeled query, else noise."""
    if query == ab.LABELED_SET[0]["query"]:
        return _hits(*sorted(ab.LABELED_SET[0]["relevant"]))[:k]
    return _hits("marketing_noise")[:k]


# --------------------------------------------------------------------------- #
# _hit_doc_id mapping
# --------------------------------------------------------------------------- #
def test_hit_doc_id_exact_match():
    hit = {"text": ab.LABELED_DOCS["solar_bill"]}
    assert ab._hit_doc_id(hit) == "solar_bill"


def test_hit_doc_id_chunked_substring():
    # a chunk (substring) of the real doc still maps back
    chunk = ab.LABELED_DOCS["pricing_kw"][:40]
    assert ab._hit_doc_id({"text": chunk}) == "pricing_kw"


def test_hit_doc_id_empty_and_unknown():
    assert ab._hit_doc_id({"text": ""}) is None
    assert ab._hit_doc_id({"text": "totally unrelated banana phone xyz"}) is None


def test_overlap_ratio_bounds():
    assert ab._overlap_ratio("", "abc") == 0.0
    assert ab._overlap_ratio("a b c", "a b c") == 1.0
    r = ab._overlap_ratio("a b c d", "a b x y")
    assert 0.0 < r < 1.0


# --------------------------------------------------------------------------- #
# score_config
# --------------------------------------------------------------------------- #
def test_score_perfect_is_full_recall_precision():
    sc = ab.score_config(fn_perfect, k=3)
    assert sc["recall"] == 1.0
    assert sc["precision"] == 1.0
    assert sc["f1"] == 1.0
    assert len(sc["per_query"]) == len(ab.LABELED_SET)


def test_score_empty_is_zero():
    sc = ab.score_config(fn_empty, k=3)
    assert sc["recall"] == 0.0
    assert sc["precision"] == 0.0
    assert sc["f1"] == 0.0


def test_score_noise_zero_recall_zero_precision():
    sc = ab.score_config(fn_noise_only, k=3)
    # marketing_noise is never in any relevant set
    assert sc["recall"] == 0.0
    assert sc["precision"] == 0.0


def test_score_partial_recall_math():
    # Custom labeled set: 1 query, 2 relevant docs, retriever returns 1 of them.
    labeled = [{"query": "q", "relevant": {"solar_bill", "warranty_25y"}}]

    def fn(query, k):
        return _hits("solar_bill")[:k]

    sc = ab.score_config(fn, labeled_set=labeled, k=3)
    assert sc["recall"] == 0.5  # 1 of 2 relevant
    assert sc["precision"] == 1.0  # 1 retrieved, 1 relevant


def test_score_precision_with_one_noise():
    labeled = [{"query": "q", "relevant": {"solar_bill"}}]

    def fn(query, k):
        return _hits("solar_bill", "marketing_noise")[:k]

    sc = ab.score_config(fn, labeled_set=labeled, k=3)
    assert sc["recall"] == 1.0
    assert sc["precision"] == 0.5  # 1 relevant of 2 retrieved


def test_k_cutoff_truncates():
    labeled = [{"query": "q", "relevant": {"warranty_25y"}}]

    def fn(query, k):
        # relevant doc is at position 2 — beyond k=1 cutoff
        return _hits("marketing_noise", "warranty_25y")

    sc = ab.score_config(fn, labeled_set=labeled, k=1)
    assert sc["recall"] == 0.0  # cut off before the relevant doc


# --------------------------------------------------------------------------- #
# compute_deltas + gate
# --------------------------------------------------------------------------- #
def test_compute_deltas_passes_when_upgrade_beats_baseline():
    report = ab.compute_deltas(
        {"baseline": fn_first_query_only, "full": fn_perfect}, k=3, margin=0.05
    )
    assert report["baseline"]["recall"] < 1.0
    assert report["configs"]["full"]["recall"] == 1.0
    assert report["configs"]["full"]["recall_delta"] > 0
    assert report["configs"]["full"]["passed"] is True
    assert report["winner"] == "full"
    assert report["passed"] is True


def test_compute_deltas_fails_when_no_improvement():
    # both baseline and candidate identical -> delta 0 -> below margin -> fail
    report = ab.compute_deltas({"baseline": fn_perfect, "rerank": fn_perfect}, k=3, margin=0.05)
    assert report["configs"]["rerank"]["recall_delta"] == 0.0
    assert report["configs"]["rerank"]["passed"] is False
    assert report["winner"] is None
    assert report["passed"] is False


def test_compute_deltas_fails_on_precision_regression():
    # candidate matches baseline recall but drags precision down -> gate blocks it
    labeled = [{"query": "q", "relevant": {"solar_bill"}}]

    def base_fn(query, k):
        return _hits("solar_bill")[:k]

    def cand_fn(query, k):
        return _hits("solar_bill", "marketing_noise", "maintenance")[:k]

    report = ab.compute_deltas(
        {"baseline": base_fn, "cand": cand_fn}, labeled_set=labeled, k=3, margin=0.0
    )
    assert report["configs"]["cand"]["recall_delta"] == 0.0
    assert report["configs"]["cand"]["precision_delta"] < 0
    assert report["configs"]["cand"]["passed"] is False
    assert report["passed"] is False


def test_compute_deltas_picks_best_winner():
    # "full" beats "rerank"; both pass, winner = larger recall_delta
    report = ab.compute_deltas(
        {
            "baseline": fn_empty,
            "rerank": fn_first_query_only,
            "full": fn_perfect,
        },
        k=3,
        margin=0.05,
    )
    assert report["configs"]["rerank"]["passed"] is True
    assert report["configs"]["full"]["passed"] is True
    assert report["winner"] == "full"  # bigger delta


def test_compute_deltas_requires_baseline():
    with pytest.raises(ValueError):
        ab.compute_deltas({"full": fn_perfect})


def test_margin_boundary_inclusive():
    # delta exactly == margin should PASS (>=)
    labeled = [
        {"query": "a", "relevant": {"solar_bill"}},
        {"query": "b", "relevant": {"pricing_kw"}},
    ]

    def base_fn(query, k):
        return []  # recall 0

    def cand_fn(query, k):
        # answer query "a" only -> recall 0.5 == margin
        if query == "a":
            return _hits("solar_bill")[:k]
        return []

    report = ab.compute_deltas(
        {"baseline": base_fn, "cand": cand_fn}, labeled_set=labeled, k=3, margin=0.5
    )
    assert report["configs"]["cand"]["recall_delta"] == 0.5
    assert report["configs"]["cand"]["passed"] is True


# --------------------------------------------------------------------------- #
# format_delta_table + run_gate rc
# --------------------------------------------------------------------------- #
def test_format_delta_table_contains_configs_and_verdict():
    report = ab.compute_deltas({"baseline": fn_empty, "full": fn_perfect}, k=3, margin=0.05)
    table = ab.format_delta_table(report)
    assert "baseline" in table
    assert "full" in table
    assert "GATE PASS" in table


def test_run_gate_rc_pass_and_fail(capsys):
    rc_pass = ab.run_gate({"baseline": fn_empty, "full": fn_perfect}, k=3, margin=0.05)
    assert rc_pass == 0
    rc_fail = ab.run_gate({"baseline": fn_perfect, "x": fn_perfect}, k=3, margin=0.05)
    assert rc_fail == 1
    out = capsys.readouterr().out
    assert "GATE" in out


def test_labeled_set_ids_exist_in_docs():
    # contract: every relevant id in the labeled set has a backing doc
    for case in ab.LABELED_SET:
        for did in case["relevant"]:
            assert did in ab.LABELED_DOCS
