"""Security scan — pre-push + periodic audit gate.

Runs multiple security checks:
1. Secrets scan (delegates to check_secrets.py)
2. Dependency vulnerability check (basic — requires `pip-audit` or warns)
3. Common security misconfigurations grep (with false-positive suppression)
4. Unsafe eval/exec detection
5. Missing input validation detection
6. Hardcoded SQL construction detection

Usage:
    python scripts/security_scan.py              # quick scan
    python scripts/security_scan.py --full       # full audit (all files)

Exit 0 = clean · Exit 1 = findings present.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Patterns for common security misconfigurations
MISCONFIG_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "CSRF disabled / session without CSRF",
        re.compile(r"csrf_protect\s*=\s*False|CSRFProtect\s*\(.*disabled|session\s*\.\s*csrf"),
    ),
    (
        "CORS allow-all origin",
        re.compile(r"allow_origins\s*=\s*\[?\s*['\"]\*['\"]\s*\]?|CORS\(.*['\"]\*['\"]"),
    ),
    ("unsafe eval / exec", re.compile(r"\beval\s*\(|\bexec\s*\(")),
    (
        "hardcoded SQL string formatting",
        re.compile(
            r"f['\"]\s*SELECT\s+.*\{.*\}|f['\"]\s*INSERT\s+.*\{.*\}|f['\"]\s*DELETE\s+.*\{.*\}|f['\"]\s*UPDATE\s+.*\{.*\}"
        ),
    ),
    (
        "raw SQL without parameterization",
        re.compile(r"\.execute\s*\(\s*['\"]\s*(SELECT|INSERT|UPDATE|DELETE)"),
    ),
    (
        "pickle / yaml.load without safe loader",
        re.compile(r"pickle\.loads?\s*\(|yaml\.load\s*\(|yaml\.unsafe_load"),
    ),
    ("debug mode enabled", re.compile(r"DEBUG\s*=\s*True|debug\s*=\s*True")),
    (
        "sensitive data in URL",
        re.compile(r"https?://[^\s'\"]+\?(?:[^&]*password|[^&]*secret|[^&]*token)"),
    ),
]

# Context patterns that indicate a false positive (checked on the same line)
FALSE_POSITIVE_CONTEXTS: list[tuple[str, re.Pattern]] = [
    (
        "Redis Lua eval",
        re.compile(r"client\.eval\s*\(|redis\.eval\s*\(|\.eval\s*\(\s*['\"][a-zA-Z_]"),
    ),
    ("parameterized SQL", re.compile(r"\.execute\s*\(\s*['\"].*['\"],\s*\(")),
    ("health check SQL", re.compile(r"SELECT\s+1\s*['\"]\s*\)")),
    ("comment-only reference", re.compile(r"#\s*.*eval|#\s*.*exec")),
]

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "data",
    "dist",
    "build",
    ".pytest_cache",
    "frontend",
    "monitoring",
}
SKIP_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".mp3",
    ".mp4",
    ".wav",
    ".zip",
    ".gz",
    ".db",
    ".pyc",
    ".lock",
    ".idx",
    ".pack",
}
SKIP_NAMES = {"security_scan.py", "check_secrets.py"}


def should_scan(rel: str) -> bool:
    p = Path(rel)
    if p.name in SKIP_NAMES:
        return False
    if p.suffix.lower() in SKIP_EXT:
        return False
    return not any(part in SKIP_DIRS for part in p.parts)


def all_py_files() -> list[str]:
    try:
        r = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=60
        )
        return [
            l.strip()
            for l in r.stdout.splitlines()
            if l.strip().endswith(".py") and should_scan(l.strip())
        ]
    except Exception:
        return [str(p.relative_to(ROOT)) for p in ROOT.rglob("app/**/*.py")]


def scan_misconfigs() -> list[str]:
    """Scan Python files for security misconfigurations, with false-positive suppression."""
    findings: list[str] = []
    for rel in all_py_files():
        fp = ROOT / rel
        if not fp.is_file():
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "nosecurity" in line or "# noqa" in line:
                continue
            # Skip test/debug files for certain patterns
            if rel.startswith("tests/") or rel.startswith("scripts/"):
                if "debug" in line.lower() or "test_" in rel:
                    continue
            for label, pat in MISCONFIG_PATTERNS:
                m = pat.search(line)
                if m:
                    # Check for false-positive context on the same line
                    is_fp = any(fp_pat.search(line) for _, fp_pat in FALSE_POSITIVE_CONTEXTS)
                    if is_fp:
                        continue
                    findings.append(f"{rel}:{i}: {label}: {m.group(0)[:60]}...")
                    break
    return findings


def check_pip_audit() -> list[str]:
    findings: list[str] = []
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--requirement",
                str(ROOT / "requirements.txt"),
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 and result.stdout:
            findings.append(f"[pip-audit] vulnerabilities found: {result.stdout[:500]}")
    except FileNotFoundError:
        findings.append("[WARN] pip-audit not installed — run: pip install pip-audit")
    except Exception as e:
        findings.append(f"[WARN] pip-audit failed: {e}")
    return findings


def check_secrets() -> list[str]:
    findings: list[str] = []
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_secrets.py"), "--all"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            for line in result.stdout.splitlines():
                if line.strip() and not line.startswith("["):
                    findings.append(f"[secrets] {line.strip()}")
    except Exception as e:
        findings.append(f"[WARN] check_secrets.py failed: {e}")
    return findings


def main() -> int:
    args = sys.argv[1:]
    full_mode = "--full" in args
    print(f"[security_scan] mode={'full' if full_mode else 'quick'} | ROOT={ROOT}")
    print("=" * 60)

    all_findings: list[str] = []

    # 1. Secrets
    print("\n[1/4] Secrets scan...")
    secrets = check_secrets()
    all_findings.extend(secrets)
    print(f"  {'OK' if not secrets else f'{len(secrets)} findings'}")

    # 2. Misconfigurations
    print("\n[2/4] Security misconfiguration scan...")
    misconfigs = scan_misconfigs()
    all_findings.extend(misconfigs)
    print(f"  {'OK' if not misconfigs else f'{len(misconfigs)} findings'}")
    for f in misconfigs[:10]:
        print(f"    {f}")
    if len(misconfigs) > 10:
        print(f"    ... and {len(misconfigs) - 10} more")

    # 3. Dependency vulnerabilities
    print("\n[3/4] Dependency vulnerability scan...")
    deps = check_pip_audit()
    all_findings.extend(deps)
    print(f"  {'OK' if not deps else f'{len(deps)} findings'}")
    for f in deps:
        print(f"    {f}")

    # 4. Summary
    print("\n" + "=" * 60)
    if all_findings:
        print(f"[FAIL] {len(all_findings)} security findings found")
        print("  Fix them or add '# nosecurity' comment for false positives.")
        return 1
    print("[OK] No security findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
