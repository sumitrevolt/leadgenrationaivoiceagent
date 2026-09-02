#!/usr/bin/env python3
"""buzz_setup_apply — owner-run Buzz workspace mutations, one command.

Everything here changes the shared Buzz workspace, so it is dry-run by default
and every step is idempotent-ish (Buzz opens a review form; you still click Save).

    python scripts/buzz_setup_apply.py                 # print the plan, change nothing
    python scripts/buzz_setup_apply.py --print-prompt  # just the prompt, to paste
    python scripts/buzz_setup_apply.py --apply         # needs BUZZ_AUTH_TAG (see below)

**`--apply` does not work today, by product design.** It returns
`auth error: agent draft requests require BUZZ_AUTH_TAG` — the NIP-OA owner
attestation. Verified 2026-08-09 that the tag is not in the Windows credential
store, not obtainable from the relay (NIP-11 JSON only, no web UI), and not
behind any local port (Buzz Desktop listens on none). Desktop mints it
in-process, so creating an agent is an owner UI action. Use `--print-prompt` and
paste; keep `--apply` for the day Buzz exposes a tag.

Why a script and not a doc: `buzz agents draft-create` takes a multi-line system
prompt on stdin. Pasting that by hand into PowerShell mangles the quoting every
time (three separate sessions have hit it). The prompt lives here as text.

WHAT THIS DOES NOT DO: it does not create a live agent. `draft-create` opens a
prefilled form in the owner's Buzz Desktop; the harness, model and permissions
are chosen there and the agent exists only after the owner clicks Save. Until
then the agent is CODE-READY, not LIVE — same distinction as
`enterprise_profile_ready` vs rollout-live in ADR-164.

Runbook: ~/.buzz/GUIDES/BUZZ_END_TO_END_RUNBOOK.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

RELAY = "https://leadsgenai.communities.buzz.xyz"
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"

# Name check: must collide with neither the 31 runtime STAFF in
# app/platform/team.py nor the four existing Buzz agents (Boss/Honey/Fizz/
# Bumble). Inventing a 32nd STAFF persona is a RED-tier refusal in
# ~/.buzz/GUIDES/AUTONOMY_POLICY.md, so the reviewer gets its own bee name.
COMB_PROMPT = """\
You are Comb, the independent reviewer on the LeadGen Buzz plane.

You run on the Codex harness. Fizz runs on Claude Code. That difference is the
entire point of you: you are a second opinion produced by a different model and
a different toolchain, not a second copy of the same one. If you agree with
Fizz, say so briefly. If you disagree, say exactly where and why, with file:line.

Your job
- Review diffs, patches and PRs raised in #dev. Find real defects.
- Report every finding with a confidence level and a severity. Do NOT filter to
  "only important issues" — a later pass does the filtering. Coverage is your job.
- Cite file:line for every claim. A finding without a location is a rumour.

Hard rules (these are refusals, not preferences)
- READ-ONLY. You do not edit files, commit, push or deploy. You raise findings;
  the owner routes the fix. Deploy is scripts/deploy_vps.sh and never you.
- Claim before you read widely, release when you stop:
  python scripts/buzzlock.py claim <paths> --tool CODEX --reason "<why>"
  python scripts/buzzlock.py release <paths> --tool CODEX --evidence "<proof>"
  Exit 2 on claim means another tool holds the file. Stop and take other work.
- Prefix every #build message with [CODEX] so the handoff is traceable.
- Never weaken a compliance gate. DND fail-closed, the TRAI 10-19 IST calling
  window, AI disclosure, consent suppression, DPDP retention and the billing
  truth in packages.py are not negotiable, and a change that loosens one is an
  ABORT you report, not a tradeoff you weigh.
- Never print a secret. Env var NAMES are fine; values never.
- Swara / the voice path is FROZEN. Review it, never propose edits to it.

Evidence discipline
- "Tests pass" is not evidence. Exit codes, pytest output and /health.version are.
- Absence of an error is not proof a fix worked. Check when the error series
  actually stopped before crediting anything.

Answer in Hinglish (Roman), concise, no filler.
"""

STEPS = [
    {
        "name": "Comb (Codex-harness reviewer)",
        "channel": "dev",
        "display_name": "Comb",
        "prompt": COMB_PROMPT,
        "desktop_form": [
            "Harness  : Codex  (Buzz ships codex-acp at %APPDATA%\\Buzz\\node-tools\\codex-acp)",
            "Model    : your Codex subscription default",
            "Respond  : owner-only  (matches AGENT_ROLES.md - stops agent @-loops)",
            "Channels : #dev and #build; do NOT grant #admin or #revenue",
            "Write    : none. Comb is read-only by role.",
        ],
    },
]


def _buzz_exe() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise SystemExit("LOCALAPPDATA unset — cannot locate buzz.exe")
    exe = Path(local) / "Buzz" / "buzz.exe"
    if not exe.exists():
        raise SystemExit(f"buzz.exe not found at {exe} — is Buzz Desktop installed?")
    return exe


def _channels() -> dict:
    if not CHANNEL_IDS.exists():
        raise SystemExit(f"channel map missing: {CHANNEL_IDS}")
    return json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))


def _owner_nsec() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from buzzlock import _owner_nsec as read_cred  # noqa: PLC0415

    nsec = read_cred()
    if not nsec:
        raise SystemExit("Buzz owner credential not readable. Open Buzz Desktop and sign in first.")
    return nsec


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="buzz_setup_apply",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="try to open the drafts in Buzz Desktop — needs BUZZ_AUTH_TAG (see below)",
    )
    ap.add_argument(
        "--print-prompt",
        action="store_true",
        help="print the system prompt only, ready to paste into the Desktop form",
    )
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    if args.print_prompt:
        for step in STEPS:
            print(step["prompt"])
        return 0

    channels = _channels()
    exe = _buzz_exe()

    print("=== buzz_setup_apply ===")
    print(f"relay: {RELAY}")
    print(f"mode : {'APPLY' if args.apply else 'DRY-RUN (nothing changes)'}\n")

    for step in STEPS:
        cid = channels.get(step["channel"])
        if not cid:
            print(f"[skip] {step['name']}: no channel id for #{step['channel']}")
            continue

        print(f"--- {step['name']} -> #{step['channel']} ({cid})")
        print("    Then set these IN THE DESKTOP FORM before saving:")
        for line in step["desktop_form"]:
            print(f"      - {line}")

        if not args.apply:
            print("    command (not run):")
            print(
                f"      buzz.exe --relay {RELAY} agents draft-create "
                f'--channel {cid} --display-name "{step["display_name"]}" '
                f"--system-prompt -"
            )
            print()
            continue

        env = dict(os.environ)
        env["BUZZ_PRIVATE_KEY"] = _owner_nsec()
        r = subprocess.run(
            [
                str(exe),
                "--relay",
                RELAY,
                "--format",
                "json",
                "agents",
                "draft-create",
                "--channel",
                cid,
                "--display-name",
                step["display_name"],
                "--system-prompt",
                "-",
            ],
            input=step["prompt"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
        )
        if r.returncode != 0:
            print(f"    FAILED rc={r.returncode}: {(r.stderr or '')[:300]}", file=sys.stderr)
            return 3
        print("    draft opened in Buzz Desktop — switch to it and click Save.\n")

    if not args.apply:
        print("Nothing changed. Re-run with --apply to open the drafts.")
    else:
        print("Drafts opened. An agent is LIVE only after you Save it in Desktop.")
        print("Verify: @mention it in #dev with a resolved mention chip (plain")
        print("text that looks like a mention does not wake a Buzz agent).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
