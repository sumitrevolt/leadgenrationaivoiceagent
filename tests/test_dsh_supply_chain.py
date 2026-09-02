from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from deploy.dsh.normalize_sea_binary import REPLACEMENT, normalize
from scripts.assemble_dsh_ci_evidence import EvidenceFailure, assemble, assemble_blocked
from scripts.verify_dsh_supply_chain import ALLOWED_CHILD_ENV, REQUIRED_PLUGINS, build_proof

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "docs" / "evidence" / "DSH_SUPPLY_CHAIN_STATIC_20260814.json"


def _pins(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==", 1)
        result[name.lower().replace("-", "_")] = version
    return result


def test_static_supply_chain_evidence_is_deterministic() -> None:
    generated = build_proof(ROOT)
    stored = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert generated == stored
    assert stored["evidence_label"] == "STATIC_VERIFIED"
    assert stored["runtime_state"] == "INERT_NOT_BUILT"
    assert stored["closure"]["forbidden_dependencies"] == []
    assert set(stored["closure"]["required_plugins"]) == REQUIRED_PLUGINS
    assert set(stored["closure"]["child_env_names"]) == ALLOWED_CHILD_ENV


def test_input_sha256_is_crlf_invariant(tmp_path: Path) -> None:
    from scripts.verify_dsh_supply_chain import _sha256

    lf = tmp_path / "lf.txt"
    crlf = tmp_path / "crlf.txt"
    lf.write_bytes(b"alpha\nbeta\n")
    crlf.write_bytes(b"alpha\r\nbeta\r\n")
    assert _sha256(lf) == _sha256(crlf)


def test_dsh_worker_lock_is_an_exact_subset_of_canonical_lock() -> None:
    canonical = _pins(ROOT / "requirements.lock.txt")
    isolated = _pins(ROOT / "requirements-dsh.lock.txt")
    assert isolated
    assert isolated.items() <= canonical.items()
    assert "deepseek_harness" not in isolated


def test_dsh_worker_lock_closure_covers_app_config_imports() -> None:
    """Regression: 2026-08-15 the dsh worker cancelled EVERY run_dsh_workforce.

    Root cause: `requirements-dsh.lock.txt` lacked `pydantic-settings` (and its
    `python-dotenv` import-time dep) → `from app.config import settings` inside
    `agent_runtime_cancellation._sync_redis()` raised ModuleNotFoundError →
    fail-closed `cancellation_store_unavailable` → all 29 armed agents executed
    nothing for 12h+. The lock closure MUST keep both pins in sync with the
    canonical lock so `app/config.py` imports inside the isolated worker.
    """
    canonical = _pins(ROOT / "requirements.lock.txt")
    isolated = _pins(ROOT / "requirements-dsh.lock.txt")
    assert canonical["pydantic_settings"] == "2.15.0"
    assert canonical["python_dotenv"] == "1.2.2"
    assert isolated["pydantic_settings"] == canonical["pydantic_settings"]
    assert isolated["python_dotenv"] == canonical["python_dotenv"]
    for module_name in ("pydantic_settings", "python_dotenv"):
        assert module_name in isolated


def test_final_runtime_image_has_no_shell_or_package_manager_stage() -> None:
    dockerfile = (ROOT / "deploy" / "dsh" / "Dockerfile").read_text(encoding="utf-8")
    assert "/tmp/pkg-sea-dsh000/sea-main.js" in dockerfile
    assert "matches.length !== 1" in dockerfile
    final = dockerfile.split(" AS runtime", 1)[1]
    assert "USER 65532:65532" in final
    assert "ENTRYPOINT" in final
    assert "apt-get" not in final
    assert "pnpm" not in final
    assert "npm " not in final
    assert "curl " not in final
    assert "wget " not in final


def test_pkg_sea_normalizer_is_exact_and_fail_closed(tmp_path: Path) -> None:
    binary = tmp_path / "dsh"
    binary.write_bytes(b"prefix/tmp/pkg-sea-Ab12z9/sea-main.jssuffix")
    assert normalize(binary) == 1
    assert binary.read_bytes() == b"prefix" + REPLACEMENT + b"suffix"

    with pytest.raises(SystemExit, match="expected exactly one"):
        normalize(binary)


def test_linux_evidence_assembler_requires_reproducible_binaries(tmp_path: Path) -> None:
    binary_a = tmp_path / "dsh-a"
    binary_b = tmp_path / "dsh-b"
    binary_a.write_bytes(b"same executable")
    binary_b.write_bytes(b"same executable")
    executable_sha256 = hashlib.sha256(binary_a.read_bytes()).hexdigest()
    proof = {
        "binary_sha256": executable_sha256,
        "forbidden_packages": [],
        "workspace_packages": [{"name": "@deepseek-ai/dsh-agent", "license": "MIT"}],
        "licences": ["MIT"],
    }
    proof_a = tmp_path / "runtime-proof-a.json"
    proof_b = tmp_path / "runtime-proof-b.json"
    sbom = tmp_path / "runtime-sbom.json"
    smoke = tmp_path / "runtime-smoke.json"
    proof_a.write_text(json.dumps(proof), encoding="utf-8")
    proof_b.write_text(json.dumps(proof), encoding="utf-8")
    sbom.write_text(
        json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "runtime"}]}),
        encoding="utf-8",
    )
    smoke.write_text(
        json.dumps(
            {
                "network_mode": "docker_internal_only",
                "fake_model": "passed",
                "fake_mcp": "passed",
                "clean_shutdown_seconds": 0.2,
                "hard_cancellation_seconds": 0.3,
                "child_env_names": ["DSH_RUN_TOKEN"],
            }
        ),
        encoding="utf-8",
    )

    evidence = assemble(
        runtime_proof_a=proof_a,
        runtime_proof_b=proof_b,
        binary_a_path=binary_a,
        binary_b_path=binary_b,
        sbom_path=sbom,
        smoke_path=smoke,
    )
    assert evidence["evidence_label"] == "LINUX_CI_VERIFIED"
    assert evidence["reproducibility"]["status"] == "BIT_FOR_BIT_REPRODUCIBLE"
    assert evidence["reproducibility"]["bit_identical"] is True
    assert evidence["reproducibility"]["executable_sha256"] == executable_sha256

    binary_b.write_bytes(b"different executable")
    changed_sha256 = hashlib.sha256(binary_b.read_bytes()).hexdigest()
    proof_b.write_text(json.dumps({**proof, "binary_sha256": changed_sha256}), encoding="utf-8")
    with pytest.raises(EvidenceFailure, match="different executable hashes"):
        assemble(
            runtime_proof_a=proof_a,
            runtime_proof_b=proof_b,
            binary_a_path=binary_a,
            binary_b_path=binary_b,
            sbom_path=sbom,
            smoke_path=smoke,
        )
    blocked = assemble_blocked(
        reason="independent Linux builds produced different executable hashes",
        runtime_proof_a=proof_a,
        runtime_proof_b=proof_b,
        binary_a_path=binary_a,
        binary_b_path=binary_b,
        sbom_path=sbom,
        smoke_path=smoke,
    )
    assert blocked["evidence_label"] == "LINUX_CI_BLOCKED"
    assert blocked["runtime_state"] == "INERT_SHADOW_BLOCKED"
    assert blocked["reproducibility"]["bit_identical"] is False
    assert blocked["reproducibility"]["closure_proofs_equal"] is True
    assert blocked["security_observed"]["sbom_component_count"] == 1
    assert blocked["lifecycle_observed"]["hard_cancellation_seconds"] == 0.3
    assert blocked["shadow_must_not_proceed"] is True

    proof_b.write_text(json.dumps(proof), encoding="utf-8")
    with pytest.raises(EvidenceFailure, match="does not match extracted artifact"):
        assemble(
            runtime_proof_a=proof_a,
            runtime_proof_b=proof_b,
            binary_a_path=binary_a,
            binary_b_path=binary_b,
            sbom_path=sbom,
            smoke_path=smoke,
        )
