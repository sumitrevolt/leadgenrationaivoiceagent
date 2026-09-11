"""Novelty gate — refuse near-duplicate videos within a rolling day window.

DESIGN (design doc §8, ruling 2026-09-11)
-----------------------------------------
Video bytes differ on every encode (timestamps, encoder noise), so a byte diff
cannot answer "is this the same video?". What a viewer actually perceives is the
*scene text* plus the recipe/template identity. So we fingerprint the normalised
scene text:

  1. lowercase → strip punctuation/control chars → collapse whitespace
  2. concatenate normalised scene texts in scene order
  3. emit word-level 3-gram shingles, hashed to 16 hex chars, stored SORTED
  4. also store ``scene_text_hash`` (sha256 of the normalised concatenation)

The check runs on the in-memory spec (in ``service.enqueue_generate``), against
the tenant's last N accepted lineage entries, SAME TENANT ONLY. A candidate is
refused when ANY OF:

  * ``jaccard >= THRESHOLD`` (the Jaccard comparison runs over the whole
    ``DEFAULT_LOOKBACK`` window and is ALREADY day-agnostic), OR
  * ``(recipe, template_id)`` is identical to a prior entry whose day is
    ``0 < (candidate_day − prior_day) <= W`` calendar days back
    (``same_recipe_template_within_window``), OR
  * ``scene_match_ratio >= RATIO`` — at least ``RATIO`` of the candidate's
    SCENES are byte-identical (same word-3-gram shingle set) to one prior
    entry's scenes. This catches the Jaccard-DILUTION clone: swap 1 of N scenes
    and the rest are verbatim, so the whole-text Jaccard stays *under*
    ``THRESHOLD`` and the global-shingle rule misses it — yet the viewer sees a
    near-duplicate. ``RATIO`` is ``flags.novelty_scene_match_ratio()`` (0.75).

WHY A WINDOW, NOT "YESTERDAY"
    The structural rule used to fire only when the prior entry was the
    *immediately preceding* calendar day. Measured same-recipe-variant similarity
    is ~0.50–0.606, i.e. the 0.6 threshold sits ABOVE that band — so the
    structural rule is what actually catches a same-recipe variant, and scoping
    it to exactly one day left a hole: accept on day 1, SKIP day 2, ship a
    near-clone on day 3 and the gate passed it (``ok: True``). A rolling window
    closes that hole without touching the threshold. This is a *widening* of the
    refusal set — every same-(recipe,template) case refused before is still
    refused, and same-(recipe,template) cases within the window are now refused
    too. Everything else is unchanged.

UNVERIFIABLE ("cannot evaluate" is labelled, never a silent pass)
    A spec whose normalised scene text is shorter than a 3-gram produces NO
    shingles (see ``_shingles``). That is legitimate — a genuinely short line
    must not be treated as identical to another short line (that was an
    availability bug). But an empty fingerprint also makes the Jaccard path read
    ``0.0`` for everything, so a candidate the gate cannot evaluate must never
    look like a clean pass: the result always carries ``novelty_unverifiable:
    True`` and a ``no_fingerprint`` reason, and (when
    ``CREATIVE_NOVELTY_ALERT_ON_UNVERIFIABLE`` is on) an owner-feed note is
    emitted. It is NOT a hard block — short text is legitimate and a hard block
    would starve a real tenant. The structural rule still applies on top.

STARVATION GUARD
    When rotation retries exhaust and every candidate was refused, the tenant
    must still receive a video. ``resolve_exhaustion`` picks the LEAST-SIMILAR
    candidate, accepts it with ``forced=True`` and records the outcome. A tenant
    must never end up with no video at all.

PERSISTENCE
  - One append-only JSONL per tenant at ``<root>/<tenant_id>.jsonl``, where
    ``<root>`` is resolved through ``runtime_data_authority`` at CALL time
    (store id ``creative.novelty``).
  - Every public entry returns a dict and NEVER raises.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.marketing.creative_os import flags
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Similarity at/above which a candidate is considered a near-duplicate.
#: This is the *default behind* ``flags.novelty_jaccard_threshold()`` — the live
#: value is read through the accessor at call time. Kept for documentation and
#: for callers/tests that reference the historical constant.
JACCARD_THRESHOLD = 0.6

#: How many prior accepted entries we compare against (the Jaccard window).
DEFAULT_LOOKBACK = 7

_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_WS_RE = re.compile(r"\s+")
_NGRAM = 3

#: Why an unverifiable candidate could not be fingerprinted.
REASON_NO_FINGERPRINT = "no_fingerprint"

#: Reason emitted when the structural rule refuses a candidate.
REASON_SAME_RT_WINDOW = "same_recipe_template_within_window"

#: Reason emitted when the scene-level match rule refuses a candidate.
REASON_SCENE_MATCH = "scene_match_ratio"


@dataclass
class CreativeLineage:
    """One accepted creative's identity, for cross-day duplicate detection."""

    tenant_id: str
    creative_id: str
    revision: int
    day: str
    recipe: str
    template_id: str
    hook_variant: str
    spec_hash: str
    scene_text_hash: str
    shingles: list[str] = field(default_factory=list)
    scene_shingles: list[list[str]] = field(default_factory=list)
    at: float = 0.0
    forced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CreativeLineage:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered)


# --------------------------------------------------------------------------- #
# Fingerprinting
# --------------------------------------------------------------------------- #
def normalize_text(text: Any) -> str:
    """lowercase → strip punctuation/control chars → collapse whitespace."""
    s = str(text or "").lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def _shingles(tokens: list[str]) -> list[str]:
    if len(tokens) >= _NGRAM:
        grams = [" ".join(tokens[i : i + _NGRAM]) for i in range(len(tokens) - _NGRAM + 1)]
    else:
        # Fewer than _NGRAM words: too little signal to fingerprint. A single
        # whole-line shingle would make two different short lines compare
        # identical (jaccard 1.0) and permanently block the tenant, so emit
        # nothing and let callers read this as "no fingerprint" (jaccard 0.0).
        grams = []
    return sorted({hashlib.sha256(g.encode("utf-8")).hexdigest()[:16] for g in grams})


def _scene_text(sc: Any) -> str:
    """Read a scene's text from EITHER an object or a JSON-round-tripped mapping.

    ``scene_fingerprint`` used to read only ``getattr(sc, "text", "")``, so a
    spec that had been through ``json.dumps``/``json.loads`` (scenes as plain
    dicts) yielded ``shingles == []`` for every candidate and the gate compared
    everything as ``0.0`` similarity — blind. Reading the mapping closes it.
    """
    if isinstance(sc, Mapping):
        return str(sc.get("text", "") or "")
    return str(getattr(sc, "text", "") or "")


def _scene_shingle_sets(spec: Any) -> list[frozenset]:
    """Per-scene shingle SETS (only non-empty scenes), for scene-level matching.

    Returns one ``frozenset`` of word-3-gram shingles per scene whose text yields
    at least one shingle. Empty scenes are dropped: they can never match a prior
    and must not count as a false "match". Backs the ``scene_match_ratio`` refusal
    rule that catches the Jaccard-dilution clone (1-of-N scenes swapped).
    """
    out: list[frozenset] = []
    for sc in _spec_scenes(spec):
        toks = normalize_text(_scene_text(sc)).split()
        grams = _shingles(toks)
        if grams:
            out.append(frozenset(grams))
    return out


def _spec_attr(spec: Any, name: str, default: Any = "") -> Any:
    """Read a spec field from either an object attribute or a mapping key."""
    if isinstance(spec, Mapping):
        return spec.get(name, default)
    return getattr(spec, name, default)


def _spec_scenes(spec: Any) -> list[Any]:
    """Scene list from either an object (``.scenes``) or a mapping (``["scenes"]``)."""
    scenes = _spec_attr(spec, "scenes", None)
    try:
        return list(scenes or [])
    except Exception:
        return []


def scene_fingerprint(spec: Any) -> dict[str, Any]:
    """Fingerprint a spec's scene TEXT only. Never raises."""
    try:
        parts = [normalize_text(_scene_text(sc)) for sc in _spec_scenes(spec)]
        joined = " ".join(p for p in parts if p)
        tokens = joined.split() if joined else []
        return {
            "shingles": _shingles(tokens),
            "scene_text_hash": hashlib.sha256(joined.encode("utf-8")).hexdigest(),
            "normalized": joined,
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[novelty] scene_fingerprint failed: %s", exc)
        return {"shingles": [], "scene_text_hash": "", "normalized": ""}


def _as_set(x: Any) -> set:
    """Coerce a shingle collection to a set; anything unusable ⇒ empty set."""
    if isinstance(x, (set, frozenset, list, tuple)):
        return set(x)
    if isinstance(x, str):
        return {x} if x else set()
    return set()


def jaccard(a: list[str] | set[str] | None, b: list[str] | set[str] | None) -> float:
    """|A∩B| / |A∪B|; empty union ⇒ 0.0. Never raises on a non-iterable arg."""
    sa, sb = _as_set(a), _as_set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


# --------------------------------------------------------------------------- #
# Persistence (call-time store resolution)
# --------------------------------------------------------------------------- #
def _novelty_dir() -> str:
    from app.platform import runtime_data_authority as _auth

    override = "CREATIVE_NOVELTY_ROOT"
    if not os.getenv(override) and os.getenv("CREATIVE_LEDGER_ROOT"):
        override = "CREATIVE_LEDGER_ROOT"
    return str(
        _auth.resolve_store_path(
            store_id="creative.novelty",
            legacy_path=Path("data") / "creative_os" / "novelty",
            target_segments=("marketing", "novelty"),
            override_env=override,
        )
    )


def _safe_stem(tenant_id: str) -> str:
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(tenant_id)


def _lineage_path(tenant_id: str) -> str:
    return os.path.join(_novelty_dir(), f"{_safe_stem(tenant_id)}.jsonl")


def _lock(path: str):
    try:
        from filelock import FileLock

        return FileLock(path + ".lock", timeout=5)
    except Exception:  # pragma: no cover
        import contextlib

        return contextlib.nullcontext()


def append_lineage(lineage: CreativeLineage) -> dict[str, Any]:
    """Append one lineage line (append-only JSONL). Never raises."""
    try:
        tid = str(lineage.tenant_id or "").strip()
        if not tid:
            return {"ok": False, "error": "tenant_id_required"}
        _novelty_dir()
        os.makedirs(_novelty_dir(), exist_ok=True)
        fp = _lineage_path(tid)
        line = json.dumps(lineage.to_dict(), ensure_ascii=False, default=str)
        try:
            with _lock(fp):
                with open(fp, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            with open(fp, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return {"ok": True, "tenant_id": tid, "path": fp}
    except Exception as exc:
        logger.warning("[novelty] append_lineage failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


def recent_lineage(tenant_id: str, n: int = DEFAULT_LOOKBACK) -> list[CreativeLineage]:
    """Last ``n`` accepted lineage entries for this tenant (oldest→newest)."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return []
    try:
        cap = max(1, int(n or DEFAULT_LOOKBACK))
    except Exception:
        cap = DEFAULT_LOOKBACK
    try:
        fp = _lineage_path(tid)
    except Exception:
        return []
    if not os.path.isfile(fp):
        return []
    rows: deque[CreativeLineage] = deque(maxlen=cap)
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                try:
                    rows.append(CreativeLineage.from_dict(rec))
                except Exception:
                    continue
    except Exception as exc:  # pragma: no cover
        logger.warning("[novelty] recent_lineage failed (%s): %s", tid, exc)
    return list(rows)


def _prev_day(day: str) -> str:
    try:
        return (date.fromisoformat(str(day)) - timedelta(days=1)).isoformat()
    except Exception:
        return ""


def _day_gap(candidate_day: str, prior_day: str) -> int | None:
    """``(candidate_day − prior_day)`` in whole calendar days, or ``None``.

    Uses the same ``date.fromisoformat`` arithmetic as ``_prev_day``. Returns
    ``None`` when either day is empty/unparsable so the caller treats the prior
    as "not in window" (the Jaccard path is unaffected).
    """
    try:
        c = date.fromisoformat(str(candidate_day))
        p = date.fromisoformat(str(prior_day))
    except Exception:
        return None
    return (c - p).days


def cross_tenant_warning(spec_hash: str, tenant_id: str, *, window: int = DEFAULT_LOOKBACK) -> dict[str, Any]:
    """Advisory: does ANOTHER tenant share this ``spec_hash`` in the lookback?

    Returns only an aggregate (``shared`` + ``tenant_count``) — never another
    tenant's ids or rows, so the tenant boundary is preserved even while
    detecting cross-customer coincidence (§8.4).
    """
    tid = str(tenant_id or "").strip()
    out = {"shared": False, "tenant_count": 0}
    if not spec_hash or not tid:
        return out
    try:
        d = _novelty_dir()
    except Exception:
        return out
    if not os.path.isdir(d):
        return out
    try:
        own = f"{_safe_stem(tid)}.jsonl"
    except Exception:
        return out
    count = 0
    try:
        for name in os.listdir(d):
            if not name.endswith(".jsonl") or name == own:
                continue
            fp = os.path.join(d, name)
            try:
                with open(fp, encoding="utf-8") as f:
                    tail: deque[str] = deque(f, maxlen=max(1, int(window)))
                for line in tail:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(rec, dict) and str(rec.get("spec_hash") or "") == spec_hash:
                        count += 1
                        break
            except Exception:
                continue
    except Exception:
        return out
    out["tenant_count"] = count
    out["shared"] = count > 0
    return out


# --------------------------------------------------------------------------- #
# Alerts / audit (best-effort; every helper is itself never-raising)
# --------------------------------------------------------------------------- #
def _owner_feed_note(
    text: str, *, severity: str = "P1", evidence: str = "", dedupe_key: str = ""
) -> bool:
    """Best-effort owner-feed event. Never raises; returns True if written."""
    try:
        from app.utils.owner_feed import emit as _of_emit

        return bool(
            _of_emit(
                source="prod",
                actor="novelty",
                text=str(text or "")[:1000],
                severity=severity,
                kind="incident",
                evidence=str(evidence or "")[:500],
                verified=True,
                dedupe_key=dedupe_key or None,
            )
        )
    except Exception:
        return False


def _ledger_note(tenant_id: str, event: str, *, detail: str = "", meta: dict[str, Any] | None = None) -> bool:
    """Best-effort delivery-ledger audit note. Never raises.

    If the ledger registry does not yet know ``event``, the outcome is recorded
    under the registered ``novelty_blocked`` audit event (with the real event
    name in ``meta``) so a guard action is never silently lost.
    """
    try:
        from app.marketing import delivery_ledger

        wrote = bool(
            delivery_ledger.log_event(tenant_id, event, detail=detail, meta=meta, actor="novelty")
        )
        if not wrote and event not in getattr(delivery_ledger, "EVENT_TYPES", frozenset()):
            wrote = bool(
                delivery_ledger.log_event(
                    tenant_id,
                    "novelty_blocked",
                    detail=f"{event}:{detail}",
                    meta={**(meta or {}), "novelty_event": event},
                    actor="novelty",
                )
            )
        return wrote
    except Exception:
        return False


def _emit_unverifiable(tenant_id: str, spec: Any, day: str) -> bool:
    """Emit the owner-feed note for a candidate that could not be fingerprinted."""
    try:
        if not flags.novelty_alert_on_unverifiable():
            return False
    except Exception:
        return False
    return _owner_feed_note(
        f"novelty_unverifiable (no scene fingerprint): {tenant_id}",
        severity="P1",
        evidence=f"tenant={tenant_id} day={day}",
        dedupe_key=f"novelty_unverifiable:{tenant_id}",
    )


# --------------------------------------------------------------------------- #
# The gate
# --------------------------------------------------------------------------- #
def _structural_hit(
    prior: CreativeLineage, recipe: str, template_id: str, day: str, window_days: int
) -> bool:
    """Same (recipe, template) as ``prior`` AND the prior is within the window."""
    same_rt = bool(prior.recipe == recipe and str(prior.template_id or "") == template_id)
    if not same_rt or not day:
        return False
    gap = _day_gap(day, prior.day)
    return bool(gap is not None and 0 < gap <= window_days)


def check(
    spec: Any,
    tenant_id: str,
    *,
    n: int = DEFAULT_LOOKBACK,
    day: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Decide whether ``spec`` is a near-duplicate of the tenant's recent history.

    Returns ``{"ok": True, "fingerprint", "against", "cross_tenant"}`` when the
    candidate is acceptable, or ``{"ok": False, "outcome": "near_duplicate",
    "reason", "against", "tried": []}`` when it must be re-selected. ``force``
    turns a refusal into an accepted-but-flagged result. When the candidate
    cannot be fingerprinted the pass is labelled (``novelty_unverifiable: True``
    + ``reason == "no_fingerprint"``) rather than returned clean. Never raises.
    """
    try:
        thr = flags.novelty_jaccard_threshold()
        window_days = flags.novelty_window_days()
        scene_thr = flags.novelty_scene_match_ratio()
        fp = scene_fingerprint(spec)
        shingles = fp.get("shingles") or []
        unverifiable = not shingles
        recipe = str(_spec_attr(spec, "recipe", "") or "")
        template_id = str(_spec_attr(spec, "template_id", "") or "")
        try:
            spec_hash = spec.spec_hash()
        except Exception:
            spec_hash = ""
        # Per-scene shingle sets for the scene-level match rule. An empty
        # candidate (no fingerprintable scenes) simply never trips the rule.
        cand_scene_sets = _scene_shingle_sets(spec)
        cand_scene_total = len(_spec_scenes(spec))
        priors = recent_lineage(tenant_id, n=n)
        against: list[dict[str, Any]] = []
        structural_hit = False
        scene_hit = False
        for p in priors:
            j = jaccard(shingles, p.shingles)
            same_rt = bool(p.recipe == recipe and str(p.template_id or "") == template_id)
            within_window = _structural_hit(p, recipe, template_id, day, window_days)
            prior_sets = set(frozenset(s) for s in (p.scene_shingles or []) if s)
            matched = sum(1 for cs in cand_scene_sets if cs in prior_sets)
            scene_ratio = (matched / cand_scene_total) if cand_scene_total else 0.0
            this_scene_hit = bool(cand_scene_sets) and scene_ratio >= scene_thr
            if j >= thr or within_window or this_scene_hit:
                against.append(
                    {
                        "creative_id": p.creative_id,
                        "jaccard": round(j, 4),
                        "recipe": p.recipe,
                        "template_id": p.template_id,
                        "day": p.day,
                        "same_recipe_template": same_rt,
                        "within_window": within_window,
                        "scene_match_ratio": round(scene_ratio, 4),
                        "scene_match_hit": this_scene_hit,
                    }
                )
            if within_window:
                structural_hit = True
            if this_scene_hit:
                scene_hit = True
        cross = cross_tenant_warning(spec_hash, tenant_id, window=n)
        result: dict[str, Any] = {
            "fingerprint": fp,
            "against": against,
            "cross_tenant": cross,
        }

        if unverifiable:
            # Cannot evaluate similarity. Never a silent pass and never a hard
            # block: label it, and fall back to the structural / scene rules.
            if (structural_hit or scene_hit) and not force:
                reasons = []
                if structural_hit:
                    reasons.append(REASON_SAME_RT_WINDOW)
                if scene_hit:
                    reasons.append(f"{REASON_SCENE_MATCH}>={scene_thr}")
                result.update(
                    {
                        "ok": False,
                        "outcome": "near_duplicate",
                        "reason": f"{REASON_NO_FINGERPRINT},{','.join(reasons)}",
                        "novelty_unverifiable": True,
                        "tried": [],
                    }
                )
                return result
            result.update(
                {
                    "ok": True,
                    "forced": bool((structural_hit or scene_hit) and force),
                    "novelty_unverifiable": True,
                    "reason": REASON_NO_FINGERPRINT,
                }
            )
            _emit_unverifiable(tenant_id, spec, day)
            return result

        if against and not force:
            reasons = []
            if any(a["jaccard"] >= thr for a in against):
                reasons.append("jaccard>=0.6")
            if any(a["same_recipe_template"] and a["within_window"] for a in against):
                reasons.append(REASON_SAME_RT_WINDOW)
            if any(a.get("scene_match_hit") for a in against):
                reasons.append(f"{REASON_SCENE_MATCH}>={scene_thr}")
            result.update(
                {
                    "ok": False,
                    "outcome": "near_duplicate",
                    "reason": ",".join(reasons) or "near_duplicate",
                    "tried": [],
                }
            )
            return result

        result.update({"ok": True, "forced": bool(against and force)})
        return result
    except Exception as exc:
        logger.warning("[novelty] check failed: %s", exc)
        # A gate that cannot run must not block a legitimate render — but it must
        # also never look like a clean pass: label it unverifiable.
        try:
            _emit_unverifiable(tenant_id, spec, day)
        except Exception:
            pass
        return {
            "ok": True,
            "fingerprint": {},
            "against": [],
            "cross_tenant": {},
            "novelty_unverifiable": True,
            "reason": REASON_NO_FINGERPRINT,
            "error": str(exc)[:160],
        }


def _similarity_profile(
    spec: Any, priors: list[CreativeLineage], window_days: int, day: str
) -> dict[str, Any]:
    """Peak Jaccard + structural-window flag for one candidate vs the priors."""
    fp = scene_fingerprint(spec)
    shingles = fp.get("shingles") or []
    recipe = str(_spec_attr(spec, "recipe", "") or "")
    template_id = str(_spec_attr(spec, "template_id", "") or "")
    max_j = 0.0
    structural = False
    for p in priors:
        j = jaccard(shingles, p.shingles)
        if j > max_j:
            max_j = j
        if _structural_hit(p, recipe, template_id, day, window_days):
            structural = True
    return {
        "max_jaccard": max_j,
        "structural": structural,
        "unverifiable": not shingles,
    }


def resolve_exhaustion(
    candidates: list[Any] | tuple[Any, ...] | None,
    tenant_id: str,
    *,
    day: str = "",
    n: int = DEFAULT_LOOKBACK,
) -> dict[str, Any]:
    """Starvation guard — a tenant must NEVER end up with no video.

    Called when the rotation loop produced ``K+1`` candidates and the gate
    refused ALL of them. Instead of returning empty (no video) or blocking the
    tenant, pick the LEAST-SIMILAR candidate — lowest peak Jaccard against the
    tenant's recent history, tie-broken toward a candidate that does NOT trip the
    structural rule — accept it with ``forced=True`` and record the outcome:

      * a ``delivery_ledger("novelty_exhausted")`` audit event (falling back to
        the registered ``novelty_blocked`` audit event when the ledger registry
        does not yet know ``novelty_exhausted`` — the outcome is never lost);
      * an ``owner_feed`` alert.

    Returns ``{"ok": True, "forced": True, "outcome": "novelty_exhausted",
    "spec": <chosen>, "events": ["novelty_exhausted"], ...}``. Never returns an
    empty ``spec`` for a non-empty candidate list; never raises.
    """
    try:
        cand_list = list(candidates or [])
    except Exception:
        cand_list = []
    tid = str(tenant_id or "")
    if not cand_list:
        return {
            "ok": False,
            "outcome": "novelty_exhausted",
            "error": "no_candidates",
            "events": [],
        }
    try:
        window_days = flags.novelty_window_days()
        priors = recent_lineage(tenant_id, n=n)
        scored = [
            (idx, spec, _similarity_profile(spec, priors, window_days, day))
            for idx, spec in enumerate(cand_list)
        ]
        # Least-similar first: lowest peak Jaccard, then non-structural, then the
        # earliest index (stable, deterministic).
        scored.sort(key=lambda t: (t[2]["max_jaccard"], 1 if t[2]["structural"] else 0, t[0]))
        chosen_idx, chosen_spec, chosen_prof = scored[0]
        accepted = accept(chosen_spec, tenant_id, day=day, forced=True)
        detail = f"picked#{chosen_idx}/{len(cand_list)} j={chosen_prof['max_jaccard']:.3f}"
        meta = {
            "chosen_index": chosen_idx,
            "candidates": len(cand_list),
            "max_jaccard": round(chosen_prof["max_jaccard"], 4),
            "structural": chosen_prof["structural"],
            "unverifiable": chosen_prof["unverifiable"],
        }
        ledger_written = _ledger_note(tid, "novelty_exhausted", detail=detail, meta=meta)
        feed_written = _owner_feed_note(
            f"novelty_exhausted: {tid} — all {len(cand_list)} rotations refused; shipped least-similar (forced)",
            severity="P1",
            evidence=f"tenant={tid} day={day}",
            dedupe_key=f"novelty_exhausted:{tid}:{day}",
        )
        return {
            "ok": True,
            "forced": True,
            "outcome": "novelty_exhausted",
            "spec": chosen_spec,
            "chosen_index": chosen_idx,
            "candidates": [
                {
                    "index": i,
                    "max_jaccard": round(p["max_jaccard"], 4),
                    "structural": p["structural"],
                    "unverifiable": p["unverifiable"],
                }
                for (i, _s, p) in scored
            ],
            "accepted": bool(accepted.get("ok")),
            "events": ["novelty_exhausted"],
            "ledger_written": ledger_written,
            "owner_feed": feed_written,
        }
    except Exception as exc:
        logger.warning("[novelty] resolve_exhaustion failed: %s", exc)
        # Absolute invariant: still hand back a candidate rather than nothing.
        fallback = cand_list[0]
        return {
            "ok": True,
            "forced": True,
            "outcome": "novelty_exhausted",
            "spec": fallback,
            "events": ["novelty_exhausted"],
            "error": str(exc)[:160],
        }


def accept(
    spec: Any,
    tenant_id: str,
    *,
    day: str = "",
    forced: bool = False,
) -> dict[str, Any]:
    """Record the WINNING spec as an accepted lineage entry. Never raises."""
    try:
        fp = scene_fingerprint(spec)
        spec_hash = ""
        try:
            spec_hash = spec.spec_hash()
        except Exception:
            spec_hash = ""
        lineage = CreativeLineage(
            tenant_id=str(tenant_id or ""),
            creative_id=str(_spec_attr(spec, "creative_id", "") or ""),
            revision=int(_spec_attr(spec, "approval_revision", 0) or 0),
            day=str(day or ""),
            recipe=str(_spec_attr(spec, "recipe", "") or ""),
            template_id=str(_spec_attr(spec, "template_id", "") or ""),
            hook_variant=str(_spec_attr(spec, "hook_variant", "") or ""),
            spec_hash=spec_hash,
            scene_text_hash=str(fp.get("scene_text_hash") or ""),
            shingles=list(fp.get("shingles") or []),
            scene_shingles=[list(s) for s in _scene_shingle_sets(spec)],
            at=time.time(),
            forced=bool(forced),
        )
        return append_lineage(lineage)
    except Exception as exc:
        logger.warning("[novelty] accept failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


__all__ = [
    "CreativeLineage",
    "DEFAULT_LOOKBACK",
    "JACCARD_THRESHOLD",
    "REASON_NO_FINGERPRINT",
    "REASON_SCENE_MATCH",
    "REASON_SAME_RT_WINDOW",
    "accept",
    "append_lineage",
    "check",
    "cross_tenant_warning",
    "jaccard",
    "normalize_text",
    "recent_lineage",
    "resolve_exhaustion",
    "scene_fingerprint",
]
