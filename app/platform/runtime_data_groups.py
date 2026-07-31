"""Deterministic declaration grouping for scanner findings.

691 unique unresolved fingerprints cannot be reviewed one at a time, and they
should not be: a module normally has ONE logical store touched from several
call sites. Grouping turns "691 items" into a reviewable set of authorities.

This is ANALYTICAL evidence only. It never mutates the allowlist, the store
manifest or the ratchet baseline. It proposes `probable_store_ids`; a human
still has to establish reader/writer/authority before anything is declared.

The grouping key deliberately does NOT include the package alone. A package
like `app/marketing` contains suppression, delivery ledgers, caches and
generated media — a directory rule would map unrelated authorities onto one
store, which is exactly the bulk shortcut that must not happen.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.platform import runtime_data_scan as _scan

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
UNRESOLVED = "UNRESOLVED"

# Filename stem -> manifest store id. Used ONLY to propose a candidate; a
# proposal is never a declaration. Resemblance is not authority.
_STORE_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"invoice"), "billing.invoices"),
    (re.compile(r"upi"), "billing.upi_payments"),
    (re.compile(r"email_suppress|email_unsub"), "compliance.email_suppression"),
    (re.compile(r"wa_suppress|whatsapp_suppress"), "compliance.wa_suppression"),
    (re.compile(r"consent"), "compliance.consent_ledger"),
    (re.compile(r"voice_suppress|dnd"), "compliance.voice_suppression"),
    (re.compile(r"dpdp"), "compliance.dpdp_audit"),
    (re.compile(r"marketing_clients|clients_store|customer"), "customers.identity"),
    (re.compile(r"prospect"), "sales.prospects"),
    (re.compile(r"approval"), "content.approvals"),
    (re.compile(r"content_queue|queue"), "content.queue"),
    (re.compile(r"delivery"), "delivery.ledger"),
    (re.compile(r"interaction"), "communications.interactions"),
    (re.compile(r"job_run|_runs\b|runs\.jsonl"), "automation.job_runs"),
    (re.compile(r"cadence"), "automation.cadence_runs"),
    (re.compile(r"recording|transcript"), "artifacts.call_recordings"),
    (re.compile(r"ollama|u2net|fastembed|model"), "cache.ml_models"),
    (re.compile(r"owner_os"), "governance.owner_os"),
    (re.compile(r"mission_control"), "governance.mission_control"),
    (re.compile(r"autopilot|tick"), "automation.autopilot_tick"),
)

_LOCK_SUFFIX_RE = re.compile(r"\.lock\b|\.lck\b")


def _path_root(finding: dict[str, Any]) -> str:
    """The store-identifying part of a path, ignoring per-record suffixes.

    `data/prospects/<id>.json` and `data/prospects/<other>.json` are the same
    authority; keeping the id would create one group per record.
    """
    raw = _scan.normalized_path(finding)
    # Strip a trailing `.lock` so a lock lands in its data's group.
    stem = _LOCK_SUFFIX_RE.sub("", raw)
    m = re.search(r"(?:data|runtime-data)[/\\]([A-Za-z0-9_\-.]+)", stem)
    if m:
        return m.group(1)
    # Symbol-resolved expressions keep their constructor text as identity.
    return stem[:80] or "<unknown>"


def _module(file: str) -> str:
    parts = file.split("/")
    return "/".join(parts[:-1]) or "."


def group_key(finding: dict[str, Any]) -> tuple[str, str, str]:
    return (_module(finding["file"]), _path_root(finding), finding["file"])


def _probable_stores(root: str, paths: list[str]) -> list[str]:
    hay = " ".join([root, *paths]).lower()
    out = []
    for pattern, store in _STORE_HINTS:
        if pattern.search(hay) and store not in out:
            out.append(store)
    return out


def _confidence(group: dict[str, Any]) -> str:
    """Confidence in the PROPOSAL, not in the safety of the code."""
    stores = group["probable_store_ids"]
    if group["classifications"] == {_scan.CANONICAL_RUNTIME_PATH}:
        return HIGH
    if len(stores) == 1 and group["symbols"] and None not in group["symbols"]:
        return HIGH
    if len(stores) == 1:
        return MEDIUM
    if len(stores) > 1:
        return LOW  # ambiguous authority — a guess here would be a bad mapping
    return UNRESOLVED


def build(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group findings deterministically. Every finding lands in exactly one."""
    buckets: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for f in findings:
        buckets.setdefault(group_key(f), []).append(f)

    groups: list[dict[str, Any]] = []
    for key, items in sorted(buckets.items()):
        module, root, file = key
        gid = "g_" + hashlib.sha256("|".join(key).encode("utf-8")).hexdigest()[:16]
        paths = sorted({_scan.normalized_path(x) for x in items})
        classifications = {x["classification"] for x in items}
        operations = sorted({x["operation"] for x in items})
        g = {
            "group_id": gid,
            "module": module,
            "path_root": root,
            "files": sorted({x["file"] for x in items}),
            "symbols": sorted({x.get("symbol") for x in items}, key=lambda s: (s is None, s)),
            "operations": operations,
            "normalized_paths": paths,
            "classifications": classifications,
            "finding_fingerprints": sorted({_scan.fingerprint(x) for x in items}),
            "finding_count": len(items),
            "production_relevance": (
                "PRODUCTION"
                if any(x.get("production_relevant") for x in items)
                else "NON_PRODUCTION"
            ),
            "has_lock": any(x["operation"] == _scan.LOCK for x in items),
            "mutating_count": sum(1 for x in items if x["operation"] in _scan.MUTATING_OPERATIONS),
        }
        g["probable_store_ids"] = _probable_stores(root, paths)
        g["confidence"] = _confidence(g)
        g["evidence_required"] = _evidence_required(g)
        g["recommended_next_action"] = _next_action(g)
        groups.append(g)

    groups.sort(key=lambda g: (-g["mutating_count"], g["module"], g["path_root"]))
    return groups


def _evidence_required(g: dict[str, Any]) -> list[str]:
    need = []
    if not g["probable_store_ids"]:
        need.append("store authority unknown — inspect executable readers/writers")
    if len(g["probable_store_ids"]) > 1:
        need.append("multiple candidate stores — filename resemblance is not authority")
    if g["mutating_count"]:
        need.append("writer modules + access modes")
    if _scan.AMBIGUOUS_REQUIRES_REVIEW in g["classifications"]:
        need.append("resolve import-time capture / unattributed read")
    if g["has_lock"]:
        need.append("confirm the lock's protected store (must match, not split)")
    return need


def _next_action(g: dict[str, Any]) -> str:
    if g["classifications"] == {_scan.CANONICAL_RUNTIME_PATH}:
        return "none — already canonical"
    if g["classifications"] <= {
        _scan.DECLARED_LEGACY_READ,
        _scan.DECLARED_LEGACY_WRITE,
    }:
        return "none — already declared"
    if g["confidence"] == HIGH and g["mutating_count"]:
        return "verify readers/writers, then add ONE symbol-level allowlist entry"
    if g["confidence"] in (MEDIUM, LOW):
        return "inspect call paths to establish authority before declaring"
    return "classify: unknown authority"


def reconcile(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Explain the gap between unresolved FINDINGS and unique FINGERPRINTS.

    A fingerprint covering two call sites of one store is fine. A fingerprint
    covering two different files, symbols or operations would mean distinct
    mutations were collapsed — which would hide real debt, so it is counted
    and surfaced rather than assumed benign.
    """
    from app.platform import runtime_data_ratchet as _ratchet

    unresolved = [f for f in findings if f["classification"] in _ratchet.UNRESOLVED]
    by_fp: dict[str, list[dict[str, Any]]] = {}
    for f in unresolved:
        by_fp.setdefault(_scan.fingerprint(f), []).append(f)

    multi_file = sum(1 for v in by_fp.values() if len({x["file"] for x in v}) > 1)
    multi_symbol = sum(1 for v in by_fp.values() if len({x.get("symbol") for x in v}) > 1)
    multi_op = sum(1 for v in by_fp.values() if len({x["operation"] for x in v}) > 1)

    return {
        "unresolved_findings": len(unresolved),
        "unique_unresolved_fingerprints": len(by_fp),
        "duplicate_fingerprint_instances": len(unresolved) - len(by_fp),
        "fingerprints_with_multiple_files": multi_file,
        "fingerprints_with_multiple_symbols": multi_symbol,
        "fingerprints_with_multiple_operations": multi_op,
    }


def tier0_report(findings: list[dict[str, Any]], tier0_ids: list[str]) -> dict[str, Any]:
    """Per-Tier-0-store coverage. Derived; never hand-maintained."""
    from app.platform import runtime_data_ratchet as _ratchet

    groups = build(findings)
    out: dict[str, Any] = {}
    for sid in tier0_ids:
        rel = [g for g in groups if sid in g["probable_store_ids"]]
        items = [
            f
            for g in rel
            for f in findings
            if _scan.fingerprint(f) in set(g["finding_fingerprints"])
        ]
        unresolved_mut = [
            f
            for f in items
            if f["classification"] in _ratchet.UNRESOLVED
            and f["operation"] in _scan.MUTATING_OPERATIONS
            and f.get("production_relevant")
        ]
        out[sid] = {
            "groups": [g["group_id"] for g in rel],
            "total_findings": len(items),
            "declared_findings": sum(
                1
                for f in items
                if f["classification"] in (_scan.DECLARED_LEGACY_READ, _scan.DECLARED_LEGACY_WRITE)
            ),
            "unresolved_findings": sum(
                1 for f in items if f["classification"] in _ratchet.UNRESOLVED
            ),
            "unresolved_production_mutating": len(unresolved_mut),
            "lock_findings": sum(1 for f in items if f["operation"] == _scan.LOCK),
            "modules": sorted({f["file"] for f in items}),
        }
    return out


__all__ = [
    "HIGH",
    "MEDIUM",
    "LOW",
    "UNRESOLVED",
    "group_key",
    "build",
    "reconcile",
    "tier0_report",
]
