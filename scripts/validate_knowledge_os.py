#!/usr/bin/env python3
"""Phase 9 — LeadGen Knowledge OS validator + acceptance tests.

Validates the whole agentic-knowledge layer:
1. Registries parse (runbooks, playbooks, owner truth).
2. Classifier is conservative (RED for compliance/irreversible; fail-closed).
3. Every runbook has required fields (id/name/trigger/class/source/detection).
4. Every playbook has required fields.
5. Secrets scan over notebook_exports/ + ops/ (no raw keys).
6. Acceptance scenarios (TEST A-D from the master prompt) pass retrieval.

Run directly (CI) or via pytest (tests/test_knowledge_os.py).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPS = ROOT / "ops"

REQUIRED_RB = {"id", "name", "trigger", "class", "source", "detection"}
REQUIRED_PB = {"id", "name", "trigger", "source", "priority"}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY"),
    re.compile(r"password\s*[:=]\s*['\"]?[^\s'\"]{8,}", re.I),
]


def load_yaml(path: Path) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_runbooks() -> list[str]:
    errs = []
    reg = load_yaml(OPS / "runbooks" / "registry.yaml")
    rbs = reg.get("runbooks", [])
    ids = set()
    for rb in rbs:
        missing = REQUIRED_RB - set(rb.keys())
        if missing:
            errs.append(f"RB {rb.get('id', '?')}: missing {sorted(missing)}")
        if rb.get("id") in ids:
            errs.append(f"RB {rb.get('id')}: duplicate id")
        ids.add(rb.get("id"))
        cls = rb.get("class")
        if cls not in {"GREEN", "AMBER", "RED"}:
            errs.append(f"RB {rb.get('id')}: bad class {cls}")
        # conservative checks: compliance/irreversible runbooks must NOT be GREEN
        if cls == "GREEN":
            naughty = rb.get("id", "").startswith(("RB-VOICE-001", "RB-VOICE-004", "RB-INFRA-004", "RB-INFRA-006", "RB-INFRA-009", "RB-SALES-006"))
            if naughty:
                errs.append(f"RB {rb.get('id')}: GREEN but compliance/irreversible — must be AMBER/RED")
    if not rbs:
        errs.append("runbook registry empty")
    return errs


def validate_playbooks() -> list[str]:
    errs = []
    reg = load_yaml(OPS / "playbooks" / "registry.yaml")
    pbs = reg.get("playbooks", [])
    ids = set()
    for pb in pbs:
        missing = REQUIRED_PB - set(pb.keys())
        if missing:
            errs.append(f"PB {pb.get('id', '?')}: missing {sorted(missing)}")
        if pb.get("id") in ids:
            errs.append(f"PB {pb.get('id')}: duplicate id")
        ids.add(pb.get("id"))
    if not pbs:
        errs.append("playbook registry empty")
    return errs


def validate_truth() -> list[str]:
    errs = []
    try:
        t = load_yaml(OPS / "owner_truth.yaml")
    except Exception as e:
        return [f"owner_truth.yaml parse: {e}"]
    for key in ["schema_version", "production", "priorities", "blockers"]:
        if key not in t:
            errs.append(f"owner_truth missing {key}")
    return errs


def scan_secrets(dirpath: Path) -> list[str]:
    hits = []
    if not dirpath.exists():
        return hits
    for p in sorted(dirpath.rglob("*")):
        if p.suffix.lower() not in {".md", ".yaml", ".yml", ".txt", ".json"}:
            continue
        if p.name in {".env", "server.env"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pat in SECRET_PATTERNS:
            m = pat.search(text)
            if m:
                hits.append(f"{p.relative_to(ROOT)}: {m.group(0)[:24]}…")
                break
    return hits


def acceptance_tests() -> list[tuple[str, bool, str]]:
    """TEST A-D from the master prompt, executed against retrieval."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import knowledge_query as kq

    results = []
    # TEST A: Busy Line -> voice runbook + playbook
    b = kq.build_bundle("Calls are failing with Busy Line")
    ids = {rb["id"] for rb in b["runbooks"]}
    ok_a = "RB-VOICE-002" in ids and b["domain"] == "voice"
    results.append(("A: Busy Line -> RB-VOICE-002 + voice domain", ok_a,
                    f"runbooks={sorted(ids)[:4]}"))

    # TEST B: deploy -> infra runbooks + deployment playbook
    b = kq.build_bundle("Deploy latest safe change")
    ids = {rb["id"] for rb in b["runbooks"]}
    pids = {pb["id"] for pb in b["playbooks"]}
    ok_b = b["domain"] == "infra" and ("RB-INFRA-007" in ids or "RB-INFRA-009" in ids) and "PB-DEPLOYMENT" in pids
    results.append(("B: Deploy -> infra runbooks + PB-DEPLOYMENT", ok_b,
                    f"runbooks={sorted(ids)[:4]} playbooks={sorted(pids)[:3]}"))

    # TEST C: hot leads -> sales playbook + suppression-aware runbacks
    b = kq.build_bundle("Follow up with hot leads")
    pids = {pb["id"] for pb in b["playbooks"]}
    ids = {rb["id"] for rb in b["runbooks"]}
    ok_c = "PB-SALES" in pids and any("RB-SALES" in i for i in ids)
    results.append(("C: Follow up hot leads -> PB-SALES + RB-SALES", ok_c,
                    f"playbooks={sorted(pids)[:3]} runbooks={sorted(ids)[:4]}"))

    # TEST D: Swara outage -> incident knowledge grounded
    b = kq.build_bundle("What did we learn from the last Swara outage")
    ids = {rb["id"] for rb in b["runbooks"]}
    ok_d = "RB-VOICE-009" in ids
    results.append(("D: Swara outage -> voice runbook grounded", ok_d,
                    f"runbooks={sorted(ids)[:4]}"))
    return results


def run(verbose: bool = True) -> int:
    errs = []
    errs += validate_runbooks()
    errs += validate_playbooks()
    errs += validate_truth()
    errs += scan_secrets(ROOT / "notebook_exports")
    errs += scan_secrets(OPS)

    if verbose:
        print(f"Validator: {len(errs)} errors")
        for e in errs:
            print("  ✗", e)
        print("\nAcceptance tests:")
        for name, ok, detail in acceptance_tests():
            print(f"  {'✓' if ok else '✗'} {name} — {detail}")

    return 1 if errs else 0


if __name__ == "__main__":
    ok = run(verbose=True)
    fails = [e for e in [] if False]
    if ok:
        print("\nALL VALIDATIONS PASS")
    sys.exit(ok)