"""Safety-rail state machine for the bounded repair loop (pure, testable).

Every decision here is fail-closed: unverifiable GitHub state, a moved head,
protected-path touches, a missing head pin, an exhausted attempt budget or a
stale CI result all refuse the operation before any file is touched.

No subprocess, no network — tests exercise these exact control paths.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.pr_factory.pilot import MAX_REPAIR_ATTEMPTS
from tools.pr_factory.pilot.manifest import PilotTask

_HEX40_RE = re.compile(r"^[0-9a-fA-F]{40}$")

#: Infra markers: retry/owner-review territory, never a code repair.
_INFRA_MARKERS = (
    "runner",
    "no space left",
    "disk space",
    "infrastructure failure",
    "client.timeout",
    "registry-1.docker.io",
    "docker hub",
    "timed out",
    "canceled",
    "cancelled",
    "network",
    "unreachable",
    "registry",
    "connection reset",
    "503",
    "502",
    "429",
    "exit code 125",
    "socket hang up",
)

#: Code markers: a real repair candidate.
_CODE_MARKERS = (
    "error",
    "traceback",
    "failed",
    "assert",
    "syntaxerror",
    "modulenotfound",
    "importerror",
    "pytest",
    "exception",
    "ruff",
    "lint",
    "mypy",
    "compileall",
    "exit code 1",
    "exit code 2",
    "keyword can't be an expression",
    "indentationerror",
)


class PilotRefusal(Exception):
    """The pilot refused to act — stable machine code + reason for audit."""

    def __init__(self, code: str, reason: str, detail: str = "") -> None:
        super().__init__(f"{code}: {reason}".rstrip(":"))
        self.code = code
        self.reason = reason
        self.detail = detail

    def to_dict(self) -> dict[str, str]:
        return {"refused": True, "code": self.code, "reason": self.reason, "detail": self.detail}


class GuardRefusal(PilotRefusal):
    """Fail-closed refusal with a stable machine code."""


class PilotStateUnverifiable(GuardRefusal):
    """GitHub state could not be confirmed — fail closed, never proceed."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("github_state_unverifiable", "GitHub state could not be verified", detail)


def validate_sha(sha: str) -> bool:
    return bool(_HEX40_RE.match(sha or ""))


def check_expected_head_sha(expected: str, actual: str) -> None:
    """Refuse when the remote task-branch head does not match the manifest pin.

    ``expected`` must be a real 40-hex pin (never empty/"PENDING") — a task whose
    head is not pinned cannot be repaired (a moved/unpinned branch is unsafe).
    """
    if not validate_sha(expected):
        raise GuardRefusal(
            "head_sha_pin_missing", "task head is not pinned", f"expected={expected!r}"
        )
    if not validate_sha(actual):
        raise PilotStateUnverifiable(f"remote head is not a sha: {actual!r}")
    if expected.lower() != actual.lower():
        raise GuardRefusal(
            "head_sha_mismatch",
            "task-branch head moved; fresh owner review required",
            f"expected={expected} actual={actual}",
        )


def protected_path_hits(changed_paths: list[str]) -> list[str]:
    """Fail-closed: any protected-prefix touch in the changed set."""
    from app.dev_control.external_agents import policy

    hits: list[str] = []
    for raw in changed_paths or []:
        canon = policy.canonical_path(raw)
        if not canon:
            hits.append(str(raw).strip() or "(unparseable path)")
            continue
        for prefix in policy.PROTECTED_PATH_PREFIXES:
            p = prefix.lower()
            if canon == p or canon.startswith(p):
                hits.append(canon)
                break
    return sorted(set(hits))


def out_of_scope_paths(changed_paths: list[str], task: PilotTask) -> list[str]:
    """Paths outside the manifest's declared ownership (scope breach evidence)."""
    from app.dev_control.external_agents import policy

    allowed_keys = {
        policy.canonical_path(a) for a in task.allowed_paths if policy.canonical_path(a)
    }
    denied_keys = {
        policy.canonical_path(d) for d in task.all_denied_paths() if policy.canonical_path(d)
    }
    bad: list[str] = []
    for raw in changed_paths or []:
        canon = policy.canonical_path(raw)
        if not canon:
            bad.append(str(raw).strip() or "(unparseable path)")
            continue
        if any(
            canon == d or canon.startswith(d.rstrip("/") + "/") or canon.startswith(d)
            for d in denied_keys
        ):
            bad.append(raw)
            continue
        if not any(canon == a or canon.startswith(a.rstrip("/") + "/") for a in allowed_keys):
            bad.append(raw)
    return sorted(set(bad))


def classify_failure(summary: str) -> str:
    """Buckets a failing log: ``code`` | ``infra`` | ``unknown``.

    Code markers win over infra markers because a stack trace inside an infra
    wrapper is still a code failure; only infra-only evidence is retryable
    without code change.
    """
    low = (summary or "").lower()
    if any(m in low for m in _CODE_MARKERS):
        return "code"
    if any(m in low for m in _INFRA_MARKERS):
        return "infra"
    return "unknown"


def is_transient_retryable(check: dict[str, Any]) -> bool:
    """True when a GitHub retry is the correct first move (no code change yet)."""
    status = (check.get("status") or "").lower()
    conclusion = (check.get("conclusion") or "").lower()
    if status != "completed":
        return False
    if conclusion in {"action_required", "success"}:
        return False
    if conclusion in {"cancelled", "canceled", "timed_out", "startup_failure", "stale"}:
        return True
    if conclusion == "failure":
        return classify_failure(check.get("log") or check.get("summary") or "") == "infra"
    return False


def can_retry_transient(attempted_retries: int, max_retries: int = 1) -> bool:
    """Bounded GitHub-level retries: at most one per diagnosis cycle."""
    return int(attempted_retries) < int(max_retries)


@dataclass
class RepairAttempt:
    pr_number: int
    head_sha: str
    attempt_number: int
    outcome: str
    ts: float = field(default_factory=time.time)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RepairLedger:
    """Append-only attempt ledger; enforces the hard repair-attempt cap.

    Backed by a JSONL file inside the git metadata dir (never committed, never
    production data). Path injectable for tests.
    """

    def __init__(self, state_dir: str | Path | None = None) -> None:
        self._path = Path(state_dir or _default_state_dir()) / "repair_ledger.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[RepairAttempt] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                self._entries.append(
                    RepairAttempt(
                        pr_number=int(data["pr_number"]),
                        head_sha=str(data["head_sha"]),
                        attempt_number=int(data["attempt_number"]),
                        outcome=str(data["outcome"]),
                        ts=float(data.get("ts", 0.0)),
                        note=str(data.get("note", "")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue

    def _append(self, entry: RepairAttempt) -> None:
        self._entries.append(entry)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def attempts_for(self, pr_number: int, head_sha: str) -> list[RepairAttempt]:
        return [
            e
            for e in self._entries
            if e.pr_number == pr_number and e.head_sha.lower() == head_sha.lower()
        ]

    def attempts_count(self, pr_number: int, head_sha: str) -> int:
        return len(self.attempts_for(pr_number, head_sha))

    def can_repair(self, pr_number: int, head_sha: str, cap: int | None = None) -> bool:
        return self.attempts_count(pr_number, head_sha) < int(cap or MAX_REPAIR_ATTEMPTS)

    def remaining(self, pr_number: int, head_sha: str, cap: int | None = None) -> int:
        limit = int(cap or MAX_REPAIR_ATTEMPTS)
        return max(0, limit - self.attempts_count(pr_number, head_sha))

    def record_attempt(
        self, pr_number: int, head_sha: str, outcome: str, note: str = ""
    ) -> RepairAttempt:
        if not self.can_repair(pr_number, head_sha):
            raise GuardRefusal(
                "attempt_cap_exceeded",
                "automated repair attempts exhausted for this head; owner review required",
                f"pr={pr_number} head={head_sha}",
            )
        entry = RepairAttempt(
            pr_number=pr_number,
            head_sha=head_sha,
            attempt_number=self.attempts_count(pr_number, head_sha) + 1,
            outcome=outcome,
            note=note,
        )
        self._append(entry)
        return entry

    def snapshot(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._entries]


def _default_state_dir() -> Path:
    """Never inside production data: use the repo git-metadata dir."""
    from pathlib import Path as _P

    return _P(__file__).resolve().parents[5] / ".git" / "leadgen-pr-pilot"


def fresh_ci_evidence(runs: list[dict[str, Any]], head_sha: str) -> dict[str, Any] | None:
    """Find a check run bound to the exact head SHA (fresh-CI evidence).

    A completed run against an older SHA is deliberately ignored — a stale CI
    result can never authorize completion for the current head.
    """
    needle = head_sha.lower()
    for run in runs or []:
        if (run.get("head_sha") or "").lower() == needle:
            return run
    return None


def require_fresh_ci(runs: list[dict[str, Any]], head_sha: str) -> None:
    """Refuse when no check run is bound to the exact head SHA."""
    if fresh_ci_evidence(runs, head_sha) is None:
        raise GuardRefusal(
            "fresh_ci_required",
            "no CI evidence for the exact head SHA; run fresh CI before verifying",
            f"head={head_sha} runs={len(runs or [])}",
        )


def stale_ci_authorizes(completed_runs: list[dict[str, Any]], current_head: str) -> bool:
    """A successful completed run on an older SHA must not authorize completion."""
    return fresh_ci_evidence(completed_runs, current_head) is not None


def build_audit_receipt(
    *,
    pr_number: int,
    head_sha: str,
    mode: str,
    verdict: str,
    attempts: int,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Structured, tamper-evident audit output for the task owner."""
    return {
        "schema": "leadgen.pr-pilot.receipt.v1",
        "pr_number": pr_number,
        "head_sha": head_sha,
        "mode": mode,
        "verdict": verdict,
        "attempts_used": int(attempts),
        "max_repair_attempts": int(MAX_REPAIR_ATTEMPTS),
        "evidence": evidence,
        "ts": time.time(),
    }
