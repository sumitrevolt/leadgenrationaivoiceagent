#!/usr/bin/env python3
"""
Telegram Coordination-Group Wiring Tool
=======================================
The ONLY code path that writes ``config/telegram/setup_spec.yaml`` — the single
source of truth for every Telegram surface (13 groups: 4 marketing + 4 voice +
5 cross-product).

Why a tool and not manual edits: the spec is read by the runner, the verify
script and the owner dashboard, so a silent reshape of the document (or a
half-applied binding) corrupts every consumer at once. Guards enforced here:

1. every write keeps a timestamped ``setup_spec.yaml.bak-*``;
2. the rendered YAML is re-parsed and compared BEFORE the write — a document
   that does not round-trip identically is refused, never partially applied;
3. ``--set`` refuses to silently replace an existing ``chat_id`` (use ``--force``);
4. ambiguous keys are rejected with the candidate list instead of guessed
   (both products define ``announcements``, so a bare key is never resolved).

Usage::

    python scripts/telegram_wire_coordination_groups.py --list
    python scripts/telegram_wire_coordination_groups.py --set workers_coordination=-1001234567890
    python scripts/telegram_wire_coordination_groups.py --set owner_alerts=-100... --force
    python scripts/telegram_wire_coordination_groups.py --create-topics workers_coordination
    python scripts/telegram_wire_coordination_groups.py --verify
    python scripts/telegram_wire_coordination_groups.py --verify --deep
    python scripts/telegram_wire_coordination_groups.py --discover   # READ-ONLY, needs a free token

Exit codes: ``0`` ok · ``1`` problem/refused · ``2`` usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "config" / "telegram" / "setup_spec.yaml"

#: Groups the owner explicitly asked for as first-class coordination surfaces.
COORDINATION_KEYS: tuple[str, ...] = (
    "workers_coordination",
    "agents_coordination",
    "admin_command_center",
)
REQUIRED_COORDINATION_KEYS = COORDINATION_KEYS

#: (slot label, env var name) — labels are loggable, token values never are.
_TOKEN_SLOTS: tuple[tuple[str, str], ...] = (
    ("jarvis", "TELEGRAM_JARVIS_BOT_TOKEN"),
    ("notify", "TELEGRAM_NOTIFY_BOT_TOKEN"),
    ("fallback", "TELEGRAM_BOT_TOKEN"),
)

_API_TIMEOUT = 12.0


# ---------------------------------------------------------------------------
# Credentials (names only — values are never printed)
# ---------------------------------------------------------------------------

def _read_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _tokens() -> dict[str, str]:
    """``{slot: token}`` for slots that are actually configured (never logged)."""
    dotenv = _read_dotenv(ROOT / ".env")
    tokens: dict[str, str] = {}
    for label, env_name in _TOKEN_SLOTS:
        value = (os.environ.get(env_name) or dotenv.get(env_name) or "").strip()
        if len(value) >= 20:
            tokens[label] = value
    return tokens


def _telegram_api(token: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(params or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_API_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error_code": exc.code, "description": str(exc.reason)}
    except Exception as exc:
        return {"ok": False, "description": f"{type(exc).__name__}: {exc}"}


def _get_me(token: str) -> dict[str, Any]:
    """``getMe`` → ``{"ok": bool, "username": str, "id": int, ...}``. Never raises."""
    res = _telegram_api(token, "getMe")
    result = res.get("result") or {}
    if res.get("ok"):
        return {"ok": True, "username": result.get("username"), "id": result.get("id")}
    return {"ok": False, "error_code": res.get("error_code"), "description": res.get("description")}


def _get_chat(token: str, chat_id: str) -> dict[str, Any]:
    res = _telegram_api(token, "getChat", {"chat_id": str(chat_id)})
    if res.get("ok"):
        result = res.get("result") or {}
        return {"ok": True, "title": result.get("title"), "is_forum": result.get("is_forum")}
    return {"ok": False, "description": res.get("description")}


# ---------------------------------------------------------------------------
# Spec load / resolve / save
# ---------------------------------------------------------------------------

def load_spec(path: str | Path | None = None) -> dict[str, Any]:
    """Parse the SSOT spec. Reads the module-level ``SPEC_PATH`` at call time."""
    target = Path(path) if path else Path(SPEC_PATH)
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def render_spec(spec: dict[str, Any]) -> str:
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=4096, default_flow_style=False)


def save_spec(
    spec: dict[str, Any],
    backup: bool = True,
    path: str | Path | None = None,
) -> None:
    """Write the SSOT spec atomically, refusing any non-lossless reshape.

    The rendered text is re-parsed and compared with the intended document
    BEFORE the file is touched, so a YAML marshalling surprise (key
    re-ordering that changes types, an unquoted ``-100…`` becoming an int)
    fails loudly instead of corrupting the source of truth.
    """
    target = Path(path) if path else Path(SPEC_PATH)
    rendered = render_spec(spec)
    reparsed = yaml.safe_load(rendered)
    if reparsed != spec:
        raise ValueError(
            "refusing to write setup_spec.yaml: rendered YAML does not round-trip identically "
            "(the document would be silently reshaped)"
        )

    if backup and target.exists():
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        target.with_name(f"{target.name}.bak-{stamp}").write_text(
            target.read_text(encoding="utf-8"), encoding="utf-8"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp")
    tmp.write_text(rendered, encoding="utf-8")
    os.replace(tmp, target)


def group_refs(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """``{ref: group}`` for every group, ``ref`` is scope-qualified where needed.

    Product groups are addressed ``<product_id>.<key>`` (both products define
    ``announcements``/``community``/``support``/``feedback``); cross-product
    groups keep their bare key because it is already unique. The returned dicts
    are the live spec objects, so a mutation persists through ``save_spec``.
    """
    refs: dict[str, dict[str, Any]] = {}
    for product in spec.get("products") or []:
        product_id = str(product.get("id") or "").strip()
        for group in product.get("groups") or []:
            key = str(group.get("key") or "").strip()
            if not product_id or not key:
                continue
            refs[f"{product_id}.{key}"] = group
    for group in spec.get("cross_product") or []:
        key = str(group.get("key") or "").strip()
        if key:
            refs[key] = group
    return refs


def resolve_group(spec: dict[str, Any], key: str) -> tuple[dict[str, Any] | None, str]:
    """Resolve ``key`` → ``(group, "")`` or ``(None, error_message)``.

    Ambiguity is reported, never guessed: a bare ``announcements`` matches two
    products and must be disambiguated by the caller.
    """
    raw = (key or "").strip()
    if not raw:
        return None, "empty key"

    refs = group_refs(spec)

    if "." in raw:
        group = refs.get(raw)
        if group is None:
            return None, f"unknown key '{raw}' (candidates: {', '.join(sorted(refs))})"
        return group, ""

    bare_matches = [
        ref
        for ref in refs
        if "." in ref and ref.rsplit(".", 1)[1] == raw
    ]
    direct = refs.get(raw)

    if len(bare_matches) > 1:
        return None, (
            f"ambiguous key '{raw}' matches {len(bare_matches)} groups: "
            + ", ".join(sorted(bare_matches))
            + " — use the scope-qualified key"
        )
    if len(bare_matches) == 1:
        return refs[bare_matches[0]], ""
    if direct is not None:
        return direct, ""
    return None, f"unknown key '{raw}' (candidates: {', '.join(sorted(refs))})"


def find_group(spec: dict[str, Any], key: str) -> dict[str, Any] | None:
    group, error = resolve_group(spec, key)
    return None if error else group


def bind_chat_id(key: str, chat_id: str | int, force: bool = False) -> int:
    """Bind ``chat_id`` to ``key``. Returns 0 on success, 1 when refused."""
    spec = load_spec()
    group, error = resolve_group(spec, key)
    if error or group is None:
        print(f"[ERROR] {error}")
        return 1

    value = str(chat_id).strip()
    if not value:
        print("[ERROR] empty chat_id")
        return 1
    if not value.lstrip("-").isdigit():
        print(f"[ERROR] chat_id '{value}' is not numeric (expected e.g. -1001234567890)")
        return 1

    existing = str(group.get("chat_id") or "").strip()
    if existing and existing == value:
        print(f"[SKIP] {key} already bound to {value}")
        return 0
    if existing and not force:
        print(
            f"[REFUSED] {key} is already bound to {existing}; refusing to replace silently. "
            "Re-run with --force if the group really moved."
        )
        return 1

    group["chat_id"] = value
    if existing:
        print(f"[WARN] replacing {key}: {existing} -> {value} (forced)")
    save_spec(spec, backup=True)

    # Re-read from disk: the write must be the thing we just decided on.
    if str(find_group(load_spec(), key).get("chat_id") or "") != value:  # type: ignore[union-attr]
        print(f"[ERROR] write verification failed for {key}")
        return 1
    print(f"[OK] {key} -> {value}  (backup written)")
    return 0


# ---------------------------------------------------------------------------
# Topic creation + verification
# ---------------------------------------------------------------------------

def _default_token() -> str | None:
    return _tokens().get("jarvis")


def create_topics(key: str, token: str | None = None) -> int:
    """Create the forum topics declared for ``key`` (idempotent). 0 ok / 1 refused."""
    spec = load_spec()
    group, error = resolve_group(spec, key)
    if error or group is None:
        print(f"[ERROR] {error}")
        return 1

    chat_id = str(group.get("chat_id") or "").strip()
    if not chat_id:
        print(f"[REFUSED] {key} has no chat_id yet — bind it first with --set {key}=<chat_id>")
        return 1

    declared = [str(t) for t in (group.get("forum_topics") or [])]
    if not declared:
        print(f"[SKIP] {key} declares no forum topics")
        return 0

    resolved = token or _default_token()
    if not resolved:
        print("[ERROR] no telegram token available (set TELEGRAM_JARVIS_BOT_TOKEN)")
        return 1

    topic_ids: dict[str, Any] = dict(group.get("topic_ids") or {})
    created: list[str] = []
    for topic in declared:
        if topic in topic_ids:
            continue
        res = _telegram_api(resolved, "createForumTopic", {"chat_id": chat_id, "name": topic})
        if res.get("ok"):
            topic_ids[topic] = (res.get("result") or {}).get("message_thread_id")
            created.append(topic)
        else:
            print(f"[ERROR] createForumTopic '{topic}' failed: {res.get('description')}")

    if created:
        group["topic_ids"] = topic_ids
        save_spec(spec, backup=True)
        print(f"[OK] {key}: created {len(created)} topic(s) -> {', '.join(created)}")
    else:
        print(f"[OK] {key}: all {len(declared)} declared topics already exist")
    return 0


def verify(deep: bool = False) -> int:
    """Check the SSOT against live Telegram. Returns 0 ok / 1 problems.

    ``deep=False`` is the cheap gate (tokens valid + the three required
    coordination groups bound). ``deep=True`` also probes every bound group with
    ``getChat`` — that is the only mode that can prove the bot is actually a
    member of a group.
    """
    spec = load_spec()
    critical: list[str] = []
    warnings: list[str] = []

    tokens = _tokens()
    if not tokens:
        critical.append("no telegram token configured (TELEGRAM_JARVIS_BOT_TOKEN)")
        jarvis_ok = False
    else:
        label = "jarvis" if "jarvis" in tokens else sorted(tokens)[0]
        me = _get_me(tokens[label])
        jarvis_ok = bool(me.get("ok"))
        if jarvis_ok:
            print(f"[OK]   token slot '{label}' authenticated as @{me.get('username')}")
        else:
            critical.append(f"token slot '{label}' invalid ({me.get('description')})")

    refs = group_refs(spec)
    bound = sum(1 for g in refs.values() if str(g.get("chat_id") or "").strip())
    print(f"[INFO] groups: {bound}/{len(refs)} bound in setup_spec.yaml")
    print("[INFO] ingress ownership is irrelevant here; this tool never calls getUpdates "
          "(only --discover does, and only read-only)")

    for key in COORDINATION_KEYS:
        group = find_group(spec, key)
        if group is None:
            critical.append(f"required coordination group '{key}' missing from the spec")
        elif not str(group.get("chat_id") or "").strip():
            critical.append(f"required coordination group '{key}' has no chat_id (unwired)")

    if deep and jarvis_ok:
        token = tokens.get("jarvis") or sorted(tokens)[0]
        for ref, group in refs.items():
            chat_id = str(group.get("chat_id") or "").strip()
            if not chat_id:
                warnings.append(f"'{ref}' not bound yet")
                continue
            probe = _get_chat(token, chat_id)
            if probe.get("ok"):
                flag = " (forum)" if probe.get("is_forum") else ""
                print(f"[OK]   {ref:<28} {probe.get('title')}{flag}")
            else:
                warnings.append(f"'{ref}' unreachable for this bot: {probe.get('description')}")

    print("-" * 72)
    for item in critical:
        print(f"CRITICAL: {item}")
    for item in warnings:
        print(f"WARN    : {item}")
    if critical:
        print(f"VERDICT: CRITICAL ({len(critical)} blocking, {len(warnings)} warnings)")
        return 1
    print(f"VERDICT: OK ({len(warnings)} warnings)")
    return 0


def discover() -> int:
    """Print chat ids seen in recent updates — READ-ONLY, never advances offset.

    Telegram only confirms (deletes) updates when ``getUpdates`` is called with
    an ``offset``. This call deliberately omits it, so it cannot eat an owner
    command that the real ingress owner still needs. A 409 means another
    consumer currently holds the token: stop it first (see the runbook).
    """
    token = _default_token()
    if not token:
        print("[ERROR] no telegram token available")
        return 1

    res = _telegram_api(token, "getUpdates", {"timeout": 0, "allowed_updates": ["message"]})
    if not res.get("ok"):
        code = res.get("error_code")
        if code == 409:
            print(
                "[BUSY] HTTP 409 — another getUpdates consumer holds this token "
                "(Hermes gateway or another runner). Non-consuming discovery needs a free token."
            )
        else:
            print(f"[ERROR] getUpdates failed: {res.get('description')}")
        return 1

    seen: dict[str, dict[str, Any]] = {}
    for update in res.get("result") or []:
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        seen[str(chat_id)] = {
            "title": chat.get("title") or chat.get("username") or chat.get("first_name"),
            "type": chat.get("type"),
        }
    if not seen:
        print("[INFO] no pending updates. Post a message in each new group, then re-run.")
        return 1
    print(f"[INFO] {len(seen)} chat(s) visible in recent updates (offset NOT advanced):")
    for chat_id, info in seen.items():
        print(f"  {chat_id:<20} {info.get('type'):<12} {info.get('title')}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_refs() -> int:
    spec = load_spec()
    refs = group_refs(spec)
    print(f"{'REF':<28} {'CHAT_ID':<20} NAME")
    print("-" * 96)
    for ref, group in refs.items():
        chat_id = str(group.get("chat_id") or "").strip() or "(unbound)"
        required = "  [REQUIRED]" if ref in COORDINATION_KEYS else ""
        print(f"{ref:<28} {chat_id:<20} {group.get('name')}{required}")
    print("-" * 96)
    print(f"{len(refs)} groups · {sum(1 for g in refs.values() if str(g.get('chat_id') or '').strip())} bound")
    print("Use scope-qualified refs for product groups (e.g. marketing.announcements).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Wire Telegram coordination groups into config/telegram/setup_spec.yaml (SSOT)"
    )
    parser.add_argument("--list", action="store_true", help="Print every group ref and its binding")
    parser.add_argument("--set", metavar="KEY=CHAT_ID", help="Bind CHAT_ID to KEY (scope-qualified for product groups)")
    parser.add_argument("--force", action="store_true", help="Allow replacing an existing chat_id")
    parser.add_argument("--create-topics", metavar="KEY", help="Create the declared forum topics for KEY")
    parser.add_argument("--verify", action="store_true", help="Verify the SSOT against live Telegram")
    parser.add_argument("--deep", action="store_true", help="With --verify: also getChat-probe every bound group")
    parser.add_argument("--discover", action="store_true", help="Print chat ids from recent updates (read-only)")
    args = parser.parse_args(argv)

    if args.set:
        if "=" not in args.set:
            print("[ERROR] --set expects KEY=CHAT_ID")
            return 2
        key, _, chat_id = args.set.partition("=")
        return bind_chat_id(key.strip(), chat_id.strip(), force=args.force)
    if args.create_topics:
        return create_topics(args.create_topics.strip())
    if args.verify:
        return verify(deep=args.deep)
    if args.discover:
        return discover()
    return _print_refs()


if __name__ == "__main__":
    sys.exit(main())
