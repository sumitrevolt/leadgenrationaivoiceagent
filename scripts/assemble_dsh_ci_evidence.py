"""Fail-closed assembler for Linux DSH build, SBOM, lifecycle, and reproducibility evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


class EvidenceFailure(RuntimeError):
    """A required DSH Linux proof is absent or invalid."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvidenceFailure(f"evidence is not an object: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble(
    *,
    runtime_proof_a: Path,
    runtime_proof_b: Path,
    binary_a_path: Path,
    binary_b_path: Path,
    sbom_path: Path,
    smoke_path: Path,
) -> dict[str, Any]:
    proof_a = _load(runtime_proof_a)
    proof_b = _load(runtime_proof_b)
    smoke = _load(smoke_path)
    sbom = _load(sbom_path)

    claimed_binary_a = proof_a.get("binary_sha256")
    claimed_binary_b = proof_b.get("binary_sha256")
    binary_a = _sha256(binary_a_path)
    binary_b = _sha256(binary_b_path)
    if claimed_binary_a != binary_a or claimed_binary_b != binary_b:
        raise EvidenceFailure("runtime proof executable hash does not match extracted artifact")
    if binary_a != binary_b:
        raise EvidenceFailure("independent Linux builds produced different executable hashes")
    if proof_a.get("forbidden_packages") != [] or proof_b.get("forbidden_packages") != []:
        raise EvidenceFailure("runtime closure contains a forbidden package")
    closure_a = {key: value for key, value in proof_a.items() if key != "binary_sha256"}
    closure_b = {key: value for key, value in proof_b.items() if key != "binary_sha256"}
    if not proof_a.get("workspace_packages") or closure_a != closure_b:
        raise EvidenceFailure("independent runtime closure proofs differ")

    components = sbom.get("components")
    if sbom.get("bomFormat") != "CycloneDX" or not isinstance(components, list) or not components:
        raise EvidenceFailure("final-image CycloneDX SBOM is empty or invalid")
    licences = proof_a.get("licences")
    if not isinstance(licences, list) or not licences:
        raise EvidenceFailure("runtime closure licence proof is empty")

    for field in ("fake_model", "fake_mcp"):
        if smoke.get(field) != "passed":
            raise EvidenceFailure(f"runtime smoke did not pass: {field}")
    if smoke.get("network_mode") != "docker_internal_only":
        raise EvidenceFailure("runtime smoke did not use an internal-only network")
    for field in ("clean_shutdown_seconds", "hard_cancellation_seconds"):
        value = smoke.get(field)
        if not isinstance(value, int | float) or value > 5:
            raise EvidenceFailure(f"runtime lifecycle bound failed: {field}")

    return {
        "schema_version": 1,
        "evidence_label": "LINUX_CI_VERIFIED",
        "runtime_state": "INERT_NOT_ARMED",
        "reproducibility": {
            "independent_builds": 2,
            "status": "BIT_FOR_BIT_REPRODUCIBLE",
            "bit_identical": True,
            "executable_sha256": binary_a,
            "closure_proofs_equal": True,
            "normalized_nondeterminism": ["pkg_sea_mkdtemp_suffix"],
        },
        "security": {
            "forbidden_packages": [],
            "licences": sorted(str(item) for item in licences),
            "sbom_format": "CycloneDX",
            "sbom_component_count": len(components),
            "network_mode": smoke["network_mode"],
            "child_env_names": smoke.get("child_env_names", []),
        },
        "lifecycle": {
            "fake_model": "passed",
            "fake_mcp": "passed",
            "clean_shutdown_seconds": smoke["clean_shutdown_seconds"],
            "hard_cancellation_seconds": smoke["hard_cancellation_seconds"],
        },
        "artifact_sha256": {
            runtime_proof_a.name: _sha256(runtime_proof_a),
            runtime_proof_b.name: _sha256(runtime_proof_b),
            sbom_path.name: _sha256(sbom_path),
            smoke_path.name: _sha256(smoke_path),
        },
    }


def assemble_blocked(
    *,
    reason: str,
    runtime_proof_a: Path,
    runtime_proof_b: Path,
    binary_a_path: Path,
    binary_b_path: Path,
    sbom_path: Path,
    smoke_path: Path,
) -> dict[str, Any]:
    """Render a durable blocker without converting a failed gate into success."""
    proof_a = _load(runtime_proof_a)
    proof_b = _load(runtime_proof_b)
    sbom = _load(sbom_path)
    smoke = _load(smoke_path)
    binary_a = _sha256(binary_a_path)
    binary_b = _sha256(binary_b_path)
    closure_a = {key: value for key, value in proof_a.items() if key != "binary_sha256"}
    closure_b = {key: value for key, value in proof_b.items() if key != "binary_sha256"}
    return {
        "schema_version": 1,
        "evidence_label": "LINUX_CI_BLOCKED",
        "runtime_state": "INERT_SHADOW_BLOCKED",
        "gate": "binary_reproducibility",
        "reason": reason,
        "reproducibility": {
            "independent_builds": 2,
            "status": "NOT_BIT_IDENTICAL",
            "bit_identical": binary_a == binary_b,
            "executable_sha256_a": binary_a,
            "executable_sha256_b": binary_b,
            "closure_proofs_equal": closure_a == closure_b,
            "normalized_nondeterminism": ["pkg_sea_mkdtemp_suffix"],
        },
        "owner_decision_required": (
            "accept_non_bit_identical_binary_with_content_addressed_closure_proof"
        ),
        "security_observed": {
            "forbidden_packages_a": proof_a.get("forbidden_packages"),
            "forbidden_packages_b": proof_b.get("forbidden_packages"),
            "licences": proof_a.get("licences"),
            "sbom_format": sbom.get("bomFormat"),
            "sbom_component_count": len(sbom.get("components") or []),
            "network_mode": smoke.get("network_mode"),
            "child_env_names": smoke.get("child_env_names"),
        },
        "lifecycle_observed": {
            "fake_model": smoke.get("fake_model"),
            "fake_mcp": smoke.get("fake_mcp"),
            "clean_shutdown_seconds": smoke.get("clean_shutdown_seconds"),
            "hard_cancellation_seconds": smoke.get("hard_cancellation_seconds"),
        },
        "shadow_must_not_proceed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-proof-a", type=Path, required=True)
    parser.add_argument("--runtime-proof-b", type=Path, required=True)
    parser.add_argument("--binary-a", type=Path, required=True)
    parser.add_argument("--binary-b", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--smoke", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        evidence = assemble(
            runtime_proof_a=args.runtime_proof_a,
            runtime_proof_b=args.runtime_proof_b,
            binary_a_path=args.binary_a,
            binary_b_path=args.binary_b,
            sbom_path=args.sbom,
            smoke_path=args.smoke,
        )
    except EvidenceFailure as exc:
        evidence = assemble_blocked(
            reason=str(exc),
            runtime_proof_a=args.runtime_proof_a,
            runtime_proof_b=args.runtime_proof_b,
            binary_a_path=args.binary_a,
            binary_b_path=args.binary_b,
            sbom_path=args.sbom,
            smoke_path=args.smoke,
        )
        # Never leave a prior LINUX_CI_VERIFIED claim at the requested output path.
        evidence["retracted_prior_claim"] = (
            "BIT_FOR_BIT_REPRODUCIBLE / LINUX_CI_VERIFIED must not be trusted "
            "when this blocker is present"
        )
        payload = f"{json.dumps(evidence, indent=2, sort_keys=True)}\n"
        args.output.write_text(payload, encoding="utf-8")
        blocker = args.output.with_name("DSH_LINUX_REPRODUCIBILITY_BLOCKED_20260814.json")
        if blocker.resolve() != args.output.resolve():
            blocker.write_text(payload, encoding="utf-8")
        print(f"DSH_LINUX_CI_EVIDENCE_BLOCKED reason={exc}", file=sys.stderr)
        return 1
    args.output.write_text(f"{json.dumps(evidence, indent=2, sort_keys=True)}\n", encoding="utf-8")
    print(
        "DSH_LINUX_CI_EVIDENCE_OK "
        f"components={evidence['security']['sbom_component_count']} "
        f"cancel={evidence['lifecycle']['hard_cancellation_seconds']}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
