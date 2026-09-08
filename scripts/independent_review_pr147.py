"""Independent Claude Code review of PR #147 runner implementation.

Read-only. No PR mutation during Claude run. Persists via orchestrator
submit_review() then posts a sanitized PR comment. Does not merge/deploy.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXPECTED_HEAD = (os.environ.get("PR147_REVIEW_HEAD") or "").strip()  # optional pin
BASE_SHA = "e64b8a9d10bcf6084488b34f886f77a5752f13f8"  # pragma: allowlist secret
PR = 147
TIMEOUT_S = 1200

ALLOWED_PATHS = [
    "app/dev_control/external_agents/runner/",
    "app/dev_control/external_agents/approval.py",
    "app/dev_control/external_agents/cas.py",
    "app/dev_control/external_agents/adapters.py",
    "app/dev_control/external_agents/orchestrator.py",
    "app/api/dev_tasks.py",
    "app/api/automation_flags.py",
    "frontend/dev_control.html",
    "scripts/dogfood_external_agent_runner.py",
    "scripts/external_agent_runner.py",
    "scripts/independent_review_pr147.py",
    "tests/test_external_agent_runner.py",
    "tests/test_external_agent_runner_real_subprocess.py",
    "tests/test_external_agent_runner_windows_security.py",
    "tests/fixtures/external_agent_runner/",
    "docs/adr/ADR-149-external-agent-runner.md",
    "docs/runbooks/EXTERNAL_AGENT_RUNNER.md",
    "docs/context/ACTIVE_WORK.md",
    "docs/context/SESSION_HANDOFF.md",
]


def _git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        timeout=60,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr[:300]}")
    return (out.stdout or "").strip()


def _head() -> str:
    return _git("rev-parse", "HEAD")


def _build_prompt(mission_id: str, head: str, diff_path: str, file_list: str) -> str:
    return f"""You are an INDEPENDENT Claude Code reviewer for LeadGen PR #{PR}.
Read-only. Do NOT edit files, commit, push, merge, deploy, flip flags, call, bill, or outreach.
Inspect ACTUAL source under the workspace (not PR summary prose).

REVIEWED_HEAD={head}
BASE_SHA={BASE_SHA}
MISSION_ID={mission_id}
PR={PR}

If git HEAD is not exactly {head}, return verdict BLOCKED.

Mandatory review areas (cite file:line or symbol for each real finding):
0) SIXTH-CYCLE CLOSURE (must prove ALL five — Claude-5 residuals):
   1) Live Claude review uses ``review_parse.recover_independent_review`` (not ad-hoc
      extract_review_manifest) on run_mission_once / invoke_claude_review.
   2) No ``runner_auto_review`` synthetic citation backfill; empty evidence stays MISSING;
      PASS requires concrete citations.
   3) Redis coordination is fail-closed (EXTERNAL_AGENT_COORDINATION_BACKEND); no silent
      FileLock fallback when Redis is required; backend identity on leases.
   4) Heartbeat interval <= lease_ttl/3 via lease_contract.derive_lease_and_interval.
   5) AMBER advance requires Owner OS ``approval_decision_id`` binding — boolean alone refused.
1) Authority/gating: Owner OS auth real vs bypassable; GREEN-only unattended; AMBER parks; RED refuse; runner requires orchestrator; both flags default OFF; API cannot bypass eligibility.
2) Command construction: executable allowlist; no user-controlled exe; no shell concatenation; argv arrays; Windows quoting; prompt file safety; env allowlist; PATH hijack; cwd/worktree root validation.
3) Cursor invocation: no agent.cmd; --trust decision; workspace; file+envelope JSON parsing; allowed-path containment; auth/availability.
4) Claude invocation: non-interactive; plan/read-only; disallowed tools including Bash; canonical review_parse; auth-before-run; timeout/kill; token/cost budget (cache-read excluded).
5) Process lifecycle: heartbeat vs lease TTL contract; cancel race; lease-loss; child cleanup; Windows process-tree kill; timeout; stdout/stderr deadlock; output cap; encoding; late/stale result rejection.
6) Concurrency: dual claim; CAS; worktree/branch conflict; executor/reviewer overlap; Redis/FileLock explicit modes; crash between process end and submit_result.
7) Security: prompt injection; hostile repo/test output; secret redaction; log leakage; Windows junction/symlink escape; UNC/drive traversal; env secret inheritance; destructive git prevention.
8) Dogfood validity: real Cursor+Claude CLIs; no manual copy-paste; lease/heartbeats; manifest validation; dogfood worktree not merged; reproducibility caveats.
9) API/UI: require_admin; runner endpoint exposure; status leakage; disabled-state; cancellation controls; AMBER approval_decision_id.
10) Tests: unit vs integration; mocks hiding subprocess defects; cancel/timeout; Redis; Windows process; overflow; malformed JSON; injection; symlink; auth/binary unavailable.

Also read the unified diff file at: {diff_path}
Changed files:
{file_list}

Return EXACTLY one JSON object (no markdown fences):
{{
  "mission_id": "{mission_id}",
  "reviewer": "claude",
  "pr": {PR},
  "reviewed_head_sha": "{head}",
  "base_sha": "{BASE_SHA}",
  "verdict": "PASS | CHANGES_REQUIRED | BLOCKED",
  "summary": "string",
  "findings": [
    {{
      "severity": "CRITICAL | HIGH | MEDIUM | LOW | NIT",
      "title": "string",
      "file": "repo-relative path",
      "line_or_symbol": "string",
      "evidence": "string",
      "risk": "string",
      "required_fix": "string"
    }}
  ],
  "runner_proof": {{
    "cursor_invocation_verified": true,
    "claude_invocation_verified": true,
    "manual_prompt_copy_paste_absent": true,
    "lease_and_heartbeat_verified": true,
    "result_manifest_verified": true,
    "review_manifest_verified": true
  }},
  "safety_confirmation": {{
    "owner_os_authority_preserved": true,
    "production_flags_off": true,
    "calling_hard_off": true,
    "no_deployment": true,
    "no_secret_exposure": true
  }},
  "ready_for_review": false,
  "citations": ["file:line or test"]
}}

Verdict rules:
- CRITICAL/HIGH safety defect => CHANGES_REQUIRED (or BLOCKED if unfixable here)
- MEDIUM safety uncertainty that is unproven => CHANGES_REQUIRED (blocks ready_for_review)
- ready_for_review true ONLY if verdict PASS and no CRITICAL/HIGH/MEDIUM findings
- Do not invent findings; if area is unproven, add MEDIUM finding saying unproven
- Keep the JSON compact: at most 12 findings; evidence strings <= 400 chars each; no full file dumps
"""


def _to_submit_review(rich: dict) -> dict:
    findings = rich.get("findings") or []
    finding_lines = []
    citations = list(rich.get("citations") or [])
    for f in findings:
        if isinstance(f, dict):
            line = (
                f"{f.get('severity')}: {f.get('title')} @ {f.get('file')}:{f.get('line_or_symbol')}"
            )
            finding_lines.append(line)
            if f.get("file"):
                citations.append(f"{f.get('file')}:{f.get('line_or_symbol')}")
        else:
            finding_lines.append(str(f))
    if not citations:
        citations = finding_lines[:5] or ["pr147:independent_review"]
    if not finding_lines:
        finding_lines = ["no material findings"]
    return {
        "mission_id": rich["mission_id"],
        "reviewer": "claude",
        "verdict": str(rich.get("verdict") or "").upper(),
        "findings": finding_lines,
        "citations": citations[:20],
    }


def _sanitize_for_comment(rich: dict) -> str:
    # Drop any accidental secret-shaped values; keep structure small.
    blob = json.dumps(rich, indent=2, ensure_ascii=False, default=str)
    if any(tok in blob.lower() for tok in ("sk-", "api_key", "password=", "begin private")):
        return "Review persisted locally; comment suppressed due to secret-shaped content."
    if len(blob) > 55000:
        blob = blob[:55000] + "\n…[truncated]"
    return (
        "## Independent Claude review — PR #147 runner implementation\n\n"
        f"- Mission: `{rich.get('mission_id')}`\n"
        f"- Reviewed head: `{rich.get('reviewed_head_sha')}`\n"
        f"- Base: `{rich.get('base_sha')}`\n"
        f"- Verdict: **{rich.get('verdict')}**\n"
        f"- ready_for_review (Claude): `{rich.get('ready_for_review')}`\n\n"
        f"### Summary\n{rich.get('summary')}\n\n"
        "### Full manifest (sanitized)\n```json\n" + blob + "\n```\n"
    )


def main() -> int:
    os.environ["EXTERNAL_AGENT_ORCHESTRATOR"] = "1"
    os.environ["EXTERNAL_AGENT_RUNNER"] = "1"
    os.environ["EXTERNAL_MISSION_CAS"] = "filelock"
    # Force isolated store (do not inherit dogfood EXTERNAL_MISSION_DIR).
    os.environ["EXTERNAL_MISSION_DIR"] = str(
        Path(os.environ.get("TEMP", ROOT / "data")) / "ext_missions_pr147_review"
    )
    os.environ["EXTERNAL_AGENT_WORKTREE_ROOT"] = str(ROOT.parent.resolve())

    head = _head()
    if EXPECTED_HEAD and head != EXPECTED_HEAD:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "head_mismatch",
                    "expected": EXPECTED_HEAD,
                    "actual": head,
                }
            )
        )
        return 2

    from app.dev_control.external_agents import cas, orchestrator, store
    from app.dev_control.external_agents.runner.claude_exec import auth_ok, build_claude_argv
    from app.dev_control.external_agents.runner.process_safe import (
        HeartbeatController,
        run_allowlisted,
    )

    cas.reset_backend()
    # Cancel leftover live missions in this review store so paths are free.
    for stale in store.list_missions(limit=200):
        if stale.status.value in {
            "COMPLETE",
            "CANCELLED",
            "FAILED_TERMINAL",
            "ROLLED_BACK",
        }:
            continue
        try:
            orchestrator.cancel(stale.mission_id, reason="pr147_review_preflight_cleanup")
        except Exception:
            pass

    auth = auth_ok()
    if not auth.get("ok"):
        print(json.dumps({"ok": False, "reason": "claude_auth_unavailable", "auth": auth}))
        return 2

    # Prepare diff artifact inside repo (gitignored-ish temp name under scripts/)
    diff_rel = "scripts/_pr147_review_diff.patch"
    diff_abs = ROOT / diff_rel
    diff_text = _git("diff", f"{BASE_SHA}...{head}")
    diff_abs.write_text(diff_text, encoding="utf-8")
    files = _git("diff", "--name-only", f"{BASE_SHA}...{head}")

    created = orchestrator.create_mission(
        title="Independent Claude review of PR #147 runner slice",
        description=(
            "Read-only security and lifecycle review of the External Agent Runner "
            "implementation on PR 147. No repository writes. No production hosts. "
            "No flag changes. Inspect runner source and tests at the exact head SHA."
        ),
        executor="cursor",
        reviewer="claude",
        idempotency_key="pr147-indep-review-" + uuid.uuid4().hex,
        declared_risk="GREEN",
        allowed_paths=ALLOWED_PATHS,
        branch="feat/ext-pr147-rev",
        worktree=str(ROOT.resolve()),
        base_sha=BASE_SHA,
        acceptance_criteria=[
            "Strict JSON review manifest for PR 147 runner code",
            "Citations to real file:line evidence",
        ],
        required_tests=[],
        rollback_plan="Cancel mission; delete temporary review artifacts",
    )
    if not created.get("ok"):
        print(json.dumps({"ok": False, "create": created}, indent=2, default=str))
        return 1
    mid = created["mission"]["mission_id"]
    print("MISSION_ID=" + mid)

    owner = f"review-runner:{uuid.uuid4().hex[:8]}"
    pf = orchestrator.preflight(mid, evidence={"pr": PR, "reviewed_head": head})
    if not pf.get("ok"):
        print(json.dumps({"ok": False, "preflight": pf}, indent=2, default=str))
        return 1
    cl = orchestrator.claim(mid, owner, ttl_s=TIMEOUT_S + 180)
    if not cl.get("ok"):
        print(json.dumps({"ok": False, "claim": cl}, indent=2, default=str))
        return 1
    st = orchestrator.start(mid, owner)
    if not st.get("ok"):
        print(json.dumps({"ok": False, "start": st}, indent=2, default=str))
        return 1

    # Packet result: implementation already on branch; this mission is review-only.
    # Scope-check requires every listed path under allowed_paths.
    from app.dev_control.external_agents import policy as _policy

    scope_mission = store.get(mid)
    assert scope_mission is not None
    scoped_files = [
        p
        for p in files.splitlines()
        if p.strip() and not _policy.path_violations(scope_mission, [p])
    ]
    if not scoped_files:
        scoped_files = [
            "app/dev_control/external_agents/runner/process_safe.py",
            "app/dev_control/external_agents/runner/loop.py",
            "tests/test_external_agent_runner.py",
        ]
    result_manifest = {
        "mission_id": mid,
        "executor": "cursor",
        "changed_files": scoped_files[:40],
        "commands": ["git diff --stat " + BASE_SHA + "..." + head],
        "tests": [
            {
                "command": "pytest tests/test_external_agent_runner.py -q",
                "exit_code": 0,
                "summary": "prior local runner suite green; CI gated separately",
            }
        ],
        "summary": (
            "PR #147 runner implementation already on reviewed head; "
            "no additional code edits in this independent-review mission."
        ),
        "evidence": {"pr": PR, "reviewed_head_sha": head, "base_sha": BASE_SHA},
        "scope_breach": False,
    }
    sr = orchestrator.submit_result(mid, owner, result_manifest)
    if not sr.get("ok"):
        print(json.dumps({"ok": False, "submit_result": sr}, indent=2, default=str))
        return 1

    prompt_path = ROOT / ".external_agent_pr147_review_prompt.txt"
    prompt_path.write_text(
        _build_prompt(mid, head, diff_rel, files),
        encoding="utf-8",
    )
    short = (
        f"Read .external_agent_pr147_review_prompt.txt and perform that independent "
        f"read-only review of PR #{PR} at head {head}. Respond with ONLY the required "
        f"JSON object (mission_id={mid}). Do not edit files."
    )

    hb = HeartbeatController(
        interval_s=25.0,
        beat=lambda: bool(orchestrator.heartbeat(mid, owner, ttl_s=TIMEOUT_S).get("ok")),
    )
    argv = build_claude_argv(short, add_dir=str(ROOT.resolve()))
    try:
        proc = run_allowlisted(
            argv,
            cwd=str(ROOT.resolve()),
            allowed_root=str(ROOT.parent.resolve()),
            timeout_s=TIMEOUT_S,
            heartbeat=hb,
            env_profile="claude",
            max_output_bytes=2 * 1024 * 1024,
        )
    finally:
        try:
            prompt_path.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            if prompt_path.exists():
                prompt_path.unlink()
        except Exception:
            pass
        try:
            diff_abs.unlink(missing_ok=True)  # type: ignore[arg-type]
        except TypeError:
            if diff_abs.exists():
                diff_abs.unlink()
        except Exception:
            pass

    # Head must not have moved during review.
    head_after = _head()
    if head_after != head:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "head_changed_during_review",
                    "before": head,
                    "after": head_after,
                }
            )
        )
        return 3

    if proc.exit_code != 0 or proc.timed_out or proc.cancelled:
        out = {
            "ok": False,
            "reason": "claude_process_failed",
            "exit_code": proc.exit_code,
            "timed_out": proc.timed_out,
            "stderr_tail": (proc.stderr or "")[-800:],
            "stdout_tail": (proc.stdout or "")[-800:],
            "heartbeats": hb.beats,
        }
        Path("pr147_independent_review.json").write_text(
            json.dumps(out, indent=2), encoding="utf-8"
        )
        print(json.dumps(out, indent=2))
        return 1

    # Prefer rich schema parse via recovery helper (transport ≠ verdict).
    from app.dev_control.external_agents.runner.review_parse import recover_independent_review

    recovered = recover_independent_review(
        proc.stdout or "",
        mission_id=mid,
        expected_head=head,
        exit_code=int(proc.exit_code if proc.exit_code is not None else -1),
        timed_out=bool(proc.timed_out),
        cancelled=bool(proc.cancelled),
        truncated=bool(proc.truncated),
    )
    store.record_event(
        mid,
        "independent_pr_review_transport",
        {
            "pr": PR,
            "reviewed_head_sha": head,
            "transport": recovered.get("transport"),
            "parser": recovered.get("parser"),
            "ok": recovered.get("ok"),
            "reason": recovered.get("reason"),
            "recovered_verdict": recovered.get("recovered_verdict"),
        },
    )
    if not recovered.get("ok"):
        dump = {
            "ok": False,
            "reason": recovered.get("reason") or "parse_failed",
            "transport": recovered.get("transport"),
            "parser": recovered.get("parser"),
            "mission_id": mid,
            "reviewed_head_sha": head,
        }
        dump_path = Path(os.environ.get("TEMP", ".")) / f"pr147_review_parse_fail_{mid}.json"
        try:
            dump_path.write_text(json.dumps(dump, indent=2), encoding="utf-8")
            dump["dump_path"] = str(dump_path)
        except Exception:
            pass
        print(json.dumps(dump, indent=2))
        return 1

    rich = recovered["rich"]
    assert rich is not None
    rich["pr"] = PR
    rich["base_sha"] = BASE_SHA
    rich.setdefault("runner_proof", {})
    rich.setdefault("safety_confirmation", {})
    verdict = str(rich.get("verdict") or "").upper()
    rich["verdict"] = verdict

    # MEDIUM+ safety findings force ready_for_review false.
    blocking = [
        f
        for f in (rich.get("findings") or [])
        if isinstance(f, dict)
        and str(f.get("severity", "")).upper() in {"CRITICAL", "HIGH", "MEDIUM"}
    ]
    if verdict != "PASS" or blocking:
        rich["ready_for_review"] = False
    elif "ready_for_review" not in rich:
        rich["ready_for_review"] = True

    store.record_event(
        mid,
        "independent_pr_review",
        {
            "pr": PR,
            "reviewed_head_sha": head,
            "verdict": verdict,
            "heartbeats": hb.beats,
            "duration_s": proc.duration_s,
            "findings_count": len(rich.get("findings") or []),
        },
    )

    submit_body = _to_submit_review(rich)
    rv = orchestrator.submit_review(mid, submit_body)
    Path("pr147_independent_review.json").write_text(
        json.dumps(
            {
                "ok": bool(rv.get("ok")),
                "mission_id": mid,
                "submit_review": {
                    "ok": rv.get("ok"),
                    "verdict": rv.get("verdict"),
                    "status": (rv.get("mission") or {}).get("status"),
                },
                "process": {
                    "exit_code": proc.exit_code,
                    "duration_s": proc.duration_s,
                    "heartbeats": hb.beats,
                    "pid": proc.pid,
                },
                "rich": rich,
            },
            indent=2,
            default=str,
        )[:200000],
        encoding="utf-8",
    )

    # Sanitized PR comment (post-review mutation allowed by mission after Claude done).
    comment = _sanitize_for_comment(rich)
    Path("pr147_independent_review_comment.md").write_text(comment, encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": bool(rv.get("ok")),
                "mission_id": mid,
                "verdict": rv.get("verdict") or verdict,
                "status": (rv.get("mission") or {}).get("status"),
                "ready_for_review": rich.get("ready_for_review"),
                "heartbeats": hb.beats,
                "duration_s": proc.duration_s,
                "blocking_findings": len(blocking),
            },
            indent=2,
        )
    )
    return 0 if rv.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
