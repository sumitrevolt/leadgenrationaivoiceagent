#!/usr/bin/env python3
"""Make one Boss identity canonical across every Buzz channel.

RUN ONCE, SUCCESSFULLY — 2026-08-09. `--apply` moved Boss across all seven
channels, every call `rc=0`, and a read-back confirmed `A present=False,
C present=True` everywhere. Re-running `--apply` now is a no-op-ish repeat; use
the default (read-only) to inspect state, and `--rollback` to undo.

WHY (evidence, 2026-08-09):
  Three identities answer to "Boss".
    20b69265  member/admin of all 7 channels · NO private key on this machine
    1b13cecc  private key IS in the credential store · member of NO channel
    bcf2f580  neither · never posted
  Three of the four stored agent keys (Honey, Fizz, Bumble) have running
  harnesses. Boss is the odd one out, and the Boss that is *in* the channels is
  the one this machine cannot run. So mentions resolve to an identity that can
  never answer.

DECISION: canonical Boss = 1b13cecc — the only Boss this machine can operate.
Membership without an operable credential is not operability.

WHAT THIS DOES (in order, so there is never zero Boss):
  1. adds 1b13cecc to every channel where 20b69265 is a member, mirroring its role
  2. re-reads membership and refuses to continue unless step 1 fully succeeded
  3. removes 20b69265 from those channels

History is never touched — past messages stay attributed to whoever sent them.
Removal is membership-only and is reversible with the printed rollback commands.

    python scripts/buzz_canonicalize_boss.py              # read-only plan
    python scripts/buzz_canonicalize_boss.py --apply      # execute
    python scripts/buzz_canonicalize_boss.py --rollback   # restore from snapshot
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "docs" / "coordination" / "BUZZ_MEMBERSHIP_SNAPSHOT.json"

# Nostr PUBLIC keys. They are 64-char hex — the same shape as a private key —
# so the entropy scanner flags them; they are published identifiers that appear
# in every `channels members` listing. No private key is stored in this file.
BOSS_A = (
    "20b69265b32c3f4f07db0cdd457c329c4618434d23f9e5c54ada84720a31270a"  # pragma: allowlist secret
)
BOSS_C = (
    "1b13ceccc2a6966064835fd942a55c8015a34a7c0f14a3462c0d845440f4e92f"  # pragma: allowlist secret
)


def _load():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from buzz_admin_setup import CHANNEL_IDS, run  # noqa: PLC0415

    return run, json.loads(CHANNEL_IDS.read_text(encoding="utf-8-sig"))


def members(run, cid: str) -> dict[str, str]:
    rc, out, _ = run(["channels", "members", "--channel", cid])
    if rc != 0:
        return {}
    d = json.loads(out)
    items = d if isinstance(d, list) else (d.get("members") or [])
    return {m.get("pubkey"): m.get("role") for m in items if m.get("pubkey")}


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="buzz_canonicalize_boss",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    run, ch = _load()
    if not SNAPSHOT.exists():
        raise SystemExit(f"snapshot missing: {SNAPSHOT} — refusing to change membership blind")
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    if args.rollback:
        print("=== ROLLBACK: restore Boss#A, remove Boss#C ===")
        for name, ms in snap["channels"].items():
            role = next((m["role"] for m in ms if m["pubkey"] == BOSS_A), None)
            if not role:
                continue
            rc, _, err = run(
                [
                    "channels",
                    "add-member",
                    "--channel",
                    ch[name],
                    "--pubkey",
                    BOSS_A,
                    "--role",
                    role,
                ]
            )
            print(f"  #{name:9} restore A role={role:6} rc={rc} {'' if rc == 0 else err[:90]}")
            rc, _, err = run(
                ["channels", "remove-member", "--channel", ch[name], "--pubkey", BOSS_C]
            )
            print(f"  #{name:9} remove  C            rc={rc} {'' if rc == 0 else err[:90]}")
        return 0

    targets = {
        n: next((m["role"] for m in ms if m["pubkey"] == BOSS_A), None)
        for n, ms in snap["channels"].items()
    }
    targets = {n: r for n, r in targets.items() if r}

    print("=== canonicalize Boss -> 1b13cecc ===")
    print(f"mode: {'APPLY' if args.apply else 'DRY-RUN (reads only)'}\n")
    for name, role in targets.items():
        live = members(run, ch[name])
        print(f"  #{name:9} role={role:6} | A present={BOSS_A in live} C present={BOSS_C in live}")

    if not args.apply:
        print("\nNothing changed. Re-run with --apply.")
        print("Rollback afterwards: python scripts/buzz_canonicalize_boss.py --rollback")
        return 0

    print("\nSTEP 1 — add canonical Boss")
    for name, role in targets.items():
        rc, _, err = run(
            ["channels", "add-member", "--channel", ch[name], "--pubkey", BOSS_C, "--role", role]
        )
        print(f"  #{name:9} add C role={role:6} rc={rc} {'' if rc == 0 else err[:90]}")

    print("\nSTEP 2 — verify before removing anything")
    missing = [n for n in targets if BOSS_C not in members(run, ch[n])]
    if missing:
        print(f"  REFUSED: canonical Boss not present in {missing}.")
        print("  Boss#A left in place — a half-migration is worse than none.")
        return 2
    print("  canonical Boss present in every target channel")

    print("\nSTEP 3 — retire Boss#A (membership only; history untouched)")
    for name in targets:
        rc, _, err = run(["channels", "remove-member", "--channel", ch[name], "--pubkey", BOSS_A])
        print(f"  #{name:9} remove A rc={rc} {'' if rc == 0 else err[:90]}")

    print("\nDone. Rollback: python scripts/buzz_canonicalize_boss.py --rollback")
    print("Boss still needs a harness: python scripts/buzz_start_harness.py --agent Boss")
    print("Then canary at >=600s. Presence alone is not proof.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
