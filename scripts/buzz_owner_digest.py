"""Owner coordination digest — saare Buzz channels ka readable snapshot EK file me.

Problem: Buzz Desktop me relay-posts collapsed cards ("show message") ki tarah
dikhte hain aur channels duplicate/confusing hain — owner ko coordination padhne
me jhol ho jata hai. Ye script sab channels ka recent traffic nikaal ke EK
markdown digest banati hai: ~/.buzz/OUTBOX/buzz_digest_<ts>.md

Usage:
  python scripts/buzz_owner_digest.py                # last 24h, file only
  python scripts/buzz_owner_digest.py --hours 48     # longer window
  python scripts/buzz_owner_digest.py --post         # #admin me summary post bhi

Read-only on the relay (sirf --post ek message bhejta hai). Owner key Windows
Credential Manager (secrets.buzz-desktop) se aati hai — kabhi log/file me nahi.

Known quirk: kuch purane posts relay pe hi cp1252-double-encoded ("â€”") stored
hain — _fix_mojibake() unhe display-time repair karta hai.
Exit codes: 0 ok, 1 config/CLI error.
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BUZZ = Path(os.environ.get("LOCALAPPDATA", "")) / "Buzz" / "buzz.exe"
RELAY = os.environ.get("BUZZ_RELAY", "ws://127.0.0.1:3100")
OUTBOX = Path.home() / ".buzz" / "OUTBOX"
CHANNEL_IDS = Path.home() / ".buzz" / "GUIDES" / "CHANNEL_IDS.json"
NAME_CACHE = Path.home() / ".buzz" / "GUIDES" / "PUBKEY_NAMES.json"

# Canonical channels pehle, baaki name-se (duplicates merge ho jaate hain).
PRIORITY = ["admin", "ops", "revenue", "gtm", "dev", "build", "leadgen", "staff-pulse"]
STATIC_NAMES = {
    "1fb82b779689c60b13f10c49f19d15884349cc5accb5b329583f6a7441a6c1a0": "Owner OS (@board)",
    "1b13ceccc2a6966064835fd942a55c8015a34a7c0f14a3462c0d845440f4e92f": "Boss",
}
MOJIBAKE_MARKERS = ("\u00e2\u20ac", "\u00e2\u201d", "\u00e2\u2019", "\u00c2")


def owner_nsec() -> str:
    from ctypes import wintypes
    ptr = ctypes.c_void_p()
    if not ctypes.windll.advapi32.CredReadW("secrets.buzz-desktop", 1, 0, ctypes.byref(ptr)):
        raise RuntimeError("Buzz desktop credential not found (secrets.buzz-desktop)")

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)), ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
        ]

    cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
    raw = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    ctypes.windll.advapi32.CredFree(ptr)
    return json.loads(raw.decode("utf-16-le").rstrip("\x00"))["identity"]


def buzz(args: list) -> tuple:
    """Run buzz CLI in BYTES mode; decode utf-8 ourselves (locale-proof)."""
    env = dict(os.environ)
    env["BUZZ_PRIVATE_KEY"] = owner_nsec()
    env["BUZZ_RELAY_URL"] = RELAY
    p = subprocess.run([str(BUZZ)] + args, capture_output=True, env=env, timeout=90)
    out = p.stdout.decode("utf-8", errors="replace")
    err = p.stderr.decode("utf-8", errors="replace")
    return p.returncode, out, err


def fix_mojibake(text: str) -> str:
    """cp1252->utf-8 double-encoded purane posts repair karo (best-effort)."""
    if not text or not any(m in text for m in MOJIBAKE_MARKERS):
        return text
    try:
        repaired = text.encode("cp1252").decode("utf-8")
        return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def load_channels() -> list:
    rc, out, err = buzz(["channels", "list", "--limit", "60"])
    if rc != 0:
        raise RuntimeError(f"channels list failed: {(err or out)[:200]}")
    data = json.loads(out)
    if isinstance(data, dict):
        data = data.get("channels") or data.get("items") or []
    def rank(ch):
        name = (ch.get("name") or "").lower()
        return (0, PRIORITY.index(name)) if name in PRIORITY else (1, name)
    return sorted(data, key=rank)


def resolve_names(pubkeys: set) -> dict:
    names = dict(STATIC_NAMES)
    if NAME_CACHE.exists():
        try:
            names.update(json.loads(NAME_CACHE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    missing = [pk for pk in pubkeys if pk not in names]
    if missing:
        rc, out, _ = buzz(["users", "get", "--pubkey", ",".join(missing)])
        if rc == 0:
            try:
                for u in json.loads(out):
                    pk = u.get("pubkey") or ""
                    nm = u.get("name") or u.get("display_name") or ""
                    if pk and nm:
                        names[pk] = nm
            except json.JSONDecodeError:
                pass
        try:
            NAME_CACHE.write_text(
                json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return names


def fetch_messages(cid: str, since: int, limit: int = 100) -> list:
    rc, out, _ = buzz(["messages", "get", "--channel", cid,
                       "--since", str(since), "--limit", str(limit)])
    if rc != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("messages") or data.get("items") or []
    return sorted(data, key=lambda m: m.get("created_at") or 0)


def fmt_ts(epoch) -> str:
    try:
        return datetime.fromtimestamp(int(epoch)).strftime("%d-%b %H:%M")
    except (TypeError, ValueError, OSError):
        return "?"


def clean(text: str) -> str:
    return fix_mojibake(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def post_to_admin(summary: str) -> bool:
    admin_cid = None
    if CHANNEL_IDS.exists():
        try:
            admin_cid = json.loads(CHANNEL_IDS.read_text(encoding="utf-8")).get("admin")
        except json.JSONDecodeError:
            pass
    if not admin_cid:
        print("POST SKIP: admin channel id CHANNEL_IDS.json me nahi mila")
        return False
    rc, out, err = buzz(["messages", "send", "--channel", admin_cid,
                         "--content", fix_mojibake(summary)])
    if rc != 0:
        print(f"POST FAILED rc={rc}: {(err or out)[:200]}")
        return False
    print("posted summary to #admin")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Buzz owner coordination digest")
    ap.add_argument("--hours", type=int, default=24, help="window in hours (default 24)")
    ap.add_argument("--post", action="store_true", help="#admin me short summary post karo")
    args = ap.parse_args()

    if not BUZZ.exists():
        print(f"buzz.exe not found at {BUZZ}")
        return 1
    since = int(time.time()) - args.hours * 3600

    try:
        channels = load_channels()
    except RuntimeError as e:
        print(e)
        return 1

    pubkeys = set()
    per_ch = {}
    for ch in channels:
        msgs = fetch_messages(ch["channel_id"], since)
        per_ch[ch["channel_id"]] = msgs
        pubkeys.update(m.get("pubkey") or "" for m in msgs)
    pubkeys.discard("")
    names = resolve_names(pubkeys)

    digest = _build_from_cache(channels, per_ch, names, args.hours, since)

    OUTBOX.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = OUTBOX / f"buzz_digest_{stamp}.md"
    path.write_text(digest, encoding="utf-8")
    print(f"digest written: {path}")

    if args.post:
        sections = [ln for ln in digest.splitlines() if ln.startswith("## ")]
        summary = (f"**[DIGEST]** {len(sections)} active channels — full: {path}\n"
                   + "\n".join(sections[:8]))
        post_to_admin(summary)
    return 0


def _build_from_cache(channels, per_ch, names, hours, since) -> str:
    """Same rendering as build_digest but uses prefetched messages."""
    by_name = {}
    for ch in channels:
        by_name.setdefault(ch.get("name") or "?", []).append(ch)
    order = sorted(by_name.values(),
                   key=lambda g: ((1, "") if g[0].get("name", "").lower() not in PRIORITY
                                  else (0, PRIORITY.index(g[0]["name"].lower()))))
    now = datetime.now().strftime("%d-%b %Y %H:%M IST")
    lines = [
        "# BUZZ OWNER DIGEST",
        f"_Generated {now} — window: last {hours}h — relay: {RELAY}_",
        "",
        "> Har channel ka section, messages oldest→newest. Truncated `…` = poora message Desktop/app me.",
        "> Agent ko jagane ke liye @Name RESOLVED chip hona chahiye — plain-text @Name mention NAHI hai.",
        "",
    ]
    total = active = 0
    for group in order:
        merged, seen_ids = [], set()
        desc = next((clean(g.get("description") or "") for g in group if g.get("description")), "")
        for ch in group:
            for m in per_ch.get(ch["channel_id"], []):
                mid = m.get("id") or m.get("event_id")
                if mid and mid in seen_ids:
                    continue
                seen_ids.add(mid)
                merged.append(m)
        if not merged:
            continue
        merged.sort(key=lambda m: m.get("created_at") or 0)
        label = f"#{group[0]['name']}" + (" _(duplicate channels merged)_" if len(group) > 1 else "")
        lines.append(f"## {label} — {len(merged)} messages" + (f"  _({desc})_" if desc else ""))
        for m in merged:
            pk = m.get("pubkey") or ""
            author = names.get(pk, pk[:12] if pk else "?")
            body = clean(m.get("content") or "")
            if len(body) > 700:
                body = body[:700] + " …[truncated]"
            lines.append(f"- **{fmt_ts(m.get('created_at'))}** `{author}`:")
            for ln in body.split("\n"):
                lines.append(f"  > {ln}")
        lines.append("")
        total += len(merged)
        active += 1
    header = f"**{total} messages · {active} active channels · {len(channels)} total channels.**\n"
    lines.insert(5, header + ("" if total else "_Is window me koi message nahi._"))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
