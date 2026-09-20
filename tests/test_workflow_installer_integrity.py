"""Guard: a workflow installer must not be able to silently no-op.

Evidence (CI run for `c691c8d1`, 2026-09-20): `Trivy repo scan + SBOM` failed
with exit 127 -- `trivy: command not found`. The install line before it looked
fine:

    curl -sfL https://raw.githubusercontent.com/.../install.sh \\
      | sh -s -- -b /usr/local/bin v0.72.0

GitHub runs each `run:` block as `bash -e {0}` -- `-e`, but **no pipefail**. In
a pipeline the exit status is the LAST command's, and `sh` handed an empty stdin
(a failed `curl`, a TLS blip, a 429, a raw.githubusercontent hiccup) exits 0.
So the download can fail, the install can do nothing, and the step still
"succeeds" -- the real failure surfaces two lines later as an unrelated-looking
127. A security scan whose installer can silently no-op is a disabled security
scan wearing a green check.

Fix shape: download to a file, assert the file is non-empty, then execute it,
then assert the binary answers. `test_trivy_installers_are_hardened_and_verify_
the_binary` pins that, and counts them so deleting an installer cannot pass by
absence (R4: a test that asserts absence must not be satisfiable by removing the
thing).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO / ".github" / "workflows"

PIPE_TO_SHELL = re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sh|bash)\b")
INSTALLER_HARDENING = ("pipefail", "--retry", "test -s")


def _workflow_steps() -> list[tuple[str, str, str]]:
    """(file, step name, run body) for every step in every workflow."""
    out = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        for _job, spec in (doc.get("jobs") or {}).items():
            for step in spec.get("steps") or []:
                if isinstance(step, dict) and step.get("run"):
                    out.append((wf.name, str(step.get("name", "")), str(step["run"])))
    return out


def _code(run: str) -> str:
    """Drop whole-line comments: a comment may quote the old dangerous shape."""
    return "\n".join(
        ln for ln in run.splitlines() if not ln.strip().startswith("#")
    )


def _logical_lines(code: str) -> list[tuple[int, str]]:
    """Join backslash continuations, keeping the physical line each one starts on.

    The shape that actually shipped split `curl ... \\` and `| sh -s --` across
    two physical lines, so a per-line scan would have missed it -- the same
    blind spot that let `docker compose ... \\` + `ps -q app` slip past a
    text-scan guard elsewhere in this repo.
    """
    out: list[tuple[int, str]] = []
    buf = ""
    start = 0
    for n, ln in enumerate(code.splitlines(), 1):
        if not buf:
            start = n
        if ln.endswith("\\"):
            buf += ln[:-1] + " "
            continue
        out.append((start, buf + ln))
        buf = ""
    if buf:
        out.append((start, buf))
    return out


def test_no_workflow_installs_by_piping_a_download_into_a_shell():
    offenders = []
    for name, step, run in _workflow_steps():
        for lineno, logical in _logical_lines(_code(run)):
            if PIPE_TO_SHELL.search(logical):
                offenders.append(f"{name} :: {step} (line {lineno}): {logical.strip()}")
    assert not offenders, (
        "a piped installer cannot fail its step: the step shell is `bash -e` "
        "without pipefail and `sh` exits 0 on empty stdin, so a dead download "
        "becomes a silent no-op install. Download, `test -s`, then execute.\n\n"
        + "\n".join(offenders)
    )


def test_trivy_installers_are_hardened_and_verify_the_binary():
    trivy_steps = [
        (name, step, run)
        for name, step, run in _workflow_steps()
        if "trivy-install.sh" in run or "Install Trivy" in step
    ]
    # There are two jobs that install Trivy (repo scan + image scan). Asserting
    # the count is what stops "fixed" meaning "deleted".
    assert len(trivy_steps) >= 2, (
        f"expected a hardened Trivy installer in both security-scan jobs, found "
        f"{len(trivy_steps)}: {[(n, s) for n, s, _ in trivy_steps]}"
    )
    for name, step, run in trivy_steps:
        code = _code(run)
        for needle in INSTALLER_HARDENING:
            assert needle in code, f"{name} :: {step} is missing {needle!r}"
        assert re.search(r"^\s*trivy\s+--version\s*$", code, re.M), (
            f"{name} :: {step} must prove the binary exists before trusting it"
        )
        assert not PIPE_TO_SHELL.search(
            " ".join(l for _, l in _logical_lines(code))
        ), f"{name} :: {step} still pipes a download into a shell"


# --------------------------------------------------------------------------- #
# anti-vacuity
# --------------------------------------------------------------------------- #


def test_detector_is_not_vacuous():
    shipped = (
        "curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/"
        "contrib/install.sh \\\n    | sh -s -- -b /usr/local/bin v0.72.0\n"
        "  trivy --version\n"
    )
    lines = _logical_lines(shipped)
    assert len(lines) == 2, "continuation join collapsed the wrong number of lines"
    assert PIPE_TO_SHELL.search(lines[0][1]), (
        "the detector must catch the continuation-split form that actually shipped"
    )
    # one-line form
    assert PIPE_TO_SHELL.search(_logical_lines("curl -sSL url | sh")[0][1])
    # hardened form must NOT be flagged
    hardened = (
        "set -euo pipefail\n"
        "curl -fsSL --retry 5 -o /tmp/trivy-install.sh https://example.com/install.sh\n"
        "test -s /tmp/trivy-install.sh\n"
        "sh /tmp/trivy-install.sh -b /usr/local/bin v0.72.0\n"
    )
    assert not any(PIPE_TO_SHELL.search(l) for _, l in _logical_lines(hardened))
    # a comment may quote the old shape without tripping the gate
    commented = "# never do: curl url | sh\ncurl -fsSL -o /tmp/i.sh https://e/i.sh\n"
    assert not any(
        PIPE_TO_SHELL.search(l) for _, l in _logical_lines(_code(commented))
    )
    # ...but an inline `#` after code does not launder it
    hidden = "curl -fsSL https://e/i.sh | sh  # installed\n"
    assert PIPE_TO_SHELL.search(_logical_lines(hidden)[0][1])
