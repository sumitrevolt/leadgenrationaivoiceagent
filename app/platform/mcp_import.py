"""Small helpers for truthful optional fastapi-mcp import diagnostics."""

from __future__ import annotations


def describe_mcp_import_failure(error: ImportError) -> tuple[str, str]:
    """Return logger level and a safe message for an MCP import failure."""
    missing_module = getattr(error, "name", "") or ""
    if missing_module == "fastapi_mcp":
        return "info", "fastapi-mcp not installed — MCP exposure disabled"

    dependency = missing_module or type(error).__name__
    return (
        "warning",
        "fastapi-mcp dependency import failed "
        f"(missing module: {dependency}) — MCP exposure disabled",
    )


def mcp_gate_kind(*, token_configured: bool, allowlist_configured: bool) -> str:
    """Describe the active MCP access gate without overstating protection."""
    if token_configured:
        return "token"
    if allowlist_configured:
        return "ip-allowlist"
    return "development-ungated"


__all__ = ["describe_mcp_import_failure", "mcp_gate_kind"]
