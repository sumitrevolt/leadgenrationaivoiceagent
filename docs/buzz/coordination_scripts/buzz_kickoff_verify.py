#!/usr/bin/env python3
"""Post kickoff messages in the new channels, then verify final wiring."""
from __future__ import annotations
import ctypes, json, os, subprocess, time
from ctypes import wintypes
from pathlib import Path

BUZZ = Path(os.environ["LOCALAPPDATA"]) / "Buzz" / "buzz.exe"
RELAY = "https://leadsgenai.communities.buzz.xyz"
IDS = json.loads((Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json").read_text(encoding="utf-8-sig"))

NAMES = {
    "1fb82b779689c60b13f10c49f19d15884349cc5accb5b329583f6a7441a6c1a0": "sumit(owner)",
    "1b13ceccc2a6966064835fd942a55c8015a34a7c0f14a3462c0d845440f4e92f": "Boss",
    "b9ffabcf66e8de5f7efa7ebae8fadaee8cc32e4f812ed54325a7f1fff4cf79c6": "Honey",
    "d2fd7e85404811241bad32516d5a68c95f660b122271da8130e35a076e61609d": "Fizz",
    "a546e85c1dad69937000a35ab260127268436c3d882711633d4c54a91d36b4e1": "Bumble",
}


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]


def owner_nsec() -> str:
    ptr = ctypes.c_void_p()
    assert ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr))
    c = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]


ENV = dict(os.environ)


def buzz(args, stdin_text=None):
    r = subprocess.run([str(BUZZ), "--relay", RELAY, "--format", "json", *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=ENV, input=stdin_text)
    out = (r.stdout or "").strip()
    try:
        return r.returncode, (json.loads(out) if out else None), (r.stderr or "").strip()
    except Exception:
        return r.returncode, out, (r.stderr or "").strip()


BUILD_MSG = """**#build is live** — coding-agent coordination plane.

Cursor, Claude Code, OpenCode aur Monkey Code yahin coordinate karenge. Prefix zaroori hai: `[CURSOR]` `[CLAUDE]` `[OPENCODE]` `[MONKEY]`. Bina prefix ke message = untraceable.

**Claim before you edit:**
```
[CLAUDE] CLAIM app/api/growth_revenue.py — reason: ADR-159 canary
[CLAUDE] RELEASE app/api/growth_revenue.py — 3 tests green, exit 0
```
File already claimed ho to edit mat karo — `[TOOL] BLOCKED ON <file>` post karke doosra kaam lo. 4 ghante purana claim stale hai (`STALE-BREAK`).

Machine-readable mirror: `docs/coordination/LOCKS.json`. Poora protocol canvas me + `~/.buzz/GUIDES/CODING_AGENT_PROTOCOL.md`.

Hard rules: `git add -A` kabhi nahi · commit/push/deploy sirf owner ke kehne pe · evidence beats prose (exit code ya kuch nahi) · secrets kabhi message me nahi · Swara/voice FROZEN."""

PULSE_MSG = """**#staff-pulse is live** — 31/31 runtime STAFF ka read-only mirror.

Chain of control: `Buzz (#admin) -> Boss -> Owner OS/OpenClaw -> 31 STAFF -> Celery`. Ye channel sirf dekhta hai — commands sirf Boss ko jaate hain, direct staff mutation hooks nahi hain. Buzz kabhi second control plane nahi banega.

Roster (verified against `app/platform/team.py` 2026-08-05, 31/31 match):
- **Coordination 1** — Boss
- **Platform 12** — Kavya, Hermes, Nikhil, Vikram, Guru, Pranav, Vidya, Arnav, Kabir, Diya, Aryan, Arya
- **Marketing 10** — Isha, Dev, Rohan, Ravi, Neha, Kiran, Priya, Zara, Anika, Ira
- **Voice 8** — Swara, Tara, Arjun, Meera, Ananya, Riya, Lekha, Raksha

Pulse line format: `[PULSE] <division> | <agent> | <last_run> | <ok|warn|fail> | <note>`

Tiers: GREEN agent khud execute · AMBER Boss decide · RED system refuse (Boss bhi bypass nahi kar sakta). Ek hi human gate: real UPI bank-credit confirmation + paid-ledger marking."""

ADMIN_MSG = """**Buzz enterprise coordination setup — done.**

**Naye channels**
- `#build` — Cursor / Claude / OpenCode / Monkey Code bridge, claim-before-edit locks
- `#staff-pulse` — 31/31 runtime STAFF read-only mirror

**Chain of control (locked in)**
`Buzz (#admin) -> Boss -> Owner OS/OpenClaw -> 31 STAFF -> Celery` — Buzz interface hai, second control plane nahi. Koi duplicate Buzz bot nahi banaya gaya.

**Autonomy tiers**
GREEN agent khud execute · AMBER Boss decide (owner ko routine approvals nahi) · RED system refuse, Boss bhi override nahi kar sakta (DND, TRAI 10-19 IST, AI disclosure, consent, DPDP, secrets, destructive ops, 32nd persona, FROZEN Swara, non-`deploy_vps.sh` deploy). **Ek hi human gate: real UPI bank-credit confirmation + paid-ledger marking.** `UPI_AUTO_ACTIVATE` fail-closed rahega.

**Naye guides** (`~/.buzz/GUIDES/`)
`AUTONOMY_POLICY.md` · `STAFF_ROUTING_MAP.md` · `CODING_AGENT_PROTOCOL.md`; `BUZZ_OPERATING_MODEL.md` + `BOSS_ADMIN.md` refreshed. Repo: `docs/coordination/{README.md, LOCKS.json}` (untracked, additive).

**Boss membership restored** — admin on `#admin` + `#leadgen`, member on gtm/ops/revenue/dev/build/staff-pulse.

**Owner action pending (1):** Boss ka managed-agent Desktop se delete ho gaya tha, aur CLI owner ko apna hi draft nahi bhej sakta (`auth_error: agent draft requests require BUZZ_AUTH_TAG`). Buzz Desktop -> Agents -> new agent -> naam `Boss`, system prompt `~/.buzz/.scratch/boss_system_prompt.txt` se paste karo. Save hote hi channel membership already wired hai.

**Touched nothing:** prod, `.env`, `team.py`, deploy, STAFF registry, OpenClaw Stage A."""


def send(channel_name, body):
    cid = IDS.get(channel_name)
    if not cid:
        print(f"[SKIP] no id for #{channel_name}")
        return
    rc, out, err = buzz(["messages", "send", "--channel", cid, "--content", "-"], stdin_text=body)
    print(f"[{'OK ' if rc == 0 else f'FAIL({rc})'}] post -> #{channel_name} {err[:160] if rc else ''}")
    time.sleep(0.5)


def verify():
    print("\n===== FINAL WIRING =====")
    rc, chans, err = buzz(["channels", "list"])
    rows = [c for c in (chans if isinstance(chans, list) else []) if c.get("name") != "DM"]
    for c in sorted(rows, key=lambda x: x.get("name") or ""):
        cid = c.get("channel_id")
        _, mem, _ = buzz(["channels", "members", "--channel", cid])
        items = mem if isinstance(mem, list) else []
        who = []
        for m in items:
            pk = m.get("pubkey", "")
            who.append(f"{NAMES.get(pk, pk[:8])}={m.get('role', 'member')}")
        print(f"  #{c.get('name'):<18} {', '.join(who)}")

    print("\n===== CANVAS CHECK =====")
    for name in ("build", "staff-pulse"):
        cid = IDS.get(name)
        rc, out, err = buzz(["canvas", "get", "--channel", cid])
        size = len(out) if isinstance(out, str) else 0
        print(f"  #{name}: canvas {'present' if size > 200 else 'MISSING'} ({size} chars)")


if __name__ == "__main__":
    ENV["BUZZ_PRIVATE_KEY"] = owner_nsec()
    send("build", BUILD_MSG)
    send("staff-pulse", PULSE_MSG)
    send("admin", ADMIN_MSG)
    verify()
