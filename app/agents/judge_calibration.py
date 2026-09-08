"""judge_calibration.py — offline calibration of LLM/agent "judges" vs human ground-truth.

Problem
-------
Across the platform several automated "judges" emit an approve/reject-flavoured
SIGNAL before a human ever looks at the item:
  - code_upgrader proposes a patch (the act of proposing == "this is worth doing").
  - sales_team grades a prospect A/B/C with a 0-100 score.
  - coordinator produces a draft plan (substance == "this plan is good enough").
The human then approves/rejects in:
  - data/code_patches.jsonl   (status updates: approved | rejected | applied)
  - data/approval_decisions.jsonl  ({source,item_id,status,by,at} — approvals_bridge)

This module reads those jsonl files OFFLINE (no LLM, no network, no DB) and, per
judge source, computes how well the judge's signal agreed with the eventual human
decision: raw % agreement + Cohen's kappa (chance-corrected agreement). It returns
a verdict per judge:
    reliable          kappa >= 0.41 AND enough paired samples
    advisory          kappa <  0.41 (judge disagrees with humans too often)
    insufficient-data not enough paired (judge-signal + human-decision) samples

Design rules (project gold-pattern)
- Pure-python, read-only, NEVER raises. One bad file => that source is
  insufficient-data, the rest still compute.
- Sparse/empty data is the COMMON case (these jsonl files start empty) — every
  path degrades to {"verdict": "insufficient-data"} rather than blowing up.
- No imports of heavy/agent modules at call time (only stdlib + logger).
"""

from __future__ import annotations

import json
import os
from typing import Any

try:  # logger is cheap + import-safe; degrade if unavailable
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

_DATA = "data"
_DECISIONS = os.path.join(_DATA, "approval_decisions.jsonl")
_CODE_PATCHES = os.path.join(_DATA, "code_patches.jsonl")
_COORD_RUNS = os.path.join(_DATA, "coordination_runs.jsonl")

# Minimum paired samples before kappa is even meaningful. Below this the verdict
# is always insufficient-data regardless of agreement (small-N kappa is noise).
_MIN_PAIRS = 8
# Landis & Koch "moderate" floor — below this a judge is advisory-only.
_KAPPA_RELIABLE = 0.41

# Human-decision normalisation: many synonyms collapse to a binary.
_POS_HUMAN = {"approved", "approve", "applied", "accept", "accepted", "yes"}
_NEG_HUMAN = {"rejected", "reject", "no", "declined", "denied"}


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        if not os.path.exists(path):
            return out
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        out.append(obj)
                except Exception:
                    pass
    except Exception as e:  # pragma: no cover - fs error
        logger.debug("[judge_calib] read skip %s: %s", path, e)
    return out


def _human_label(status: Any) -> int | None:
    """Map a human decision string to 1 (positive) / 0 (negative) / None (n/a)."""
    s = str(status or "").strip().lower()
    if s in _POS_HUMAN:
        return 1
    if s in _NEG_HUMAN:
        return 0
    return None


# --------------------------------------------------------------------------- #
# Cohen's kappa over paired binary labels (judge vs human)
# --------------------------------------------------------------------------- #
def cohens_kappa(pairs: list[tuple[int, int]]) -> float | None:
    """Cohen's kappa for a list of (judge_label, human_label) in {0,1}.

    Returns None if there are no pairs. Edge case: when both raters are perfectly
    constant AND identical, observed-agreement is 1.0 and expected-agreement is
    also 1.0 -> 0/0; we return 1.0 (perfect agreement) which is the conventional
    treatment for that degenerate-but-correct case.
    """
    n = len(pairs)
    if n == 0:
        return None
    # Confusion counts
    a = b = c = d = 0  # a=both1, d=both0, b=judge1/human0, c=judge0/human1
    for jl, hl in pairs:
        jl = 1 if jl else 0
        hl = 1 if hl else 0
        if jl == 1 and hl == 1:
            a += 1
        elif jl == 0 and hl == 0:
            d += 1
        elif jl == 1 and hl == 0:
            b += 1
        else:
            c += 1
    po = (a + d) / n  # observed agreement
    # Marginals -> expected agreement by chance
    p_j1 = (a + b) / n
    p_j0 = (c + d) / n
    p_h1 = (a + c) / n
    p_h0 = (b + d) / n
    pe = (p_j1 * p_h1) + (p_j0 * p_h0)
    denom = 1.0 - pe
    if denom == 0:
        # Both raters constant. If they also agree (po==1) -> perfect; else 0.
        return 1.0 if po >= 0.999999 else 0.0
    return (po - pe) / denom


def _verdict(kappa: float | None, n_pairs: int) -> str:
    if kappa is None or n_pairs < _MIN_PAIRS:
        return "insufficient-data"
    return "reliable" if kappa >= _KAPPA_RELIABLE else "advisory"


def _summarise(source: str, pairs: list[tuple[int, int]], note: str = "") -> dict[str, Any]:
    n = len(pairs)
    kappa = cohens_kappa(pairs)
    agree = None
    if n:
        agree = round(sum(1 for j, h in pairs if (1 if j else 0) == (1 if h else 0)) / n, 4)
    return {
        "source": source,
        "n_pairs": n,
        "agreement": agree,
        "kappa": (round(kappa, 4) if kappa is not None else None),
        "verdict": _verdict(kappa, n),
        "note": note,
    }


# --------------------------------------------------------------------------- #
# Per-source pairing
# --------------------------------------------------------------------------- #
def _pairs_code_patches() -> tuple[list[tuple[int, int]], str]:
    """code_upgrader judge: a proposed patch == judge says positive (1).

    The jsonl appends status-updates; collapse to latest status per id. The judge
    signal is constant-positive (it only proposes things it thinks are worth it),
    so kappa measures whether humans agree with the proposing-judge. A judge that
    only ever fires "yes" CAN still be reliable if humans also mostly say yes, but
    kappa correctly punishes a one-sided judge when humans disagree.
    """
    rows = _read_jsonl(_CODE_PATCHES)
    if not rows:
        return [], "no code_patches.jsonl yet"
    latest: dict[str, dict[str, Any]] = {}
    for r in rows:
        pid = str(r.get("id") or "")
        if not pid:
            continue
        merged = dict(latest.get(pid) or {})
        merged.update(r)
        latest[pid] = merged
    pairs: list[tuple[int, int]] = []
    for pid, r in latest.items():
        hl = _human_label(r.get("status"))
        if hl is None:
            continue  # still "proposed" / undecided -> no human label yet
        # Judge signal = it proposed this patch at all -> positive.
        pairs.append((1, hl))
    return pairs, f"{len(latest)} patches, {len(pairs)} human-decided"


def _coord_score_map() -> dict[str, int]:
    """Judge signal per coordinator run: 1 if the draft has real substance, else 0."""
    out: dict[str, int] = {}
    for r in _read_jsonl(_COORD_RUNS):
        rid = str(r.get("run_id") or r.get("id") or "")
        if not rid:
            continue
        substance = bool(
            r.get("summary") or r.get("solution") or r.get("design") or r.get("implementation_plan")
        )
        out[rid] = 1 if substance else 0
    return out


def _decision_map() -> dict[str, list[dict[str, Any]]]:
    """Latest human decision per (source, item_id) from approval_decisions.jsonl,
    grouped by source. Later rows overwrite earlier (collapse-to-latest)."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in _read_jsonl(_DECISIONS):
        src = str(r.get("source") or "").strip().lower()
        iid = str(r.get("item_id") or "").strip()
        if src and iid:
            latest[(src, iid)] = r
    grouped: dict[str, list[dict[str, Any]]] = {}
    for (src, iid), r in latest.items():
        grouped.setdefault(src, []).append({**r, "item_id": iid})
    return grouped


def _pairs_coordinator(
    decisions: dict[str, list[dict[str, Any]]],
) -> tuple[list[tuple[int, int]], str]:
    """coordinator judge (substance-detector) vs human approve/reject."""
    rows = decisions.get("coordinator", [])
    if not rows:
        return [], "no coordinator decisions yet"
    smap = _coord_score_map()
    pairs: list[tuple[int, int]] = []
    matched = 0
    for r in rows:
        hl = _human_label(r.get("status"))
        if hl is None:
            continue
        jl = smap.get(str(r.get("item_id")))
        if jl is None:
            continue  # decision for a run we can't see the judge-signal for
        matched += 1
        pairs.append((jl, hl))
    return pairs, f"{len(rows)} decisions, {matched} matched to a run signal"


def _pairs_generic_decisions(
    source: str, decisions: dict[str, list[dict[str, Any]]]
) -> tuple[list[tuple[int, int]], str]:
    """Fallback judge for sources (e.g. sales/fde) where the only available judge
    signal is the act-of-surfacing itself. The agent surfaced the item == it judged
    it worth a human's time == positive (1). Measures human agreement with that.
    """
    rows = decisions.get(source, [])
    if not rows:
        return [], f"no {source} decisions yet"
    pairs: list[tuple[int, int]] = []
    for r in rows:
        hl = _human_label(r.get("status"))
        if hl is None:
            continue
        pairs.append((1, hl))
    return pairs, f"{len(rows)} decisions, {len(pairs)} human-decided"


# --------------------------------------------------------------------------- #
# Public entrypoint
# --------------------------------------------------------------------------- #
def calibrate() -> dict[str, Any]:
    """Calibrate every judge against human ground-truth. Never raises.

    Returns:
        {
          "judges": [ {source,n_pairs,agreement,kappa,verdict,note}, ... ],
          "summary": {"reliable":[..],"advisory":[..],"insufficient":[..]},
          "thresholds": {"min_pairs":8,"kappa_reliable":0.41},
          "ok": True,
        }
    """
    judges: list[dict[str, Any]] = []
    try:
        decisions = _decision_map()
    except Exception as e:  # pragma: no cover
        logger.debug("[judge_calib] decision_map skip: %s", e)
        decisions = {}

    # code_upgrader (self-contained in code_patches.jsonl)
    try:
        p, note = _pairs_code_patches()
        judges.append(_summarise("code_upgrader", p, note))
    except Exception as e:  # pragma: no cover
        logger.debug("[judge_calib] code_patches skip: %s", e)
        judges.append(_summarise("code_upgrader", [], "error"))

    # coordinator (substance-detector judge vs human, via approval_decisions)
    try:
        p, note = _pairs_coordinator(decisions)
        judges.append(_summarise("coordinator", p, note))
    except Exception as e:  # pragma: no cover
        logger.debug("[judge_calib] coordinator skip: %s", e)
        judges.append(_summarise("coordinator", [], "error"))

    # sales + fde (surfacing-judge fallback)
    for src in ("sales", "fde"):
        try:
            p, note = _pairs_generic_decisions(src, decisions)
            judges.append(_summarise(src, p, note))
        except Exception as e:  # pragma: no cover
            logger.debug("[judge_calib] %s skip: %s", src, e)
            judges.append(_summarise(src, [], "error"))

    summary = {
        "reliable": [j["source"] for j in judges if j["verdict"] == "reliable"],
        "advisory": [j["source"] for j in judges if j["verdict"] == "advisory"],
        "insufficient": [j["source"] for j in judges if j["verdict"] == "insufficient-data"],
    }
    return {
        "ok": True,
        "judges": judges,
        "summary": summary,
        "thresholds": {"min_pairs": _MIN_PAIRS, "kappa_reliable": _KAPPA_RELIABLE},
    }


__all__ = ["calibrate", "cohens_kappa"]
