"""Offline, deterministic policy proof for the hardened DSH source build."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DSH_DIR = ROOT / "deploy" / "dsh"
DEFAULT_OUTPUT = ROOT / "docs" / "evidence" / "DSH_SUPPLY_CHAIN_STATIC_20260814.json"

REQUIRED_PLUGINS = {
    "@deepseek-ai/dsh-agent",
    "@deepseek-ai/dsh-agent-loop",
    "@deepseek-ai/dsh-invariants",
    "@deepseek-ai/dsh-llm",
    "@deepseek-ai/dsh-llm-pi-ai",
    "@deepseek-ai/dsh-llm-retry",
    "@deepseek-ai/dsh-mcp-client",
    "@deepseek-ai/dsh-sdk-jsonrpc-server",
    "@deepseek-ai/dsh-session",
    "@deepseek-ai/dsh-system-prompt",
    "@deepseek-ai/dsh-tools",
}
REQUIRED_DEPENDENCIES = {
    "@deepseek-ai/dsh-agent",
    "@deepseek-ai/dsh-agent-loop",
    "@deepseek-ai/dsh-llm",
    "@deepseek-ai/dsh-llm-pi-ai",
    "@deepseek-ai/dsh-llm-retry",
    "@deepseek-ai/dsh-mcp-client",
    "@deepseek-ai/dsh-sdk-jsonrpc-demo",
    "@deepseek-ai/dsh-sdk-jsonrpc-server",
    "@deepseek-ai/dsh-sdk-protocol",
    "@deepseek-ai/dsh-session",
    "@deepseek-ai/dsh-tools",
}
# Cordis YAML may only reference the three runtime gateway/token vars.
CORDIS_ENV_NAMES = {"DSH_RUN_TOKEN", "DSH_LLM_BASE_URL", "DSH_MCP_URL"}
# Worker child process also carries bootstrap config + scratch HOME (pkg SEA).
ALLOWED_CHILD_ENV = CORDIS_ENV_NAMES | {"DSH_CORDIS_CONFIG", "HOME"}
FORBIDDEN_PACKAGE = re.compile(
    r"^@deepseek-ai/dsh-(?:"
    r"bash|browser|fs-local|fs-sandbox|jobs|scheduler|session-telemetry|skill|"
    r"subagent|terminal|tool-bash|tool-fs|tool-jobs|tool-skill|tool-subagent|"
    r"tool-web|web(?:-|$)|llm-deepseek"
    r")"
)


class DshSupplyChainError(RuntimeError):
    """Static DSH supply-chain contract violation."""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    # Text proofs must be CRLF-invariant so Windows worktrees match Linux CI.
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DshSupplyChainError(message)


def build_proof(root: Path = ROOT) -> dict[str, Any]:
    dsh_dir = root / "deploy" / "dsh"
    lock_path = dsh_dir / "upstream.lock.json"
    manifest_path = dsh_dir / "runtime.package.json"
    cordis_path = dsh_dir / "cordis.yml"
    patch_path = dsh_dir / "hardening.patch"
    dockerfile_path = dsh_dir / "Dockerfile"
    worker_dockerfile_path = dsh_dir / "worker.Dockerfile"
    gateway_dockerfile_path = dsh_dir / "test-gateway.Dockerfile"
    verifier_path = dsh_dir / "verify_runtime.mjs"
    normalizer_path = dsh_dir / "normalize_sea_binary.py"
    requirements_path = root / "requirements-dsh.lock.txt"
    workflow_path = root / ".github" / "workflows" / "dsh-runtime.yml"
    smoke_path = root / "scripts" / "dsh_runtime_smoke.py"
    assembler_path = root / "scripts" / "assemble_dsh_ci_evidence.py"
    fake_gateway_path = root / "tests" / "fixtures" / "dsh_fake_gateway.py"
    compose_path = root / "docker-compose.vps.yml"
    dsh_jobs_path = root / "app" / "tasks" / "dsh_jobs.py"

    for path in (
        lock_path,
        manifest_path,
        cordis_path,
        patch_path,
        dockerfile_path,
        worker_dockerfile_path,
        gateway_dockerfile_path,
        verifier_path,
        normalizer_path,
        requirements_path,
        workflow_path,
        smoke_path,
        assembler_path,
        fake_gateway_path,
        compose_path,
        dsh_jobs_path,
    ):
        _require(path.is_file(), f"required DSH build input missing: {path.relative_to(root)}")

    lock = json.loads(_read(lock_path))
    manifest = json.loads(_read(manifest_path))
    dependencies = set(manifest.get("dependencies", {}))
    _require(REQUIRED_DEPENDENCIES <= dependencies, "hardened runtime is missing required packages")
    forbidden_dependencies = sorted(name for name in dependencies if FORBIDDEN_PACKAGE.search(name))
    _require(
        not forbidden_dependencies, f"forbidden runtime dependencies: {forbidden_dependencies}"
    )
    _require(
        all(version == "workspace:^" for version in manifest["dependencies"].values()),
        "runtime workspace dependencies must use workspace:^",
    )

    cordis = _read(cordis_path)
    plugins = re.findall(r"^\s*name:\s*['\"]([^'\"]+)['\"]\s*$", cordis, flags=re.MULTILINE)
    _require(set(plugins) == REQUIRED_PLUGINS, "Cordis plugin set differs from hardened allowlist")
    _require(len(plugins) == len(set(plugins)), "Cordis contains duplicate plugin rows")
    cordis_env = set(re.findall(r"process\.env\.([A-Z][A-Z0-9_]*)", cordis))
    _require(cordis_env == CORDIS_ENV_NAMES, "Cordis child environment references changed")

    patch = _read(patch_path)
    for required_removal in (
        "-import * as LlmDeepSeek from '@deepseek-ai/dsh-llm-deepseek'",
        "-import type SubagentRuntime from '@deepseek-ai/dsh-subagent'",
        '-    "@deepseek-ai/dsh-llm-deepseek": "workspace:^",',
        '-    "@deepseek-ai/dsh-subagent": "workspace:^",',
    ):
        _require(required_removal in patch, f"hardening patch lacks removal: {required_removal}")

    dockerfile = _read(dockerfile_path)
    for field in (
        "commit",
        "tree",
        "git_archive_sha256",
        "source_date_epoch",
        "node_image",
        "runtime_image",
        "pnpm",
    ):
        _require(
            str(lock[field]) in dockerfile, f"Dockerfile does not bind upstream lock field: {field}"
        )
    _require("USER 65532:65532" in dockerfile, "final DSH image must run non-root")
    _require(
        "pnpm install --frozen-lockfile --ignore-scripts" in dockerfile,
        "upstream install must be frozen and ignore lifecycle scripts",
    )
    _require("git apply --check" in dockerfile, "source hardening patch must fail closed")
    _require("verify_runtime.mjs" in dockerfile, "final dependency closure must be scanned")
    _require(
        "/tmp/pkg-sea-dsh000/sea-main.js" in dockerfile  # nosec B108 -- literal proof marker
        and "expected one pkg SEA temp path" in dockerfile,
        "pkg SEA random build path must be normalized fail-closed",
    )
    _require(
        "DSH_CORDIS_CONFIG=/usr/local/bin/cordis.yml" in dockerfile,
        "packaged runtime must pin Cordis under /usr/local/bin (pkg-visible path)",
    )
    worker_dockerfile = _read(worker_dockerfile_path)
    _require(
        "DSH_CORDIS_CONFIG=/usr/local/bin/cordis.yml" in worker_dockerfile,
        "DSH worker must pin the same Cordis path as the runtime image",
    )
    _require("USER 65532:65532" in worker_dockerfile, "DSH worker must run non-root")
    _require(
        "requirements-dsh.lock.txt" in worker_dockerfile and "--no-deps" in worker_dockerfile,
        "DSH worker must use its exact isolated Python lock",
    )
    _require(
        "/usr/local/bin/dsh-jsonrpc-agent" in worker_dockerfile,
        "DSH worker image must copy only the verified runtime artifact",
    )
    compose = _read(compose_path)
    _require("dsh_net:" in compose and "internal: true" in compose, "DSH network must be internal")
    dsh_service = compose.split("\n  dsh-worker:", 1)[-1].split("\n  scheduler:", 1)[0]
    for hardening_line in ("read_only: true", "cap_drop: [ALL]", "no-new-privileges:true"):
        _require(hardening_line in dsh_service, f"DSH worker compose lacks {hardening_line}")
    _require("env_file:" not in dsh_service, "DSH worker must not inherit the application env file")
    child_env_source = _read(dsh_jobs_path)
    child_env_match = re.search(
        r"CHILD_ENV_NAMES\s*=\s*frozenset\(\s*\{([^}]+)\}\s*\)",
        child_env_source,
        flags=re.DOTALL,
    )
    _require(child_env_match is not None, "DSH child env allowlist declaration missing")
    discovered_child_env = set(re.findall(r'"([A-Z][A-Z0-9_]*)"', child_env_match.group(1)))
    _require(
        discovered_child_env == ALLOWED_CHILD_ENV,
        "DSH worker child environment names changed",
    )
    workflow = _read(workflow_path)
    _require(
        "docker build --no-cache" in workflow, "Linux CI must perform independent no-cache builds"
    )
    _require(
        "--binary-a" in workflow and "--binary-b" in workflow,
        "Linux CI must compare the extracted executable artifacts",
    )
    _require(
        "docker_internal_only" in _read(assembler_path),
        "CI evidence must require internal-only egress",
    )
    _require("--internal" in _read(smoke_path), "runtime smoke network must be Docker-internal")
    _require(
        "hard_cancellation_seconds" in _read(smoke_path),
        "runtime smoke must record hard cancellation",
    )

    requirements = [
        line.strip()
        for line in _read(requirements_path).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    _require(
        all("==" in line for line in requirements), "requirements-dsh.lock.txt must be exact-pinned"
    )
    _require(
        not any(
            "deepseek" in line.lower() or "git+" in line.lower() or "://" in line
            for line in requirements
        ),
        "DSH Python lock must not install the stock SDK/wheel or a VCS dependency",
    )

    for field, length in (("commit", 40), ("tree", 40), ("git_archive_sha256", 64)):
        value = str(lock[field])
        _require(
            len(value) == length and re.fullmatch(r"[0-9a-f]+", value) is not None,
            f"invalid {field}",
        )
    _require(lock["upstream_license"] == "MIT", "upstream licence changed")

    input_paths = (
        lock_path,
        manifest_path,
        cordis_path,
        patch_path,
        dockerfile_path,
        worker_dockerfile_path,
        gateway_dockerfile_path,
        verifier_path,
        normalizer_path,
        requirements_path,
        workflow_path,
        smoke_path,
        assembler_path,
        fake_gateway_path,
        compose_path,
        dsh_jobs_path,
    )
    return {
        "schema_version": 1,
        "evidence_label": "STATIC_VERIFIED",
        "runtime_state": "INERT_NOT_BUILT",
        "upstream": {
            "repository": lock["repository"],
            "commit": lock["commit"],
            "tree": lock["tree"],
            "git_archive_sha256": lock["git_archive_sha256"],
            "git_archive_bytes": lock["git_archive_bytes"],
            "source_date_epoch": lock["source_date_epoch"],
            "license": lock["upstream_license"],
        },
        "closure": {
            "dependency_count": len(dependencies),
            "required_plugins": sorted(REQUIRED_PLUGINS),
            "forbidden_dependencies": forbidden_dependencies,
            "child_env_names": sorted(ALLOWED_CHILD_ENV),
            "cordis_env_names": sorted(CORDIS_ENV_NAMES),
        },
        "input_sha256": {
            str(path.relative_to(root)).replace("\\", "/"): _sha256(path) for path in input_paths
        },
        "unverified_until_linux_ci": [
            "source_build",
            "binary_reproducibility",
            "final_image_sbom_and_licences",
            "fake_model_and_mcp_smoke",
            "clean_shutdown",
            "hard_cancellation_under_5_seconds",
            "isolated_network_egress",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="verify without writing evidence")
    args = parser.parse_args()
    proof = build_proof()
    if not args.check:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{json.dumps(proof, indent=2, sort_keys=True)}\n", encoding="utf-8")
    print(
        "DSH_SUPPLY_CHAIN_STATIC_OK "
        f"commit={proof['upstream']['commit'][:12]} "
        f"deps={proof['closure']['dependency_count']} "
        f"plugins={len(proof['closure']['required_plugins'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
