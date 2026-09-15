#!/usr/bin/env python3
"""Hermes integration CONTRACT harness (read-only, no GUI, no network by default).

WHY THIS EXISTS
---------------
Hermes is a **local Windows desktop app**. GitHub-hosted runners are Linux, so no
runner can launch the Hermes GUI or reach its loopback ports (9119 / 20128). A
workflow that pretended to "test Hermes" by launching it would be permanently red or
permanently skipped — worse than nothing.

So this harness verifies the part that IS verifiable from anywhere: the **integration
surface contract** that the desktop depends on and that a bad commit can silently break:

  1. Every Hermes profile has BOTH ``profile.yaml`` and ``config.yaml`` (a profile with
     no config cannot route).
  2. Every ``config.yaml`` pins the ONE gateway contract: provider ``omniroute``,
     base_url ``http://127.0.0.1:20128/v1``, key_env ``OMNIROUTE_API_KEY``.
  3. Every ``config.yaml`` ``model.default`` is a REAL OmniRoute identifier — either a
     canonical ``leadsgen combo N`` or a known legacy alias from
     ``app/platform/omniroute_aliases.py``. An unknown model id is a hard failure
     (fail-closed: never silently invent a route).
  4. The port contract in the launcher scripts matches the documented constants:
     Hermes backend = 9119, OmniRoute gateway = 20128.
  5. ``docs/hermes/mcp_servers.json`` parses and still declares the ``leadgen_admin_harness``
     MCP server the desktop cockpit depends on.

WHAT IT DOES **NOT** PROVE (honest scope)
-----------------------------------------
* It does NOT prove Hermes launches, serves, or answers. That needs a Windows host.
* It does NOT prove 9119/20128 are listening — they are loopback-only on the owner's
  machine and on the VPS respectively, unreachable from a Linux runner.
* The optional ``--check-prod`` leg only proves the public health-triple leg
  (``https://leadsgenai.in/health``) answers; the other two legs are out of reach here.

Exit 0 = contract intact. Exit 1 = drift (details printed). No secrets are read.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - CI installs pyyaml explicitly
    print("FATAL: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    raise SystemExit(2)

REPO = pathlib.Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO / "docs" / "hermes" / "profiles"
MCP_SERVERS = REPO / "docs" / "hermes" / "mcp_servers.json"
START_SCRIPT = REPO / "scripts" / "start-hermes-omniroute.ps1"
ENSURE_SCRIPT = REPO / "scripts" / "ensure-hermes-backend.ps1"
ALIASES_MODULE = REPO / "app" / "platform" / "omniroute_aliases.py"

# The documented port contract (HERMES_CONTROL_PLANE.md + the launcher scripts).
GATEWAY_BASE_URL = "http://127.0.0.1:20128/v1"
GATEWAY_PORT = 20128
BACKEND_PORT = 9119

failures: list[str] = []
notes: list[str] = []


def _load_aliases() -> dict[str, int]:
    """Load LEGACY_ALIASES by file path — avoids importing the app package graph."""
    spec = importlib.util.spec_from_file_location("_hermes_aliases", ALIASES_MODULE)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise SystemExit(f"FATAL: cannot load {ALIASES_MODULE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(getattr(mod, "LEGACY_ALIASES", {}))


def _check_model_resolvable(name: str, model: str, aliases: dict[str, int]) -> None:
    canonical = re.match(r"^leadsgen combo (\d+)$", str(model).strip(), re.IGNORECASE)
    if canonical:
        n = int(canonical.group(1))
        if not 1 <= n <= 14:
            failures.append(f"{name}: model.default '{model}' has an out-of-range combo index")
        return
    if str(model).strip().lower() in aliases:
        return
    failures.append(
        f"{name}: model.default '{model}' is not a known OmniRoute alias and not "
        f"'leadsgen combo N' — refusing to invent a route (fail-closed)"
    )


def check_profiles() -> None:
    if not PROFILES_DIR.is_dir():
        failures.append(f"profiles dir missing: {PROFILES_DIR}")
        return
    aliases = _load_aliases()
    dirs = sorted(p for p in PROFILES_DIR.iterdir() if p.is_dir())
    if not dirs:
        failures.append(f"no profile directories under {PROFILES_DIR}")
        return
    notes.append(f"profiles discovered: {len(dirs)}")
    for d in dirs:
        name = d.name
        prof = d / "profile.yaml"
        cfg = d / "config.yaml"
        if not prof.is_file():
            failures.append(f"{name}: missing profile.yaml")
        else:
            try:
                data = yaml.safe_load(prof.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    failures.append(f"{name}: profile.yaml is not a mapping")
            except yaml.YAMLError as e:
                failures.append(f"{name}: profile.yaml does not parse ({e.__class__.__name__})")
        if not cfg.is_file():
            failures.append(f"{name}: missing config.yaml (profile cannot route)")
            continue
        try:
            c = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            failures.append(f"{name}: config.yaml does not parse ({e.__class__.__name__})")
            continue
        if not isinstance(c, dict):
            failures.append(f"{name}: config.yaml is not a mapping")
            continue
        model = (c.get("model") or {}) if isinstance(c.get("model"), dict) else {}
        if model.get("provider") != "omniroute":
            failures.append(f"{name}: model.provider must be 'omniroute' (got {model.get('provider')!r})")
        if model.get("base_url") != GATEWAY_BASE_URL:
            failures.append(f"{name}: model.base_url must be {GATEWAY_BASE_URL} (got {model.get('base_url')!r})")
        if model.get("key_env") != "OMNIROUTE_API_KEY":
            failures.append(f"{name}: model.key_env must be 'OMNIROUTE_API_KEY' (got {model.get('key_env')!r})")
        default = model.get("default")
        if not default:
            failures.append(f"{name}: model.default is empty")
        else:
            _check_model_resolvable(name, str(default), aliases)
        prov = ((c.get("providers") or {}).get("omniroute") or {}) if isinstance(c.get("providers"), dict) else {}
        if prov and prov.get("base_url") != GATEWAY_BASE_URL:
            failures.append(
                f"{name}: providers.omniroute.base_url must be {GATEWAY_BASE_URL} (got {prov.get('base_url')!r})"
            )


def check_port_contract() -> None:
    """Assert the launcher scripts still declare the documented 9119 / 20128 ports."""
    if not START_SCRIPT.is_file():
        failures.append(f"missing launcher: {START_SCRIPT.name}")
    else:
        t = START_SCRIPT.read_text(encoding="utf-8", errors="replace")
        m_port = re.search(r"\$Port\s*=\s*(\d+)", t)
        m_back = re.search(r"\$BackendPort\s*=\s*(\d+)", t)
        if not m_port or int(m_port.group(1)) != GATEWAY_PORT:
            failures.append(f"{START_SCRIPT.name}: $Port must be {GATEWAY_PORT} (got {m_port and m_port.group(1)})")
        if not m_back or int(m_back.group(1)) != BACKEND_PORT:
            failures.append(f"{START_SCRIPT.name}: $BackendPort must be {BACKEND_PORT} (got {m_back and m_back.group(1)})")
    if not ENSURE_SCRIPT.is_file():
        failures.append(f"missing launcher: {ENSURE_SCRIPT.name}")
    else:
        t = ENSURE_SCRIPT.read_text(encoding="utf-8", errors="replace")
        m_port = re.search(r"\$Port\s*=\s*(\d+)", t)
        if not m_port or int(m_port.group(1)) != BACKEND_PORT:
            failures.append(f"{ENSURE_SCRIPT.name}: $Port must be {BACKEND_PORT} (got {m_port and m_port.group(1)})")
        if "9119" not in t:
            failures.append(f"{ENSURE_SCRIPT.name}: documented backend port 9119 not referenced")


def check_mcp_servers() -> None:
    if not MCP_SERVERS.is_file():
        failures.append(f"missing {MCP_SERVERS.name}")
        return
    try:
        data = json.loads(MCP_SERVERS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        failures.append(f"mcp_servers.json does not parse ({e.__class__.__name__})")
        return
    servers = (data or {}).get("mcpServers") or {}
    if not isinstance(servers, dict) or not servers:
        failures.append("mcp_servers.json: 'mcpServers' missing or empty")
        return
    if "leadgen_admin_harness" not in servers:
        failures.append("mcp_servers.json: 'leadgen_admin_harness' MCP server is missing (owner cockpit depends on it)")
    notes.append(f"mcp servers declared: {', '.join(sorted(servers))}")


def check_prod_health() -> None:
    """Optional: the ONLY health-triple leg reachable from a Linux runner."""
    import time
    import urllib.error
    import urllib.request

    url = "https://leadsgenai.in/health"
    last = ""
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 - fixed https URL
                body = r.read(2000).decode("utf-8", "replace")
                if r.status == 200 and '"version"' in body:
                    ver = re.search(r'"version"\s*:\s*"([^"]+)"', body)
                    notes.append(f"prod health OK (attempt {attempt}): version={ver.group(1) if ver else '?'}")
                    return
                last = f"status={r.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e.__class__.__name__
        time.sleep(min(2 ** attempt, 10))
    failures.append(f"prod health {url} unreachable after 5 attempts (last: {last})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check-prod", action="store_true", help="also probe https://leadsgenai.in/health")
    args = ap.parse_args(argv)

    check_profiles()
    check_port_contract()
    check_mcp_servers()
    if args.check_prod:
        check_prod_health()

    print("=== Hermes integration contract harness ===")
    for n in notes:
        print(f"  note : {n}")
    if failures:
        print(f"\nFAIL — {len(failures)} contract drift item(s):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\nOK — Hermes integration contract intact.")
    print("  scope: profile/config schema + port contract + MCP surface.")
    print("  NOT proven here: GUI launch, live 9119/20128 listeners (loopback-only, need a Windows host).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
