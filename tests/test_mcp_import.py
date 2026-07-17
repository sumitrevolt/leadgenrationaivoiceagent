import importlib.util
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "app" / "platform" / "mcp_import.py"
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
    assert (
        mcp_gate_kind(token_configured=False, allowlist_configured=True)
        == "ip-allowlist"
    )
