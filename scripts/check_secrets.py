"""Secrets scanner — pre-push gate (project rule: secrets SIRF .env me).

Adapted from luongnv89/claude-howto 06-hooks/security-scan.sh (MIT) — Python
port, Windows-safe (no bash hooks), project-tailored patterns (Exotel/Razorpay/
Stripe/Groq/Pollinations/JWT) + placeholder allowlist.

Usage:
    python scripts/check_secrets.py              # changed files vs HEAD (staged+unstaged)
    python scripts/check_secrets.py --all        # poora repo (slow, one-time audit)
    python scripts/check_secrets.py path1 path2  # specific files

Exit 0 = clean · Exit 1 = potential secret mila (file:line print hota hai).
Wired into /verify step 4. False-positive ho to us LINE me `nosecret` comment
add karo (scanner skip kar dega) — ya value placeholder banao.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("generic key/secret/token/password assignment",
     re.compile(r"(?i)\b\w*(api[_-]?key|secret|token|passwd|password)\w*\s*[=:]\s*['\"][A-Za-z0-9_\-/+\.]{12,}['\"]")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Stripe/Pollinations sk_ key", re.compile(r"\bsk_(?:live_|test_)?[A-Za-z0-9]{16,}")),
    ("Razorpay live key", re.compile(r"\brzp_live_[A-Za-z0-9]{8,}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("Groq/OpenAI-style key", re.compile(r"\b(?:gsk|sk-proj|sk-ant)[-_][A-Za-z0-9_\-]{20,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}")),
    ("Bearer header literal", re.compile(r"(?i)Authorization['\"]?\s*[:=]\s*['\"]Bearer\s+[A-Za-z0-9_\-\.]{20,}")),
]

# In values pe match ho to fake/placeholder maan ke skip
PLACEHOLDER = re.compile(
    r"(?i)(your[-_ ]|<|>|\{\{|xxx|changeme|change-me|example|dummy|placeholder|sample|redacted|\.\.\.|abcdef|1234567890)"
)

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "data", "dist", "build", ".pytest_cache", ".agents", ".claude"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf", ".eot",
            ".pdf", ".mp3", ".mp4", ".wav", ".zip", ".gz", ".db", ".pyc", ".lock", ".idx", ".pack"}
SKIP_NAMES = {"check_secrets.py"}  # khud ke patterns pe trip na ho
ENV_FILE = re.compile(r"(^|[\\/])\.env(\..*)?$")  # .env gitignored — waise bhi skip


def changed_files() -> list[str]:
    out: set[str] = set()
    for args in (
        ["diff", "--name-only", "HEAD"],
        ["diff", "--cached", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],  # NAYE untracked files bhi
    ):
        try:
            r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30)
            out.update(l.strip() for l in r.stdout.splitlines() if l.strip())
        except Exception:
            pass
    return sorted(out)


def all_files() -> list[str]:
    try:
        r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        return [l.strip() for l in r.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def should_scan(rel: str) -> bool:
    p = Path(rel)
    if p.name in SKIP_NAMES or ENV_FILE.search(rel):
        return False
    if p.suffix.lower() in SKIP_EXT:
        return False
    return not any(part in SKIP_DIRS for part in p.parts)


def scan_file(rel: str) -> list[str]:
    fp = ROOT / rel
    if not fp.is_file():
        return []
    try:
        text = fp.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    findings = []
    for i, line in enumerate(text.splitlines(), 1):
        if "nosecret" in line:
            continue
        for label, pat in PATTERNS:
            m = pat.search(line)
            if m and not PLACEHOLDER.search(line):
                findings.append(f"{rel}:{i}: {label}: {m.group(0)[:48]}...")
                break
    return findings


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--all":
        targets = all_files()
        mode = "ALL tracked files"
    elif args:
        targets = args
        mode = "given paths"
    else:
        targets = changed_files()
        mode = "changed vs HEAD"
    targets = [t for t in targets if should_scan(t)]
    print(f"[check_secrets] scanning {len(targets)} files ({mode})")
    findings: list[str] = []
    for t in targets:
        findings.extend(scan_file(t))
    if findings:
        print("[FAIL] potential secrets mile — .env me daalo ya line pe `nosecret` (sirf false-positive pe):")
        for f in findings:
            print("  " + f)
        return 1
    print("[OK] no secrets detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
