#!/usr/bin/env python3
"""Hostinger Managed Hermes — daily project health report.

Runs INSIDE the Hostinger Hermes sandbox (read-only). Probes the live deployment,
runs prod_check against the cloned repo, collects metrics, and emails a digest to
NOTIFY_EMAIL. No write access to repo or VPS.

Naming note: this targets the *Hostinger* product "Hermes Agent". The project
already has an internal Hermes agent (`app/platform/infra_handler.py`) — different.

Usage:
    python3 scripts/hostinger_hermes_daily_report.py            # send email
    python3 scripts/hostinger_hermes_daily_report.py --dry-run  # print only

Setup: see docs/HOSTINGER_HERMES_SETUP.md
"""

from __future__ import annotations

import json
import os
import smtplib
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

# Force UTF-8 stdout for Windows dry-runs (Linux sandbox is UTF-8 by default).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

CONFIG_PATH = Path.home() / ".hermes" / "config.env"
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict[str, str]:
    """Load ~/.hermes/config.env (KEY=VALUE lines). Env vars override file."""
    cfg: dict[str, str] = {}
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    # env wins
    for k in (
        "NOTIFY_EMAIL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "NTFY_URL",
        "NTFY_TOPIC",
        "NTFY_TOKEN",
        "HEALTH_URL",
        "READY_URL",
    ):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    cfg.setdefault("HEALTH_URL", "https://leadsgenai.in/health")
    cfg.setdefault("READY_URL", "https://leadsgenai.in/health/ready")
    cfg.setdefault("NOTIFY_EMAIL", "admin@leadsgenai.in")
    return cfg


_ANSI_RE = __import__("re").compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 60) -> tuple[int, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = _strip_ansi((r.stdout or "") + (r.stderr or ""))
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    except FileNotFoundError as e:
        return 127, f"NOT_FOUND: {e}"
    except Exception as e:
        return 1, f"ERR: {type(e).__name__}: {e}"


def section_git() -> tuple[str, str]:
    rc, head = run(["git", "log", "-1", "--oneline"], cwd=REPO_ROOT)
    rc2, recent = run(["git", "log", "-5", "--oneline"], cwd=REPO_ROOT)
    rc3, _ = run(["git", "fetch", "origin", "-q"], cwd=REPO_ROOT, timeout=30)
    rc4, behind = run(["git", "rev-list", "--count", "HEAD..origin/main"], cwd=REPO_ROOT)
    behind_n = behind.strip() if rc4 == 0 else "?"
    status = "ok" if rc == 0 else "git_error"
    body = f"HEAD: {head.strip()}\nBehind origin/main: {behind_n}\n\nRecent 5:\n{recent.strip()}"
    return status, body


def section_prod_check() -> tuple[str, str]:
    script = REPO_ROOT / "scripts" / "prod_check.py"
    if not script.exists():
        return "missing", "scripts/prod_check.py not present"
    rc, out = run([sys.executable, str(script)], cwd=REPO_ROOT, timeout=120)
    tail = "\n".join(out.strip().splitlines()[-15:])
    status = "ok" if rc == 0 and "ALL CHECKS PASSED" in out else "fail"
    return status, tail


def probe_url(url: str, timeout: int = 10) -> dict[str, str]:
    """GET url, return {status, body_excerpt, code, elapsed_ms}."""
    t0 = datetime.now()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hostinger-hermes/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(2048).decode("utf-8", errors="ignore")
            code = r.getcode()
        elapsed = int((datetime.now() - t0).total_seconds() * 1000)
        return {
            "status": "ok" if code == 200 else "bad",
            "code": str(code),
            "elapsed_ms": str(elapsed),
            "body": body[:500],
        }
    except urllib.error.HTTPError as e:
        return {
            "status": "http_error",
            "code": str(e.code),
            "elapsed_ms": "?",
            "body": str(e)[:300],
        }
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        return {"status": "network_error", "code": "?", "elapsed_ms": "?", "body": str(e)[:300]}
    except Exception as e:
        return {
            "status": "unknown_error",
            "code": "?",
            "elapsed_ms": "?",
            "body": f"{type(e).__name__}: {e}"[:300],
        }


def section_external_health(cfg: dict[str, str]) -> tuple[str, str]:
    h = probe_url(cfg["HEALTH_URL"])
    r = probe_url(cfg["READY_URL"])
    overall = "ok" if h["status"] == "ok" and r["status"] == "ok" else "degraded"
    body = (
        f"GET {cfg['HEALTH_URL']}\n"
        f"  → {h['code']} in {h['elapsed_ms']}ms ({h['status']})\n"
        f"  body excerpt: {h['body'][:200]}\n\n"
        f"GET {cfg['READY_URL']}\n"
        f"  → {r['code']} in {r['elapsed_ms']}ms ({r['status']})\n"
        f"  body excerpt: {r['body'][:200]}"
    )
    return overall, body


def section_pending_patches() -> tuple[str, str]:
    """code_upgrader proposed patches (read-only — file in repo data/)."""
    patches_file = REPO_ROOT / "data" / "code_patches.jsonl"
    if not patches_file.exists():
        return "ok", "data/code_patches.jsonl absent (no patches yet)"
    by_id: dict[str, dict] = {}
    try:
        with patches_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    pid = rec.get("id")
                    if not pid:
                        continue
                    if pid in by_id:
                        by_id[pid].update({k: v for k, v in rec.items() if v is not None})
                    else:
                        by_id[pid] = dict(rec)
                except Exception:
                    pass
    except Exception as e:
        return "fail", f"read error: {e}"
    rows = list(by_id.values())
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.get("status", "proposed")] = counts.get(r.get("status", "proposed"), 0) + 1
    body_lines = [f"Total patches: {len(rows)}", f"By status: {counts}"]
    proposed = [r for r in rows if r.get("status", "proposed") == "proposed"][:5]
    if proposed:
        body_lines.append("\nLatest proposed (top 5):")
        for r in proposed:
            body_lines.append(f"  - {r.get('id', '?')[:8]}  {r.get('title', '')[:80]}")
    status = "ok" if len(proposed) < 5 else "attention"
    return status, "\n".join(body_lines)


def section_loop_audit() -> tuple[str, str]:
    """TODOs/stubs in critical paths."""
    audit = REPO_ROOT / "scripts" / "loop_audit.py"
    if not audit.exists():
        return "ok", "scripts/loop_audit.py absent"
    rc, out = run([sys.executable, str(audit)], cwd=REPO_ROOT, timeout=30)
    if rc != 0:
        return "fail", out[-500:]
    # Just send summary line
    summary_line = ""
    for line in out.splitlines():
        if "SUMMARY" in line or "Total hits" in line or "Files with issues" in line:
            summary_line += line + "\n"
    if not summary_line:
        summary_line = out[-300:]
    return "ok", summary_line.strip()


def build_report(cfg: dict[str, str]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    sections: list[tuple[str, str, str]] = []
    for name, fn in [
        ("Git state", section_git),
        ("prod_check.py", section_prod_check),
        ("External health", lambda: section_external_health(cfg)),
        ("Pending code-upgrader patches", section_pending_patches),
        ("Loop / stub audit", section_loop_audit),
    ]:
        try:
            status, body = fn()
        except Exception as e:
            status, body = "exception", f"{type(e).__name__}: {e}"
        sections.append((name, status, body))

    bad = [n for n, s, _ in sections if s not in ("ok",)]
    headline = "ALL GREEN" if not bad else f"ATTENTION: {', '.join(bad)}"

    lines = [
        "LeadGen AI — daily health report",
        f"Generated: {now}",
        f"Reporter: Hostinger Managed Hermes (sandbox: {socket.gethostname()})",
        f"Headline: {headline}",
        "",
        "=" * 60,
        "",
    ]
    for name, status, body in sections:
        lines.append(f"## {name}  [{status}]")
        lines.append("")
        lines.append(body)
        lines.append("")
        lines.append("-" * 60)
        lines.append("")
    lines.append("--")
    lines.append("Generated by scripts/hostinger_hermes_daily_report.py")
    lines.append("Docs: docs/HOSTINGER_HERMES_SETUP.md")
    return "\n".join(lines)


def send_email(cfg: dict[str, str], subject: str, body: str) -> tuple[bool, str]:
    host = cfg.get("SMTP_HOST")
    port = int(cfg.get("SMTP_PORT") or 465)
    user = cfg.get("SMTP_USERNAME")
    pw = cfg.get("SMTP_PASSWORD")
    to = cfg.get("NOTIFY_EMAIL")
    if not (host and user and pw and to):
        return False, "SMTP config incomplete (missing host/username/password/notify_email)"
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
        return True, f"sent to {to}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def push_ntfy(cfg: dict[str, str], title: str, body: str) -> None:
    url = cfg.get("NTFY_URL")
    topic = cfg.get("NTFY_TOPIC")
    if not (url and topic):
        return
    try:
        req = urllib.request.Request(
            f"{url.rstrip('/')}/{topic}",
            data=body[:2000].encode("utf-8"),
            headers={
                "Title": title[:200],
                "Priority": "default",
                "Authorization": f"Bearer {cfg['NTFY_TOKEN']}" if cfg.get("NTFY_TOKEN") else "",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass  # ntfy is best-effort


def main() -> int:
    dry = "--dry-run" in sys.argv
    cfg = load_config()
    body = build_report(cfg)
    subject = f"[Hermes] LeadGen daily health {datetime.now().strftime('%Y-%m-%d')}"
    if "ATTENTION" in body.splitlines()[3]:
        subject = f"[Hermes] ⚠️ LeadGen ATTENTION {datetime.now().strftime('%Y-%m-%d')}"
    if dry:
        print(body)
        print("\n(dry-run, no email sent)")
        return 0
    ok, info = send_email(cfg, subject, body)
    if ok:
        print(f"[ok] {info}")
        # ntfy short ping only on issues
        if "ATTENTION" in subject:
            push_ntfy(cfg, subject, body.splitlines()[3] if len(body.splitlines()) > 3 else "")
        return 0
    print(f"[fail] {info}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
