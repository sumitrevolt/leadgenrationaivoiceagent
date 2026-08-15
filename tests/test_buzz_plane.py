"""Buzz coding-agent plane: file locks + the cost/quota rollup.

Both scripts are operator tools that run on a dirty tree while several harnesses
edit it. The failures they guard against have already happened once each — a
crash on a fresh checkout, and a tool editing a file another tool held.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


buzzlock = _load("buzzlock")
cost = _load("buzz_agent_cost")
admin = _load("buzz_admin_setup")


# --------------------------------------------------------------------------- #
# buzzlock
# --------------------------------------------------------------------------- #
@pytest.fixture
def locks(tmp_path, monkeypatch):
    """Point buzzlock at a throwaway registry and silence the #build post."""
    monkeypatch.setattr(buzzlock, "LOCKS", tmp_path / "LOCKS.json")
    monkeypatch.setattr(buzzlock, "post_build", lambda body: "buzz skipped (test)")
    return tmp_path / "LOCKS.json"


def test_every_declared_tool_can_claim(locks):
    """Smoke only — this iterates TOOLS, so it passes for anything added.

    Real coverage is test_multi_harness_tools_are_registered below, which names
    the tools and therefore fails if one is dropped.
    """
    for tool in buzzlock.TOOLS:
        args = _args(paths=[f"app/{tool.lower()}.py"], tool=tool, reason="smoke")
        assert buzzlock.cmd_claim(args) == 0


def test_multi_harness_tools_are_registered():
    """Named, so dropping a harness fails here instead of silently un-gating it.

    A tool absent from TOOLS can't claim, so it edits the shared tree with no
    lock at all — the exact failure the registry exists to prevent.
    """
    for tool in ("CURSOR", "CLAUDE", "CODEX", "GOOSE", "OPENCODE", "FREEBUFF", "MONKEY"):
        assert tool in buzzlock.TOOLS


def test_status_on_missing_registry_is_clean(locks, capsys):
    """Regression: a fresh worktree has no LOCKS.json (it is gitignored).

    This used to raise FileNotFoundError, so `buzzlock status` was unusable on
    every new checkout and agents skipped the lock protocol entirely.
    """
    assert not locks.exists()
    assert buzzlock.cmd_status(_args()) == 0
    assert "no active claims" in capsys.readouterr().out


def test_corrupt_registry_fails_loudly(locks):
    """Half-written JSON must not be silently treated as an empty registry."""
    locks.write_text('{"locks": [', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        buzzlock.load()
    assert "corrupt" in str(exc.value)


def test_second_tool_is_refused_with_exit_2(locks):
    """Exit 2 is the contract other tools branch on — not just a warning."""
    assert buzzlock.cmd_claim(_args(["app/api/billing.py"], "CLAUDE", "adr")) == 0
    rc = buzzlock.cmd_claim(_args(["app/api/billing.py"], "CODEX", "review"))
    assert rc == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["claim", "a.py", "--tool", "NOT_A_TOOL", "--reason", "x"],  # bad choice
        ["claim", "a.py", "--tool", "CLAUDE"],  # missing --reason
        ["release", "a.py", "--tool", "CLAUDE"],  # missing --evidence
        ["handoff", "--tool", "CURSOR"],  # missing --next/--evidence
        ["not-a-subcommand"],
    ],
)
def test_usage_errors_exit_1_not_2(locks, monkeypatch, argv):
    """Exit 2 must mean REFUSED and nothing else.

    argparse's own default is to exit 2 on usage errors, colliding with the
    refusal code a caller branches on — a typo'd `--tool` would read as "another
    tool holds this file". Found by independent review (canary
    GRID-CANARY-20260809-104317). Usage errors are 1, as the docstring claims.
    """
    monkeypatch.setattr(sys, "argv", ["buzzlock", *argv])
    with pytest.raises(SystemExit) as exc:
        buzzlock.main()
    assert exc.value.code == 1, f"{argv} should be a usage error (1), got {exc.value.code}"


def test_refusal_still_exits_2(locks):
    """The other half of the contract: a genuine conflict is still exactly 2."""
    assert buzzlock.cmd_claim(_args(["app/x.py"], "CLAUDE", "first")) == 0
    assert buzzlock.cmd_claim(_args(["app/x.py"], "CODEX", "second")) == 2


def test_release_frees_the_file_for_another_tool(locks):
    buzzlock.cmd_claim(_args(["app/api/billing.py"], "CLAUDE", "adr"))
    buzzlock.cmd_release(_args(["app/api/billing.py"], "CLAUDE", evidence="exit 0"))
    assert buzzlock.cmd_claim(_args(["app/api/billing.py"], "CODEX", "review")) == 0


def test_handoff_body_requires_evidence_line():
    body = buzzlock.format_handoff(
        "CURSOR", "CLAUDE", "ship gates", "tests", "exit 0", "owner blitz", "scripts/buzzlock.py"
    )
    assert body.startswith("[CURSOR] HANDOFF -> CLAUDE")
    assert "Evidence: exit 0" in body
    assert "Goal: ship gates" in body


def test_handoff_refuses_blank_evidence(locks):
    a = _Args()
    a.tool = "CURSOR"
    a.next_tool = "CLAUDE"
    a.goal = a.done = a.left = a.touched = "x"
    a.evidence = "   "
    assert buzzlock.cmd_handoff(a) == 1


def test_break_refuses_a_fresh_claim(locks):
    buzzlock.cmd_claim(_args(["app/api/billing.py"], "CLAUDE", "adr"))
    args = _args(tool="CODEX")
    args.path = "app/api/billing.py"
    assert buzzlock.cmd_break(args) == 2


class _Args:
    pass


def _args(paths=None, tool=None, reason=None, evidence=None):
    a = _Args()
    a.paths, a.tool, a.reason, a.evidence = paths, tool, reason, evidence
    return a


# --------------------------------------------------------------------------- #
# cost rollup
# --------------------------------------------------------------------------- #
def test_cost_uses_cache_multipliers_not_flat_input_rate():
    """Cache writes cost 1.25x and reads 0.1x — a flat rate misprices agent work.

    Agent transcripts are overwhelmingly cache reads, so treating them as full
    input price inflates the estimate by roughly an order of magnitude.
    """
    usage = {"input": 0, "output": 0, "cache_write": 1_000_000, "cache_read": 1_000_000}
    # Opus 5 input is $5/MTok -> 1M write = $6.25, 1M read = $0.50
    assert cost._cost("claude-opus-5", usage) == pytest.approx(6.75)


def test_unknown_model_is_priced_not_dropped():
    """A new model ID must not silently score as free."""
    usage = {"input": 1_000_000, "output": 0, "cache_write": 0, "cache_read": 0}
    assert cost._cost("claude-model-from-the-future", usage) > 0


def test_claude_scan_dedupes_repeated_uuids(tmp_path, monkeypatch):
    """Resumed transcripts replay assistant messages; counting twice doubles the day."""
    proj = tmp_path / "C--some-project"
    proj.mkdir()
    line = json.dumps(
        {
            "uuid": "same-uuid",
            "timestamp": "2026-08-08T10:00:00.000Z",
            "message": {
                "model": "claude-opus-5",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        }
    )
    (proj / "a.jsonl").write_text(line + "\n" + line + "\n", encoding="utf-8")
    monkeypatch.setattr(cost, "CLAUDE_SESSIONS", tmp_path)

    days = cost.scan_claude("2026-08-01", None)
    assert days["2026-08-08"]["claude-opus-5"]["calls"] == 1
    assert days["2026-08-08"]["claude-opus-5"]["output"] == 50


def test_codex_scan_sums_deltas_and_tracks_peak_quota(tmp_path, monkeypatch):
    """Codex emits a cumulative total AND a per-turn delta — summing totals triples it."""
    sess = tmp_path / "2026" / "08"
    sess.mkdir(parents=True)
    recs = [
        {
            "timestamp": "2026-08-08T10:00:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"input_tokens": 1000, "output_tokens": 100},
                    "last_token_usage": {
                        "input_tokens": 1000,
                        "cached_input_tokens": 400,
                        "output_tokens": 100,
                    },
                },
                "rate_limits": {"primary": {"used_percent": 92.0}},
            },
        },
        {
            "timestamp": "2026-08-08T11:00:00.000Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {"input_tokens": 3000, "output_tokens": 300},
                    "last_token_usage": {
                        "input_tokens": 2000,
                        "cached_input_tokens": 0,
                        "output_tokens": 200,
                    },
                },
                "rate_limits": {"primary": {"used_percent": 3.0}},
            },
        },
    ]
    (sess / "rollout.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(cost, "CODEX_SESSIONS", tmp_path)

    days, quota = cost.scan_codex("2026-08-01")
    day = days["2026-08-08"]
    assert day["output"] == 300  # 100 + 200 deltas, not 100 + 300 totals
    assert day["cache_read"] == 400
    assert day["input"] == 2600  # (1000-400) + 2000 — cached split out
    # A reset drops the latest reading to 3%; the peak is what shows the squeeze.
    assert quota["used_percent"] == 3.0
    assert quota["peak_percent"] == 92.0


def test_project_filter_excludes_other_projects(tmp_path, monkeypatch):
    for name in ("C--leadgen", "C--other"):
        p = tmp_path / name
        p.mkdir()
        (p / "s.jsonl").write_text(
            json.dumps(
                {
                    "uuid": name,
                    "timestamp": "2026-08-08T10:00:00.000Z",
                    "message": {
                        "model": "claude-opus-5",
                        "usage": {"input_tokens": 10, "output_tokens": 1},
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(cost, "CLAUDE_SESSIONS", tmp_path)

    days = cost.scan_claude("2026-08-01", "leadgen")
    assert days["2026-08-08"]["claude-opus-5"]["calls"] == 1


# --------------------------------------------------------------------------- #
# canvas overwrite guard
# --------------------------------------------------------------------------- #
def test_guard_blocks_a_canvas_rewrite_that_drops_a_rule():
    """`canvas set` REPLACES the document, so a non-superset silently deletes rules.

    Both live canvases were hand-written by earlier sessions; a blind write would
    have destroyed them.
    """
    current = "# Dev\nNo commit/push without owner ask.\nSwara/voice FROZEN."
    new = "# Dev\nNo commit/push without owner ask.\nNow with cross-check!"
    dropped = admin._dropped_lines(current, new)
    assert dropped == ["Swara/voice FROZEN."]


def test_guard_allows_a_true_superset():
    current = "# Dev\nSwara/voice FROZEN."
    new = "# Dev\nSwara/voice FROZEN.\n\n## Cross-check\nowner routes it."
    assert admin._dropped_lines(current, new) == []


def test_guard_ignores_pure_whitespace_reflow():
    """Re-indenting a line is not data loss; a missing rule is."""
    current = "  Swara/voice   FROZEN.  "
    new = "Swara/voice FROZEN."
    assert admin._dropped_lines(current, new) == []


def test_guard_is_a_noop_on_an_empty_canvas():
    assert admin._dropped_lines("", "anything") == []
    assert admin._dropped_lines(None, "anything") == []


def test_shipped_canvases_are_supersets_of_what_was_published():
    """The exact live content read from the relay on 2026-08-09.

    If someone edits BUILD_CANVAS/DEV_CANVAS and drops one of these lines, this
    fails here rather than deleting it from the workspace.
    """
    build_had = [
        "**Plane:** developer tooling. NOT runtime STAFF, NOT prod control.",
        "| `[CURSOR]` | Cursor | IDE-side edits, refactors, inline fixes |",
        "Machine-readable mirror: `docs/coordination/LOCKS.json` in the repo.",
        "- Never `git add -A`. Stage explicit paths only.",
        "- Swara / voice path = FROZEN.",
    ]
    assert admin._dropped_lines("\n".join(build_had), admin.BUILD_CANVAS) == []

    dev_had = [
        "# Dev",
        "Checkout: REPOS/leadgenrationaiagent → Documents/leadgenrationaiagent",
        "Context first: docs/context/{CURRENT_STATE,ACTIVE_WORK,SESSION_HANDOFF}.md",
        "No commit/push without owner ask. Swara/voice FROZEN.",
    ]
    assert admin._dropped_lines("\n".join(dev_had), admin.DEV_CANVAS) == []


def test_render_never_claims_money_was_spent(tmp_path, monkeypatch):
    """The free-stack mandate means the USD figure is a counterfactual, not spend.

    If this wording is ever dropped, the report starts reading like a bill.
    """
    monkeypatch.setattr(cost, "CLAUDE_SESSIONS", tmp_path)
    monkeypatch.setattr(cost, "CODEX_SESSIONS", tmp_path)
    body = cost.render(cost.build_report(7, None), 88.0)
    assert "not money spent" in body
    assert "marginal cost" in body
