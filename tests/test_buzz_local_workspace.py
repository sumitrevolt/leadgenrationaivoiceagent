from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "buzz_local_workspace", REPO / "scripts" / "buzz_local_workspace.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["buzz_local_workspace"] = mod
    spec.loader.exec_module(mod)
    return mod


def agent(pubkey: str, name: str, relay: str = "", active: bool = True) -> dict:
    return {
        "pubkey": pubkey,
        "name": name,
        "relay_url": relay,
        "is_active": active,
    }


def test_selects_only_source_backed_identities_despite_name_duplicates():
    mod = load_module()
    known = mod.CANONICAL_AGENT_PUBKEYS
    rows = [agent("0" * 64, "Honey", "ws://127.0.0.1:3100")]
    rows += [agent(pubkey, name, "wss://hosted") for name, pubkey in known.items()]
    rows += [agent("f" * 64, "Comb", "ws://127.0.0.1:3100")]

    selected = mod.select_canonical_agents(rows)

    assert set(selected) == set(known)
    assert {name: row["pubkey"] for name, row in selected.items()} == known


def test_canonical_pubkey_repairs_mutable_display_name_drift():
    mod = load_module()
    bumble = mod.CANONICAL_AGENT_PUBKEYS["Bumble"]

    selected = mod.select_canonical_agents([agent(bumble, "Pollen")])

    assert selected == {"Bumble": {"pubkey": bumble, "relay_url": ""}}


def test_prefers_local_record_only_when_public_key_is_canonical():
    mod = load_module()
    boss = mod.CANONICAL_AGENT_PUBKEYS["Boss"]
    selected = mod.select_canonical_agents(
        [agent(boss, "Boss", "wss://hosted"), agent(boss, "Alias", "ws://localhost:3000")]
    )

    assert selected["Boss"]["relay_url"] == "ws://localhost:3000"


def test_inactive_or_missing_canonical_identity_is_omitted():
    mod = load_module()
    fizz = mod.CANONICAL_AGENT_PUBKEYS["Fizz"]

    assert mod.select_canonical_agents([agent(fizz, "Fizz", active=False)]) == {}
