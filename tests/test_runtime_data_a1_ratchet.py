"""A1 ratchet — the three migrated stores must stay migrated.

The repo-wide debt ratchet only forbids GROWTH: existing findings are tolerated
because 1000+ of them predate the workstream. That is the right rule for the
backlog and the wrong rule for a store that has just been migrated, where the
honest target is zero and it must stay zero.

So this file asserts the stronger property for A1 only: the five writer modules
carry NO uncontrolled in-checkout runtime path, and exactly three manifest rows
moved state.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.platform import runtime_data_allowlist as allowlist
from app.platform import runtime_data_baseline as baseline
from app.platform import runtime_data_manifest as manifest
from tests.runtime_data_waves import A1_STORE_IDS, all_declared_store_ids

REPO = Path(__file__).resolve().parents[1]

#: Their production writer/reader modules.
A1_MODULES = (
    "app/telephony/voice_launch.py",
    "app/platform/platform_dial.py",
    "app/telephony/dial_gate.py",
    "app/telephony/call_feedback.py",
)

#: Counts pinned so a "small cleanup" cannot quietly relax the controls this
#: migration depends on.
#: 0 AFTER host cutover activate + CUTOVER_COMPLETE flip. DUAL_READ alone must
#: never drop this count — only CUTOVER_COMPLETE after verified bytes move.
EXPECTED_BLOCKERS = 0
# 2026-07-30: ops.owner_email_canary adds one narrowly-scoped CREATE entry.
# 2026-07-31: governance.mission_control adds 4 entries (ledger/missions/idem/file).
# 2026-07-31: sales.prospects adds 5 entries (Prospect Score V2 backfill sidecar).
# 27 since 2026-08-02: admin remove-customer added a DELETE against the brand-kit
# store, which was then CLASSIFIED (manifest store marketing.brand_kits + allowlist
# entry with owner and review condition). This guard exists to catch green bought by
# LOOSENING a control -- declaring a newly-added destructive path is the opposite:
# the entry count rises because the reviewed surface grew, and the baseline
# fingerprint count below is deliberately unchanged.
# 2026-08-04: 43 -> 45. #240 added data/offers.jsonl (immutable offer/order store)
# and its atomic temp. The reviewed surface GREW -- both paths are declared with
# owner, migration_tier and review_condition under the existing
# billing.upi_payments family; no baseline debt was tolerated and
# EXPECTED_BASELINE_FINGERPRINTS below is deliberately unchanged.
# 2026-08-05: 45 -> 47 via campaign_offer_policies.jsonl (+temp) under billing.upi_payments.
# 2026-08-05: 47 -> 50. ADR-158/161 memory stack declared platform.memory_governance
# (+3 entries: rules_fn, rules_path_var, audit_fn). CLASSIFIED, not tolerated —
# baseline fingerprint count unchanged.
# 2026-08-06: 50 -> 52. Tenant-aware workforce memory adds two READ bindings
# (_entries_path and tenants_dir) under the existing platform.workforce_memory
# family. CLASSIFIED, not tolerated — baseline fingerprints remain unchanged.
# 2026-08-11: 52 -> 55. ADR-177 GSC rank snapshot declares marketing.gsc_rankings
# (+3 entries: daily, state, state_tmp). CLASSIFIED, not tolerated — baseline
# fingerprint count unchanged.
# 2026-08-12: 55 -> 61. PR #333 staff_bus declares platform.staff_bus
# (+6 entries: root, events, idempotency, idempotency_open, audit, dlq).
# CLASSIFIED, not tolerated — baseline fingerprint count unchanged.
# 2026-08-14: 61 -> 62. Hot Queue owner reminder declares ops.office_briefing
# (+1 entry: _notification_path READ/DELETE claim). CLASSIFIED, not tolerated —
# baseline fingerprint count unchanged.
# 2026-08-16: 62 -> 70. Marketing factory JSONL (appointment/health/drips/forms/
# proposals/review) classified as TIER_3 REBUILDABLE_CACHE (+8 allowlist rows).
# CLASSIFIED, not tolerated — baseline fingerprint count unchanged.
EXPECTED_ALLOWLIST_ENTRIES = 70
EXPECTED_BASELINE_FINGERPRINTS = 839


def _uncontrolled_path_findings(module_path: str) -> list[tuple[int, str]]:
    """In-checkout runtime paths that the code would actually open.

    Deliberately AST-based. These modules NAME their stores in prose — a line
    scan flagged the docstrings that explain the very rule being enforced, which
    is a false positive with the same shape as the bug it was hunting.

    Not counted:
      * docstrings — prose, never a path the code opens;
      * the declared `legacy_path=` argument — that IS the controlled reference,
        and the authority needs it to keep pre-cutover behaviour identical.

    Counted:
      * any string literal that names a checkout-relative `data/...` path;
      * `os.path.join("data", ...)` / `Path("data", ...)`, where no single
        literal contains a separator and a substring scan would see nothing.

    A data-rooted join is reported by its RECONSTRUCTED path (`data/x.jsonl`)
    whenever every segment is a literal, including segments contributed by
    `Path("data") / "x"`. It degrades to the bare kind `join-with-data-root`
    only when a segment is computed. The reconstruction matters: an exclusion
    list can only name what the detector names, and a finding reported as an
    anonymous kind forces a caller to exclude every join in the module at once
    — which is the hole this test exists to close.
    """
    tree = ast.parse((REPO / module_path).read_text(encoding="utf-8"))

    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node

    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                exempt.add(id(body[0].value))
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "legacy_path":
                    for sub in ast.walk(kw.value):
                        if isinstance(sub, ast.Constant):
                            exempt.add(id(sub))

    def _render_join(call: ast.Call) -> str:
        """`data/...` rebuilt from literal segments, or the bare kind."""
        segments: list[str] = []
        for arg in call.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                segments.append(arg.value.replace("\\", "/").strip("/"))
            else:
                return "join-with-data-root"
        # Absorb `Path("data") / "sub" / "file"` — the divisions are the
        # remaining segments and they sit ABOVE the call in the tree.
        node: ast.AST = call
        while True:
            parent = parents.get(id(node))
            if (
                isinstance(parent, ast.BinOp)
                and isinstance(parent.op, ast.Div)
                and parent.left is node
            ):
                right = parent.right
                if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
                    return "join-with-data-root"
                segments.append(right.value.replace("\\", "/").strip("/"))
                node = parent
                continue
            break
        return "/".join(s for s in segments if s)

    findings: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # `os.path.join("data", "x.json")` / `Path("data", "x.json")`
        if isinstance(node, ast.Call):
            first = node.args[0] if node.args else None
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and first.value.strip("/\\") == "data"
                and id(first) not in exempt
            ):
                findings.append((getattr(node, "lineno", -1), _render_join(node)))
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in exempt
        ):
            value = node.value.replace("\\", "/")
            if value.startswith("data/") or "/data/" in value:
                findings.append((getattr(node, "lineno", -1), node.value))

    return findings


#: Paths that live in an A1 module but belong to a store A1 did NOT migrate.
#: Each entry names the owning store and why it is not in this wave. This is an
#: exclusion list, not an amnesty: the assertion below requires the observed set
#: to equal it exactly, so a NEW literal cannot hide behind an old one, and a
#: path that later gets migrated must be delisted or the test fails.
OUT_OF_SCOPE: dict[str, dict[str, str]] = {
    "app/telephony/call_feedback.py": {
        "data/dial_blocklist_audit.jsonl": (
            "DIAL_BLOCKLIST_AUDIT. The manifest deliberately keeps this audit "
            "ledger OUT of telephony.dial_suppression until it has its own "
            "reader/writer evidence — folding it in here would migrate a store "
            "nobody has classified."
        ),
    },
    "app/telephony/voice_launch.py": {},
}


@pytest.mark.parametrize("module_path", A1_MODULES)
def test_a1_writer_modules_have_zero_uncontrolled_runtime_paths(module_path):
    """Zero for the A1 stores — and every survivor named, with its owner.

    'Zero findings in these files' would have been a nicer sentence and a false
    one: two A1 modules also host stores from later waves. Claiming those away
    silently is precisely the overclaim this workstream keeps catching.
    """
    declared = OUT_OF_SCOPE.get(module_path, {})
    observed = {value for _, value in _uncontrolled_path_findings(module_path)}

    undeclared = sorted(observed - set(declared))
    assert not undeclared, f"{module_path} still opens an unclassified checkout path: {undeclared}"

    stale = sorted(set(declared) - observed)
    assert not stale, (
        f"{module_path}: {stale} no longer appears — delete the exclusion rather "
        "than leaving a hole the next literal can hide in"
    )


def test_the_ratchet_would_actually_catch_a_regression(tmp_path):
    """Anti-vacuity: a scanner that finds nothing anywhere proves nothing.

    An earlier canary in this repo passed only because execution stopped at step
    one, so a detector is not trusted here until it is shown failing on purpose.
    """
    sample = tmp_path / "regression.py"
    sample.write_text(
        '"""A docstring naming data/dial_blocklist.json must NOT count."""\n'
        "import os\n"
        "from pathlib import Path\n"
        "A = Path('data/dial_blocklist.json')\n"
        "B = os.path.join('data', 'platform_dial.json')\n"
        "C = Path('data') / 'recordings'\n"
        "D = os.path.join('data', compute_name())\n",
        encoding="utf-8",
    )
    # The scanner joins against REPO; an absolute path makes that a no-op, so
    # the sample can live in tmp_path and still exercise the real implementation.
    findings = _uncontrolled_path_findings(str(sample))
    values = {value for _, value in findings}
    assert len(findings) == 4, findings
    assert "data/dial_blocklist.json" in values, "the plain literal slipped through"
    assert (
        "data/platform_dial.json" in values
    ), "the os.path.join('data', ...) shape slipped through"
    assert "data/recordings" in values, "the Path('data') / 'sub' shape slipped through"
    assert "join-with-data-root" in values, (
        "a join with a COMPUTED segment must still be reported — degrading to the "
        "bare kind is what keeps an unnameable path from being silently dropped"
    )


# ------------------------------------------------------------------ manifest
def test_the_three_a1_rows_are_cutover_complete():
    """A1's own rows, asserted by A1's own file.

    This was `moved == A1_STORE_IDS` while A1 was the newest wave. It is a
    subset assertion now that later waves have landed — NOT a relaxation: the
    exact global set is asserted once in ``test_runtime_data_waves.py`` as the
    union of every wave declared in ``runtime_data_waves.py``.
    """
    moved = {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert set(A1_STORE_IDS) <= moved, set(A1_STORE_IDS) - moved


def test_no_unmigrated_tier0_row_was_touched():
    """Every Tier-0 store outside a landed wave must still be LEGACY_IN_CHECKOUT.

    Landed = union of every wave in the registry. A state that runs ahead of
    the code is exactly the false claim this manifest exists to prevent.
    """
    landed = set(all_declared_store_ids())
    still_legacy = {
        s["store_id"]
        for s in manifest.STORES
        if s.get("migration_tier") == manifest.TIER_0 and s["store_id"] not in landed
    }
    for store_id in still_legacy:
        row = next(s for s in manifest.STORES if s["store_id"] == store_id)
        assert row["migration_state"] == manifest.LEGACY_IN_CHECKOUT, store_id


def test_manifest_still_validates():
    assert manifest.validate() == []


def test_cutover_complete_clears_deployment_blockers():
    """After host copy/verify/activate, A1 stores are CUTOVER_COMPLETE and non-blocking.

    DUAL_READ_PRE_CUTOVER remains a blocking state for any future wave that has
    not yet finished host cutover — the empty blocker list is the honest answer
    only when every previously dual-read store has reached CUTOVER_COMPLETE.
    """
    blocking = manifest.blocking_stores()
    assert len(blocking) == EXPECTED_BLOCKERS, sorted(s["store_id"] for s in blocking)
    assert A1_STORE_IDS <= {s["store_id"] for s in manifest.by_state(manifest.CUTOVER_COMPLETE)}
    assert manifest.DUAL_READ_PRE_CUTOVER in manifest.BLOCKING_STATES
    assert manifest.CUTOVER_COMPLETE not in manifest.BLOCKING_STATES


def test_no_allowlist_or_baseline_relaxation():
    """The migration must not buy its green by loosening a neighbouring control."""
    assert len(allowlist.load()) == EXPECTED_ALLOWLIST_ENTRIES
    assert len(baseline.ENTRIES) == EXPECTED_BASELINE_FINGERPRINTS


def test_deployment_still_denied_with_the_root_unset(monkeypatch):
    """Three migrated stores do not authorise a deploy — nothing has moved yet."""
    import importlib.util

    monkeypatch.delenv("LEADGEN_RUNTIME_DATA_DIR", raising=False)
    monkeypatch.delenv("LEADGEN_RUNTIME_DATA_HOST_DIR", raising=False)
    monkeypatch.delenv("RUNTIME_DATA_CUTOVER_ENABLED", raising=False)
    monkeypatch.setenv("APP_ENV", "production")

    spec = importlib.util.spec_from_file_location(
        "_pf", REPO / "scripts" / "runtime_data_preflight.py"
    )
    pf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pf)

    reasons = pf.deploy_denied(pf.gather())
    assert reasons, "a deploy must not be permitted before the cutover"
    assert any(r.startswith("MODE_") for r in reasons)
    assert "CUTOVER_GATE_DISABLED" in reasons
