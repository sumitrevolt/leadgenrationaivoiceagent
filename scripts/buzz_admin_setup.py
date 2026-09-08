#!/usr/bin/env python3
"""buzz_admin_setup — make the Buzz workspace self-documenting.

The protocol lives in ~/.buzz/GUIDES/ on ONE machine. Agents in the workspace
cannot read that, so they cannot follow it. This publishes the rules into Buzz
itself: channel canvases (what a tool sees when it opens #build / #dev) and a
NIP-23 note (the full runbook, readable by any member on any machine).

    python scripts/buzz_admin_setup.py               # show current state, change nothing
    python scripts/buzz_admin_setup.py --apply       # write canvases + note

`canvas set` REPLACES the document, so --show prints what is there now and
--apply refuses to clobber a canvas it did not author unless you pass --force.
Read before you overwrite; that rule applies to shared workspaces too.

Runbook source of truth stays ~/.buzz/GUIDES/BUZZ_END_TO_END_RUNBOOK.md — this
publishes a copy so the workspace is not dependent on one laptop.
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
RUNBOOK = Path.home() / ".buzz" / "GUIDES" / "BUZZ_END_TO_END_RUNBOOK.md"

# Both canvases below are SUPERSETS of what was already published on
# 2026-08-03/05. Every existing line is preserved verbatim; only new material is
# added. The guard in `_dropped_lines` enforces that mechanically — this comment
# is the intent, that function is the proof.

BUILD_CANVAS = """# #build — Coding Agent Bridge

**Plane:** developer tooling. NOT runtime STAFF, NOT prod control.

## Who posts here

| Prefix | Tool | Typical job |
|--------|------|-------------|
| `[CURSOR]` | Cursor | IDE-side edits, refactors, inline fixes |
| `[CLAUDE]` | Claude Code / Cowork | Multi-file changes, audits, loop-engineer runs |
| `[CODEX]` | Codex | Independent review of a Claude-authored diff; scripted patches |
| `[GOOSE]` | Goose | Block's harness; spikes and one-off automation |
| `[OPENCODE]` | OpenCode | Terminal-driven patches, scripted edits |
| `[FREEBUFF]` | Freebuff | Desktop-app sessions (Electron; no headless mode) |
| `[MONKEY]` | Monkey Code | Experiments, throwaway spikes |

Every message MUST start with the prefix. No prefix = untraceable = ignore it.

`[CODEX]` is the keyboard-side Codex CLI. The Buzz agent **Comb** also runs on
Codex and uses the same prefix and the same locks — one identity per harness, so
a line reads the same whoever drove it. Freebuff and OpenCode cannot be Buzz
agents (Electron app / no binary on PATH); prefix + handoff is their complete
integration, not a placeholder.

## Claim-before-edit (hard rule)

The repo tree is chronically dirty and multiple tools edit it at once.
Truncation and lost edits have already happened. So:

1. **CLAIM** before touching files:
   `[CLAUDE] CLAIM app/api/growth_revenue.py, tests/test_billing_truth_2026.py — reason: ADR-159 canary`
2. **RELEASE** when done:
   `[CLAUDE] RELEASE app/api/growth_revenue.py — 3 tests green, exit 0`
3. If a file is already claimed, **do not edit it**. Post `[TOOL] BLOCKED ON <file> (held by <tool>)` and pick different work.
4. Claims older than 4 hours are stale — anyone may post `STALE-BREAK <file>` and take it.

Machine-readable mirror: `docs/coordination/LOCKS.json` in the repo.

Use the CLI, do not hand-edit the JSON — it writes atomically and posts the
matching `#build` line in the same step:

```
python scripts/buzzlock.py status
python scripts/buzzlock.py claim <paths> --tool <TOOL> --reason "<why>"
python scripts/buzzlock.py release <paths> --tool <TOOL> --evidence "<proof>"
```

**Exit 2 on claim = another tool holds it. That is a stop, not a warning.**
Exit 1 = usage error, exit 0 = ok. Branch on 2 and only 2.
(Until 2026-08-09 argparse also exited 2 on a typo'd flag, so a bad `--tool` read
as a refusal — fixed, and pinned by tests.)
`LOCKS.json` is gitignored and per-checkout; the CLI creates it on first use.

A claim is only refused if the holder is a **different** tool **and** the lock is
not stale (`stale_after_minutes`, default 240) — a stale lock is taken silently
and returns 0.

## Handoff format

```
[TOOL] HANDOFF -> <next tool>
Goal:      <one line>
Done:      <what actually landed>
Evidence:  <exit codes / pytest / /health.version>
Left:      <precise next step>
Touched:   <file list>
```

## Non-negotiable

- Never `git add -A`. Stage explicit paths only.
- No commit / push / deploy without owner asking. Deploy = `scripts/deploy_vps.sh` + `APP_VERSION=<sha>`.
- Evidence beats prose. Exit code or it did not happen.
- Secrets never in a message. Env var NAMES fine, values never.
- Swara / voice path = FROZEN.
"""

DEV_CANVAS = """# Dev
Checkout: REPOS/leadgenrationaiagent → Documents/leadgenrationaiagent
Context first: docs/context/{CURRENT_STATE,ACTIVE_WORK,SESSION_HANDOFF}.md
No commit/push without owner ask. Swara/voice FROZEN.

---

## Cross-check: two harnesses, owner-routed

## Cross-check: two harnesses, owner-routed

```
owner: @Fizz implement X          (Claude Code harness)
Fizz:  patch + evidence
owner: @Comb review Fizz's patch  (Codex harness)
Comb:  findings — file:line + confidence + severity
owner: decides
```

**Agents do not @mention each other.** Respond-policy is owner-only on purpose —
it stops @-loops. The owner routes the second opinion.

Why a different harness: two agents on the same model correlate their mistakes.
Comb runs on Codex precisely so it fails differently from Fizz.

## Reviewer rules

- **Coverage, not filtering.** Report every finding with confidence and
  severity. "Only high-severity issues" makes a reviewer withhold real bugs —
  recall drops while it looks more precise. A later pass does the filtering.
- **file:line or it didn't happen.** A finding without a location is a rumour.
- **Evidence beats prose.** Exit codes, pytest output, `/health.version`.
  "Tests pass" is not evidence.
- Absence of an error is not proof a fix worked — check when the error series
  actually stopped before crediting anything.

## Refusals (not tradeoffs)

DND fail-closed · TRAI 10-19 IST calling window · AI disclosure · consent
suppression · DPDP retention · billing truth in `packages.py`. A change that
loosens one of these is an ABORT you report, not a cost you weigh.
Swara / the voice path is FROZEN — review it, never propose edits to it.

## Wake an agent properly

Use a **resolved @mention chip**. Plain text that looks like a mention does not
wake a Buzz agent, and a thread reply without a fresh mention does not retrigger
one. A workspace that looks dead is almost always this.
"""

OWNER_BRIEF = """\
**[SETUP] Buzz multi-harness plane — ADR-167**

Workspace is now self-documenting. `#build` and `#dev` canvases carry the
protocol, and the full runbook is published as a note (`buzz-end-to-end-runbook`)
so it is readable from any machine, not just one laptop.

**What changed**
- `#build` canvas: tool table now has `[CODEX]` `[GOOSE]` `[FREEBUFF]` + the
  buzzlock CLI. Every previous line preserved.
- `#dev` canvas: added the owner-routed cross-check contract.
- Cost/quota report posted to `#ops`. Headline: **Codex subscription peaked at
  100% in 7 days** — quota, not money, is what takes an agent offline here.

**One action left for you (~30 seconds)**
Comb — the Codex-harness reviewer — is CODE-READY but not created. Agent creation
**cannot be scripted at all**: `agents draft-create` needs a NIP-OA auth tag,
Buzz Desktop mints it in-process, and it is not in the credential store, on the
relay, or behind any local port. Checked all three. It needs your click.

In Buzz Desktop: create agent in `#dev`, name **Comb**, harness **Codex**,
respond **owner-only**, channels `#dev` + `#build` only.

For the system prompt, run this and paste the output into the form:

```
python scripts/buzz_setup_apply.py --print-prompt
```

**Why a second harness:** Fizz runs on Claude Code. Two agents on the same model
correlate their mistakes, so a same-harness "review" is theatre. Comb fails
differently, which is the entire point.

Route work as: `@Fizz` builds -> `@Comb` reviews -> you decide. Agents do not
mention each other; owner-only respond policy is deliberate and stays.
"""

NOTE_NAME = "buzz-end-to-end-runbook"
NOTE_TITLE = "Buzz End-to-End Runbook — multi-harness + OmniRoute combos"
NOTE_SUMMARY = (
    "How this workspace is wired: two harnesses (Claude + Codex), seven "
    "keyboard tools under file locks, the owner-routed cross-check, and the "
    "OmniRoute free-provider lane that absorbs quota pressure."
)
NOTE_TAGS = ["buzz", "leadgen", "runbook", "omniroute", "codex"]


def _buzz_exe() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise SystemExit("LOCALAPPDATA unset — cannot locate buzz.exe")
    exe = Path(local) / "Buzz" / "buzz.exe"
    if not exe.exists():
        raise SystemExit(f"buzz.exe not found at {exe}")
    return exe


def _nsec() -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from buzzlock import _owner_nsec  # noqa: PLC0415

    nsec = _owner_nsec()
    if not nsec:
        raise SystemExit("Buzz owner credential unavailable — sign in to Buzz Desktop.")
    return nsec


def run(args: list[str], stdin: str | None = None) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = _nsec()
    r = subprocess.run(
        [str(_buzz_exe()), "--relay", RELAY, "--format", "json", *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=180,
    )
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _dropped_lines(current: str | None, new: str) -> list[str]:
    """Non-blank lines in the live canvas that the new body does not contain.

    `canvas set` replaces the whole document, so the only honest safety check is
    "does my replacement still say everything the old one said". Whitespace is
    normalised because reflowing a paragraph is not data loss; a missing rule is.
    """
    if not (current or "").strip():
        return []
    have = {" ".join(line.split()) for line in new.splitlines()}
    return [
        line.strip()
        for line in current.splitlines()
        if line.strip() and " ".join(line.split()) not in have
    ]


def canvas_get(cid: str) -> str | None:
    rc, out, _ = run(["canvas", "get", "--channel", cid])
    if rc != 0:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return out
    if isinstance(data, dict):
        for key in ("content", "canvas", "document", "text"):
            if isinstance(data.get(key), str):
                return data[key]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="buzz_admin_setup",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--apply", action="store_true", help="write canvases and the note")
    ap.add_argument(
        "--dump",
        action="store_true",
        help="print each canvas in full and exit — read it before you replace it",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="replace a canvas even though lines would be lost (destructive)",
    )
    ap.add_argument(
        "--brief",
        action="store_true",
        help="also post the owner brief to #admin (requires --apply)",
    )
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    channels = json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))
    targets = [("build", BUILD_CANVAS), ("dev", DEV_CANVAS)]

    print("=== buzz_admin_setup ===")
    print(f"mode: {'APPLY' if args.apply else 'SHOW (nothing changes)'}\n")

    if args.dump:
        for name, _ in targets:
            cid = channels.get(name)
            if not cid:
                continue
            print(f"########## #{name} ##########")
            print(canvas_get(cid) or "<empty>")
            print()
        return 0

    for name, body in targets:
        cid = channels.get(name)
        if not cid:
            print(f"[skip] #{name}: no channel id")
            continue

        current = canvas_get(cid)
        dropped = _dropped_lines(current, body)
        print(
            f"--- #{name} canvas: {len(current or '')} chars now -> {len(body)} chars"
            f" ({len(dropped)} line(s) would be lost)"
        )

        if dropped and not args.force:
            print("    REFUSED — this is not a superset. These lines would vanish:")
            for line in dropped[:8]:
                print(f"      - {line}")
            if len(dropped) > 8:
                print(f"      ... and {len(dropped) - 8} more")
            print("    Fold them into the new body, or pass --force to drop them.")
            continue

        if not args.apply:
            print("    would write (superset — nothing lost)")
            continue

        rc, _, err = run(["canvas", "set", "--channel", cid, "--content", "-"], stdin=body)
        print("    written" if rc == 0 else f"    FAILED rc={rc}: {err[:200]}")

    # --- the runbook as a NIP-23 note ---------------------------------------
    print(f"\n--- note '{NOTE_NAME}'")
    if not RUNBOOK.exists():
        print(f"    [skip] runbook missing at {RUNBOOK}")
    elif not args.apply:
        print(f"    would publish {RUNBOOK.stat().st_size} bytes from {RUNBOOK.name}")
    else:
        cmd = [
            "notes",
            "set",
            "--name",
            NOTE_NAME,
            "--title",
            NOTE_TITLE,
            "--summary",
            NOTE_SUMMARY,
            "--content",
            "-",
        ]
        for t in NOTE_TAGS:
            cmd += ["--tag", t]
        rc, _, err = run(cmd, stdin=RUNBOOK.read_text(encoding="utf-8"))
        print("    published" if rc == 0 else f"    FAILED rc={rc}: {err[:200]}")

    if args.brief:
        cid = channels.get("admin")
        print("\n--- owner brief -> #admin")
        if not cid:
            print("    [skip] no #admin channel id")
        elif not args.apply:
            print(f"    would post {len(OWNER_BRIEF)} chars")
        else:
            rc, _, err = run(
                ["messages", "send", "--channel", cid, "--content", "-"], stdin=OWNER_BRIEF
            )
            print("    posted" if rc == 0 else f"    FAILED rc={rc}: {err[:200]}")

    if not args.apply:
        print("\nNothing changed. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
