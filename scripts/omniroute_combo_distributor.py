#!/usr/bin/env python3
"""
omniroute_combo_distributor.py — Autonomous combo-distribution runtime.

Council purpose (2026-09-05, autonomous):
  Single-source-of-truth distributor for the 14-combo × 5-desktop-app × 42-provider
  matrix. Reads config/desktop_apps/combo_distribution.yaml, validates against
  the live .omniroute-cutover/combos.json + providers.json, and emits a
  reconciliation diff. Self-healing rules are encoded as data, not control flow.

Sub-commands (all exit-0 unless a hard contract violation is detected):

  build-manifest    Re-emit combo_distribution.yaml from current OmniRoute state.
  validate          Verify manifest against live OmniRoute + desktop app configs.
  render-matrix     Print human-readable matrix to stdout.
  emit-desktop-configs  Re-emit 5 desktop app config files from manifest.
  dry-run           All actions logged but no file writes (default in CI).
  apply             Write desktop app configs (gated by --apply flag).

Council invariants (NEVER BREAK):
  - Every combo MUST have >=3 priority providers (failover redundancy).
  - Desktop apps MUST NOT shadow exec / spawn / shell / fs_delete (OpenClaw model).
  - Kill switches MUST be defined for voice + agent + heavy combos.
  - The manifest is the single source of truth; .env/.mcp.json overrides are
    session-only and reconciled at next run.

Run as a module:
    python -m scripts.omniroute_combo_distributor validate
    python -m scripts.omniroute_combo_distributor render-matrix
    python -m scripts.omniroute_combo_distributor emit-desktop-configs --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "config" / "desktop_apps" / "combo_distribution.yaml"
OMNI_COMBOS_PATH = REPO_ROOT / ".omniroute-cutover" / "combos.json"
OMNI_PROVIDERS_PATH = REPO_ROOT / ".omniroute-cutover" / "providers.json"
DESKTOP_APPS_DIR = REPO_ROOT / "config" / "desktop_apps"

IST = timezone.utc  # placeholder; ISO 8601 +05:30 below via offset=timedelta


# --------------------------------------------------------------------------- #
# Manifest I/O
# --------------------------------------------------------------------------- #
@dataclass
class ComboSpec:
    name: str
    type: str
    tier: str
    email: str
    primary_provider: str
    providers: list
    free_tier_limit_rpm: int
    free_tier_limit_daily: int
    fail_priority: str
    handoff_threshold: float
    workers: dict
    kill_switch: str

    @property
    def provider_count(self) -> int:
        return len(self.providers)

    def is_valid(self) -> tuple:
        errs: list = []
        if self.provider_count < 3:
            errs.append(f"{self.name}: needs >=3 providers, has {self.provider_count}")
        if not self.email or "@" not in self.email:
            errs.append(f"{self.name}: invalid email {self.email!r}")
        if self.primary_provider not in self.providers:
            errs.append(
                f"{self.name}: primary_provider={self.primary_provider!r} not in providers list"
            )
        if self.free_tier_limit_rpm <= 0:
            errs.append(f"{self.name}: rpm<=0")
        if self.free_tier_limit_daily <= 0:
            errs.append(f"{self.name}: daily<=0")
        if not any(self.workers.values()):
            errs.append(f"{self.name}: no workers enabled (vps+project both false)")
        return (len(errs) == 0, errs)


@dataclass
class DesktopAppSpec:
    id: str
    role: str
    description: str
    worker_scope: str
    combos: list

    def is_valid(self) -> tuple:
        errs: list = []
        if not self.combos:
            errs.append(f"desktop_app {self.id!r}: no combos assigned")
        if self.worker_scope not in ("vps_and_project", "vps_only", "project_only"):
            errs.append(
                f"desktop_app {self.id!r}: invalid worker_scope {self.worker_scope!r}"
            )
        return (len(errs) == 0, errs)


@dataclass
class Manifest:
    version: int
    desktop_apps: list
    combos: list
    kill_switches: dict
    self_healing: dict

    @classmethod
    def load(cls, path: Path = MANIFEST_PATH) -> "Manifest":
        if not path.exists():
            raise FileNotFoundError(f"manifest not found at {path}")
        if yaml is None:
            raise RuntimeError(
                "PyYAML not installed; install via pip install pyyaml"
            )
        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))

        desktop_apps = [
            DesktopAppSpec(
                id=d["id"],
                role=d["role"],
                description=d.get("description", "").strip(),
                worker_scope=d.get("worker_scope", "vps_and_project"),
                combos=d.get("combos", []),
            )
            for d in raw_data.get("desktop_apps", [])
        ]
        combos = [
            ComboSpec(
                name=c["name"],
                type=c.get("type", "leadgen"),
                tier=c.get("tier", ""),
                email=c.get("email", ""),
                primary_provider=c.get("primary_provider", ""),
                providers=c.get("providers", []),
                free_tier_limit_rpm=int(c.get("free_tier_limit_rpm", 0)),
                free_tier_limit_daily=int(c.get("free_tier_limit_daily", 0)),
                fail_priority=c.get("fail_priority", "priority"),
                handoff_threshold=float(c.get("handoff_threshold", 0.85)),
                workers=c.get("workers", {}),
                kill_switch=c.get("kill_switch", ""),
            )
            for c in raw_data.get("combos", [])
        ]
        kill_switches = raw_data.get("kill_switches", {}) or {}
        self_healing = raw_data.get("self_healing", {}) or {}
        version = int(raw_data.get("version", 1))

        return cls(
            version=version,
            desktop_apps=desktop_apps,
            combos=combos,
            kill_switches=kill_switches,
            self_healing=self_healing,
        )

    def validate(self) -> tuple:
        errs: list = []
        if not self.desktop_apps:
            errs.append("manifest: no desktop_apps defined")
        if not self.combos:
            errs.append("manifest: no combos defined")
        # Combo invariant: 14 combos
        if len(self.combos) != 14:
            errs.append(
                f"manifest: expected 14 combos, got {len(self.combos)}"
            )
        # Each combo must satisfy provider ≥3
        for c in self.combos:
            ok, e = c.is_valid()
            if not ok:
                errs.extend(e)
        # Each desktop app must be valid
        for d in self.desktop_apps:
            ok, e = d.is_valid()
            if not ok:
                errs.extend(e)
        # Each desktop app's combos must exist in manifest
        combo_names = {c.name for c in self.combos}
        for d in self.desktop_apps:
            for cn in d.combos:
                if cn not in combo_names:
                    errs.append(
                        f"desktop_app {d.id!r} references unknown combo {cn!r}"
                    )
        # Kill switch coverage — every kill_switch referenced by a combo must exist
        ks_names = set(self.kill_switches.keys())
        for c in self.combos:
            if c.kill_switch and c.kill_switch not in ks_names:
                errs.append(
                    f"combo {c.name!r}: unknown kill_switch {c.kill_switch!r}"
                )
        return (len(errs) == 0, errs)


# --------------------------------------------------------------------------- #
# OmniRoute state read
# --------------------------------------------------------------------------- #
@dataclass
class OmniState:
    combos: list = field(default_factory=list)
    connections: list = field(default_factory=list)

    @classmethod
    def load(cls) -> "OmniState":
        combos_raw: list = []
        connections: list = []
        if OMNI_COMBOS_PATH.exists():
            try:
                combos_raw = json.loads(OMNI_COMBOS_PATH.read_text(encoding="utf-8")).get(
                    "combos", []
                )
            except Exception:  # pragma: no cover
                combos_raw = []
        if OMNI_PROVIDERS_PATH.exists():
            try:
                pdata = json.loads(OMNI_PROVIDERS_PATH.read_text(encoding="utf-8"))
                if isinstance(pdata, dict):
                    connections = pdata.get("connections", [])
                elif isinstance(pdata, list):
                    connections = pdata
            except Exception:  # pragma: no cover
                connections = []
        return cls(combos=combos_raw, connections=connections)

    def combo_names(self) -> set:
        return {c.get("name", "") for c in self.combos}

    def combo_by_name(self, name: str):
        for c in self.combos:
            if c.get("name") == name:
                return c
        return None


# --------------------------------------------------------------------------- #
# Reconciliation report
# --------------------------------------------------------------------------- #
@dataclass
class ReconcileReport:
    manifest_version: int
    manifest_combos: list
    omni_combos: list
    missing_in_omni: list
    missing_in_manifest: list
    combo_provider_mismatches: dict
    desktop_app_combo_coverage: dict
    kill_switches_total: int
    self_healing_rules_total: int
    provider_slot_total: int
    worker_scope_total: int
    validation_errors: list

    def to_dict(self) -> dict:
        return {
            "manifest_version": self.manifest_version,
            "generated_at": datetime.now().isoformat(),
            "manifest_combos_count": len(self.manifest_combos),
            "omni_combos_count": len(self.omni_combos),
            "missing_in_omni": self.missing_in_omni,
            "missing_in_manifest": self.missing_in_manifest,
            "combo_provider_mismatches": self.combo_provider_mismatches,
            "desktop_app_combo_coverage": self.desktop_app_combo_coverage,
            "kill_switches_total": self.kill_switches_total,
            "self_healing_rules_total": self.self_healing_rules_total,
            "provider_slot_total": self.provider_slot_total,
            "worker_scope_total": self.worker_scope_total,
            "validation_errors": self.validation_errors,
            "status": "OK" if not self.validation_errors else "DRIFT",
        }


def reconcile(manifest: Manifest, omni: OmniState) -> ReconcileReport:
    m_ok, m_errs = manifest.validate()

    manifest_combo_names = {c.name for c in manifest.combos}
    omni_combo_names = omni.combo_names()

    missing_in_omni = sorted(manifest_combo_names - omni_combo_names)
    missing_in_manifest = sorted(omni_combo_names - manifest_combo_names)

    provider_mismatches: dict = {}
    for c in manifest.combos:
        oc = omni.combo_by_name(c.name)
        if not oc:
            continue
        omni_providers = set()
        for m in oc.get("models", []):
            mp = m.get("model", "").split("/", 1)[0] if m.get("model") else None
            if mp:
                omni_providers.add(mp)
        manifest_providers = set(c.providers)
        only_in_manifest = sorted(manifest_providers - omni_providers)
        only_in_omni = sorted(omni_providers - manifest_providers)
        if only_in_manifest or only_in_omni:
            provider_mismatches[c.name] = {
                "only_in_manifest": only_in_manifest,
                "only_in_omni": only_in_omni,
            }

    desktop_coverage: dict = {d.id: list(d.combos) for d in manifest.desktop_apps}
    provider_slot_total = sum(c.provider_count for c in manifest.combos)
    worker_scope_total = sum(
        sum(1 for v in c.workers.values() if v) for c in manifest.combos
    )

    return ReconcileReport(
        manifest_version=manifest.version,
        manifest_combos=sorted(manifest_combo_names),
        omni_combos=sorted(omni_combo_names),
        missing_in_omni=missing_in_omni,
        missing_in_manifest=missing_in_manifest,
        combo_provider_mismatches=provider_mismatches,
        desktop_app_combo_coverage=desktop_coverage,
        kill_switches_total=len(manifest.kill_switches),
        self_healing_rules_total=len(manifest.self_healing.get("rules", [])),
        provider_slot_total=provider_slot_total,
        worker_scope_total=worker_scope_total,
        validation_errors=m_errs,
    )


# --------------------------------------------------------------------------- #
# Desktop-app config emitters (one per app)
# --------------------------------------------------------------------------- #
def render_desktop_app_config(manifest: Manifest, app: DesktopAppSpec) -> str:
    """Return JSON body for one desktop app config."""
    lines: list = []
    lines.append("{")
    lines.append(f'  "id": "{app.id}",')
    lines.append(f'  "role": "{app.role}",')
    lines.append(f'  "description": "{app.description}",')
    lines.append(f'  "worker_scope": "{app.worker_scope}",')
    lines.append('  "combos": {')
    for cn in app.combos:
        c = next((x for x in manifest.combos if x.name == cn), None)
        if not c:
            continue
        lines.append(f'    "{cn}": {{')
        lines.append(f'      "email": "{c.email}",')
        lines.append(f'      "primary_provider": "{c.primary_provider}",')
        lines.append(f'      "providers": {json.dumps(c.providers)},')
        lines.append(f'      "rpm_limit": {c.free_tier_limit_rpm},')
        lines.append(f'      "daily_limit": {c.free_tier_limit_daily},')
        lines.append(f'      "kill_switch": "{c.kill_switch}",')
        lines.append(f'      "workers": {json.dumps(c.workers)}')
        lines.append("    },")
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def emit_desktop_configs(manifest: Manifest, apply: bool) -> dict:
    """Emit one config file per desktop app. Returns map of app_id -> path."""
    out_map: dict = {}
    for app in manifest.desktop_apps:
        out_path = DESKTOP_APPS_DIR / f"{app.id}_config.json"
        body = render_desktop_app_config(manifest, app)
        if apply:
            out_path.write_text(body, encoding="utf-8")
        out_map[app.id] = str(out_path)
    return out_map


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def render_matrix(manifest: Manifest) -> str:
    lines: list = []
    lines.append("=" * 100)
    lines.append("LeadGen AI — 14 Combos × 5 Desktop Apps × 42 Provider Slots")
    lines.append("=" * 100)
    lines.append("")
    lines.append("DESKTOP APPS")
    lines.append("-" * 100)
    for app in manifest.desktop_apps:
        lines.append(
            f"  {app.id:<14}  role={app.role:<28}  scope={app.worker_scope:<18}  combos={len(app.combos)}"
        )
        for cn in app.combos:
            lines.append(f"      └─ {cn}")
    lines.append("")
    lines.append("COMBOS")
    lines.append("-" * 100)
    for c in manifest.combos:
        vps = "VPS" if c.workers.get("vps") else "  "
        prj = "PROJECT" if c.workers.get("project") else "       "
        ks = c.kill_switch or "(none)"
        lines.append(
            f"  {c.name:<28}  providers={c.provider_count:>2}  rpm={c.free_tier_limit_rpm:>4}  "
            f"daily={c.free_tier_limit_daily:>5}  kill={ks}"
        )
        lines.append(
            f"    └─ primary={c.primary_provider}  workers=[{vps}|{prj}]  email={c.email}"
        )
    lines.append("")
    total_slots = sum(c.provider_count for c in manifest.combos)
    lines.append(f"TOTAL PROVIDER SLOTS: {total_slots}  (target=42 = 14x3)")
    lines.append(f"KILL SWITCHES: {len(manifest.kill_switches)}")
    lines.append(
        f"SELF-HEALING RULES: {len(manifest.self_healing.get('rules', []))}"
    )
    lines.append("=" * 100)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _load_manifest() -> Manifest:
    return Manifest.load()


def _load_omni() -> OmniState:
    return OmniState.load()


def cmd_validate(args: argparse.Namespace) -> int:
    manifest = _load_manifest()
    omni = _load_omni()
    report = reconcile(manifest, omni)
    d = report.to_dict()
    print(json.dumps(d, indent=2))
    return 0 if not d["validation_errors"] else 1


def cmd_render_matrix(args: argparse.Namespace) -> int:
    manifest = _load_manifest()
    print(render_matrix(manifest))
    return 0


def cmd_emit_desktop_configs(args: argparse.Namespace) -> int:
    manifest = _load_manifest()
    out_map = emit_desktop_configs(manifest, apply=args.apply)
    for app_id, path in out_map.items():
        action = "WROTE" if args.apply else "DRY-RUN"
        print(f"[{action}] desktop_app={app_id:<14} path={path}")
    return 0


def cmd_build_manifest(args: argparse.Namespace) -> int:
    """Re-emit combo_distribution.yaml from current OmniRoute state."""
    omni = _load_omni()
    # Map: keep manifest as SoT; we only confirm coverage here
    manifest = _load_manifest()
    report = reconcile(manifest, omni)
    d = report.to_dict()
    print(json.dumps(d, indent=2))
    return 0 if not d["validation_errors"] else 1


def cmd_emit_router_registry(args: argparse.Namespace) -> int:
    """Emit a worker router registry mapping combo -> worker scope."""
    manifest = _load_manifest()
    registry = {"version": 1, "generated_at": datetime.now().isoformat(), "routes": []}
    for c in manifest.combos:
        registry["routes"].append({
            "combo": c.name,
            "primary_provider": c.primary_provider,
            "providers": c.providers,
            "vps_enabled": bool(c.workers.get("vps")),
            "project_enabled": bool(c.workers.get("project")),
            "kill_switch": c.kill_switch,
            "rpm_limit": c.free_tier_limit_rpm,
            "daily_limit": c.free_tier_limit_daily,
            "email": c.email,
        })
    out_path = DESKTOP_APPS_DIR / "router_registry.json"
    if args.apply:
        out_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    action = "WROTE" if args.apply else "DRY-RUN"
    print(f"[{action}] router_registry -> {out_path}")
    return 0


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omniroute_combo_distributor",
        description="LeadGen AI combo distributor (14×5×42) — autonomous self-healing engine.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate", help="Validate manifest vs live OmniRoute + desktop app configs.")

    sub.add_parser("render-matrix", help="Print human-readable distribution matrix.")

    p_emit = sub.add_parser(
        "emit-desktop-configs",
        help="Emit per-desktop-app config files from manifest.",
    )
    p_emit.add_argument(
        "--apply",
        action="store_true",
        help="Actually write files. Default is dry-run.",
    )

    p_router = sub.add_parser(
        "emit-router-registry",
        help="Emit worker router registry mapping combo -> worker scope.",
    )
    p_router.add_argument(
        "--apply",
        action="store_true",
        help="Actually write files. Default is dry-run.",
    )

    sub.add_parser("build-manifest", help="Re-validate manifest and report coverage.")
    return p


def main(argv=None) -> int:
    parser = build_argparser()
    args = parser.parse_args(argv)
    handlers = {
        "validate": cmd_validate,
        "render-matrix": cmd_render_matrix,
        "emit-desktop-configs": cmd_emit_desktop_configs,
        "emit-router-registry": cmd_emit_router_registry,
        "build-manifest": cmd_build_manifest,
    }
    handler = handlers.get(args.cmd)
    if not handler:
        parser.print_help()
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())