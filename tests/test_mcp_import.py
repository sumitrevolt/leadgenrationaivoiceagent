import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[1] / "app" / "platform" / "mcp_import.py"
_REPO_ROOT = Path(__file__).parents[1]
_SPEC = importlib.util.spec_from_file_location("mcp_import_under_test", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
describe_mcp_import_failure = _MODULE.describe_mcp_import_failure
mcp_gate_kind = _MODULE.mcp_gate_kind


def test_describe_top_level_fastapi_mcp_missing():
    error = ModuleNotFoundError(
        "No module named 'fastapi_mcp'",
        name="fastapi_mcp",
    )

    level, message = describe_mcp_import_failure(error)

    assert level == "info"
    assert message == "fastapi-mcp not installed — MCP exposure disabled"


def test_describe_nested_dependency_missing_truthfully():
    error = ModuleNotFoundError(
        "No module named 'pywintypes'",
        name="pywintypes",
    )

    level, message = describe_mcp_import_failure(error)

    assert level == "warning"
    assert "fastapi-mcp dependency import failed" in message
    assert "pywintypes" in message
    assert "not installed" not in message


def test_mcp_gate_kind_reports_ungated_development_truthfully():
    assert mcp_gate_kind(token_configured=False, allowlist_configured=False) == (
        "development-ungated"
    )
    assert mcp_gate_kind(token_configured=True, allowlist_configured=False) == "token"
    assert mcp_gate_kind(token_configured=False, allowlist_configured=True) == "ip-allowlist"


@pytest.mark.parametrize(
    ("app_env", "expected_log", "unexpected_log"),
    [
        pytest.param(
            "development",
            "MCP server mounted at /mcp (gated: development-ungated",
            "MCP mount REFUSED",
            id="development-mounts",
        ),
        pytest.param(
            "production",
            "MCP mount REFUSED",
            "MCP server mounted at /mcp (gated: development-ungated",
            id="production-refuses",
        ),
    ],
)
def test_mcp_mount_follows_canonical_app_env(
    app_env: str,
    expected_log: str,
    unexpected_log: str,
):
    env = os.environ.copy()
    env["APP_ENV"] = app_env
    env["RUN_IN_PROCESS_SCHEDULER"] = "0"
    if app_env == "production":
        env["DEBUG"] = "0"
        env["SECRET_KEY"] = (
            "mcp-production-test-secret-0000000000000001"  # pragma: allowlist secret
        )
        env["JWT_SECRET_KEY"] = (
            "mcp-production-test-jwt-000000000000001"  # pragma: allowlist secret
        )
    for key in ("ENV", "FASTAPI_MCP_TOKEN", "MCP_IP_ALLOWLIST"):
        env.pop(key, None)

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    logs = result.stdout + result.stderr

    assert result.returncode == 0, logs[-4000:]
    assert expected_log in logs
    assert unexpected_log not in logs
