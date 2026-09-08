"""Semantic deployment-path manifest — one row per logical entry point.

NOT one row per command occurrence. The raw scanner finds 85 mutation-pattern
occurrences across 38 files; that is candidate discovery, not classification.
Three files it flagged production-capable turned out to be a CI workflow, a
throwaway-container restore drill, and an `echo` of operator instructions.

The load-bearing distinction here is:

    requires_runtime_data_guard = production_capable AND runtime_data_mutation_capable

A production-scoped script that writes `.env` is sensitive, but it cannot revert
the checkout or replace containers — counting it as an unguarded deployment path
would inflate the denominator and hide the real gap.

Every `evidence` field cites what was READ, not what was pattern-matched.
This module is DATA and performs no I/O.
"""

from __future__ import annotations

from typing import Any

MANIFEST_VERSION = "2026-07-26.1"

# --- operation classes -------------------------------------------------------
NORMAL_RELEASE = "NORMAL_RELEASE"
RECOVERY_SELF_HEAL = "RECOVERY_SELF_HEAL"
DATABASE_RESTORE = "DATABASE_RESTORE"
BOOTSTRAP_PROVISIONING = "BOOTSTRAP_PROVISIONING"
# nosecret — a classification label whose value equals its own name, not a credential.
# `# pragma: allowlist secret` covers GitGuardian; scripts/check_secrets.py wants `nosecret`.
SECRET_CONFIG_PREPARATION = "SECRET_CONFIG_PREPARATION"  # pragma: allowlist secret  nosecret
MAINTENANCE = "MAINTENANCE"
TEST_CI = "TEST_CI"
UNKNOWN_CLASS = "UNKNOWN"

# --- environment scope -------------------------------------------------------
PRODUCTION = "PRODUCTION"
TEST_ONLY = "TEST_ONLY"
LOCAL_DEVELOPMENT = "LOCAL_DEVELOPMENT"
UNKNOWN_SCOPE = "UNKNOWN"

# --- status ------------------------------------------------------------------
GUARDED_DIRECTLY = "GUARDED_DIRECTLY"
GUARDED_BY_CANONICAL_PARENT = "GUARDED_BY_CANONICAL_PARENT"
PRODUCTION_NON_RUNTIME_MUTATION = "PRODUCTION_NON_RUNTIME_MUTATION"
NON_PRODUCTION = "NON_PRODUCTION"
DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
UNGUARDED_PRODUCTION_PATH = "UNGUARDED_PRODUCTION_PATH"
UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"

VALID_STATUSES = frozenset(
    {
        GUARDED_DIRECTLY,
        GUARDED_BY_CANONICAL_PARENT,
        PRODUCTION_NON_RUNTIME_MUTATION,
        NON_PRODUCTION,
        DIAGNOSTIC_ONLY,
        UNGUARDED_PRODUCTION_PATH,
        UNKNOWN_REQUIRES_REVIEW,
    }
)

CANONICAL_RELEASE_PARENT = "scripts/deploy_vps.sh"


def _e(**kw: Any) -> dict[str, Any]:
    kw.setdefault("language", "shell")
    kw.setdefault("direct_or_wrapper", "direct")
    kw.setdefault("canonical_parent", None)
    kw.setdefault("guard_location", None)
    kw.setdefault("fallback_after_denial", False)
    # Detached delegation (`setsid nohup ... &`) still inherits the parent's
    # guard — the guard runs before any mutation either way — but the caller
    # cannot observe whether the release actually completed. That is an
    # OPERATIONAL weakness, not a containment one, so it gets its own fields
    # rather than being folded into `guarded`.
    kw.setdefault("detached_execution", False)
    kw.setdefault("operational_completion_observable", True)
    # True where a wrapper legitimately mutates AFTER a successful guarded
    # release (migrations, feature-enable). Containment then rests on ordering,
    # not on the wrapper being read-only — so it is stated rather than implied.
    kw.setdefault("post_parent_mutation", False)
    kw.setdefault("post_parent_operations", [])
    kw.setdefault("post_parent_failure_propagated", True)
    kw.setdefault("post_parent_rollback_available", True)
    # Risks that are real but are NOT runtime-data containment gaps. Kept in a
    # separate field so they can never inflate or deflate the guard count.
    kw.setdefault("operational_risks", [])
    return kw


ENTRYPOINTS: list[dict[str, Any]] = [
    # ================================================= GUARDED (evidence-backed)
    _e(
        deployment_id="release.canonical",
        file="scripts/deploy_vps.sh",
        entrypoint="bash scripts/deploy_vps.sh [sha]",
        operation_class=NORMAL_RELEASE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        operations=["git pull --ff-only", "compose build", "compose up -d"],
        first_mutating_operation="git pull --ff-only",
        guard_strategy="DIRECT_PREFLIGHT",
        guarded=True,
        guard_location="after `cd $REPO`, before sha resolution / git pull",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        status=GUARDED_DIRECTLY,
        evidence="canonical release authority; rolls all 5 app-image services",
    ),
    _e(
        deployment_id="release.mcp_remote",
        file="scripts/_mcp_deploy_remote.sh",
        entrypoint="bash scripts/_mcp_deploy_remote.sh",
        operation_class=NORMAL_RELEASE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        operations=["git fetch", "git reset --hard", "compose up -d"],
        first_mutating_operation="git reset --hard origin/main",
        guard_strategy="DIRECT_PREFLIGHT",
        guarded=True,
        guard_location="line 8, before git fetch/reset",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        status=GUARDED_DIRECTLY,
        evidence="independent reset --hard chain; cannot delegate without changing MCP flow",
    ),
    _e(
        deployment_id="release.pitch",
        file="scripts/vps_pitch_deploy.sh",
        entrypoint="bash scripts/vps_pitch_deploy.sh",
        operation_class=NORMAL_RELEASE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        operations=["git reset --hard", "compose build", "compose up -d"],
        first_mutating_operation="git reset --hard origin/main",
        guard_strategy="DIRECT_PREFLIGHT",
        guarded=True,
        guard_location="line 5, before git fetch/reset",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        status=GUARDED_DIRECTLY,
        evidence="app-only rollout variant; delegation candidate for a later wave",
    ),
    _e(
        deployment_id="release.force_pull",
        file="scripts/vps_force_pull.py",
        entrypoint="python scripts/vps_force_pull.py",
        language="python",
        operation_class=NORMAL_RELEASE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        operations=["git stash", "git clean (scoped)", "git pull", "compose up -d"],
        first_mutating_operation="git stash",
        guard_strategy="DIRECT_PREFLIGHT",
        guarded=True,
        guard_location="main() calls preflight_ok() before building the chain",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        status=GUARDED_DIRECTLY,
        evidence="behaviourally proven in tests/test_force_pull_guard.py: a denied "
        "preflight makes subprocess.run a spy that fails the test if reached",
    ),
    # ============================================ PARENT-GUARDED (proven delegation)
    _e(
        deployment_id="recovery.ship_recover",
        file="scripts/_ship_vps_recover.sh",
        entrypoint="bash scripts/_ship_vps_recover.sh",
        operation_class=RECOVERY_SELF_HEAL,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        direct_or_wrapper="wrapper",
        canonical_parent=CANONICAL_RELEASE_PARENT,
        operations=["delegates redeploy"],
        first_mutating_operation="scripts/deploy_vps.sh (delegated)",
        guard_strategy="CANONICAL_PARENT",
        guarded=True,
        guard_location="inherits deploy_vps.sh guard",
        guard_precedes_mutation=True,
        exit_code_propagated=False,
        detached_execution=True,
        operational_completion_observable=False,
        operational_risks=["RECOVERY_RESULT_PROPAGATION_DEGRADED"],
        status=GUARDED_BY_CANONICAL_PARENT,
        evidence='line 31 runs `setsid nohup bash scripts/deploy_vps.sh "$VER"`. '
        "Lines 5-6 before it are `cd` and `git rev-parse` — read-only. No "
        "independent mutation chain, so the parent's guard covers it. NOTE: the "
        "delegation is detached (setsid nohup &), so the parent's exit status is "
        "NOT propagated to this wrapper — tracked as a separate weakness.",
    ),
    # ================================= UNGUARDED, GENUINELY REQUIRES GUARD
    _e(
        deployment_id="release.flywheel",
        file="scripts/vps_flywheel_deploy.sh",
        entrypoint="bash scripts/vps_flywheel_deploy.sh",
        operation_class=NORMAL_RELEASE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        direct_or_wrapper="wrapper",
        canonical_parent=CANONICAL_RELEASE_PARENT,
        operations=["delegates release", "alembic upgrade", ".env enable", "restart app"],
        first_mutating_operation="scripts/deploy_vps.sh (delegated)",
        guard_strategy="CANONICAL_PARENT",
        guarded=True,
        guard_location="inherits deploy_vps.sh guard",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        post_parent_mutation=True,
        post_parent_operations=["alembic upgrade head", ".env mutation", "restart app"],
        # `alembic upgrade head || true` swallows a migration failure, and a
        # partially-applied migration has no automatic rollback. Guard coverage
        # proves containment of runtime data; it does not prove this is
        # operationally safe, so the two are recorded separately.
        post_parent_failure_propagated=False,
        post_parent_rollback_available=False,
        operational_risks=["FLYWHEEL_MIGRATION_FAILURE_SWALLOWED"],
        status=GUARDED_BY_CANONICAL_PARENT,
        evidence="CONSOLIDATED 2026-07-26. Old body was a bare unguarded chain. "
        "Unlike the other wrappers this one keeps real post-release work: "
        "`alembic upgrade head` and a .env mutation via vps_flywheel_enable.sh, "
        "then a no-rebuild restart. Recorded as post_parent_mutation=True rather "
        "than described as read-only verification, because it is not read-only "
        "and a comment-vs-code mismatch is what made selfheal unclassifiable. "
        "Containment holds on ORDERING: nothing mutates before the guarded "
        "parent, and nothing mutates if it returns 90/91 (proven in "
        "tests/test_release_wrapper_delegation.py).",
    ),
    _e(
        deployment_id="release.all",
        file="scripts/deploy_all.sh",
        entrypoint="bash scripts/deploy_all.sh",
        operation_class=NORMAL_RELEASE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        direct_or_wrapper="wrapper",
        canonical_parent=CANONICAL_RELEASE_PARENT,
        operations=["delegates release", "read-only skew report"],
        first_mutating_operation="scripts/deploy_vps.sh (delegated)",
        guard_strategy="CANONICAL_PARENT",
        guarded=True,
        guard_location="inherits deploy_vps.sh guard",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        status=GUARDED_BY_CANONICAL_PARENT,
        evidence="CONSOLIDATED 2026-07-26. Its whole purpose — rolling all five "
        "app-image services to clear :latest skew — is already a property of the "
        "parent, so only the extra read-only skew report remains. The "
        "`worker-heavy` hyphen hazard (a wrong service name aborts the entire "
        "`up`) now exists in one place instead of nine.",
    ),
    *[
        _e(
            deployment_id=f"release.adr{n}",
            file=f"scripts/deploy_adr{n}.sh",
            entrypoint=f"bash scripts/deploy_adr{n}.sh",
            operation_class=NORMAL_RELEASE,
            environment_scope=PRODUCTION,
            production_capable=True,
            runtime_data_mutation_capable=True,
            independently_invokable=True,
            direct_or_wrapper="wrapper",
            canonical_parent=CANONICAL_RELEASE_PARENT,
            operations=["delegates release", "read-only verification"],
            first_mutating_operation="scripts/deploy_vps.sh (delegated)",
            guard_strategy="CANONICAL_PARENT",
            guarded=True,
            guard_location="inherits deploy_vps.sh guard",
            guard_precedes_mutation=True,
            exit_code_propagated=True,
            status=GUARDED_BY_CANONICAL_PARENT,
            evidence="CONSOLIDATED 2026-07-26. Was a frozen fork of the release "
            "chain pinned to a historical SHA, with no guard. Now delegates; only "
            "its read-only post-checks remain. deploy_adr097.sh is the sharpest "
            "case: it exists to ship the image-PROVENANCE guard, yet was itself an "
            "unguarded release path.",
        )
        for n in ("095", "096", "097")
    ],
    *[
        _e(
            deployment_id=f"release.builder.{stem}",
            file=f"scripts/{stem}.py",
            entrypoint=f"python scripts/{stem}.py",
            language="python",
            operation_class=NORMAL_RELEASE,
            environment_scope=PRODUCTION,
            production_capable=True,
            runtime_data_mutation_capable=True,
            independently_invokable=True,
            direct_or_wrapper="wrapper",
            canonical_parent=CANONICAL_RELEASE_PARENT,
            operations=["delegates release", "read-only smoke"],
            first_mutating_operation="scripts/deploy_vps.sh (delegated)",
            guard_strategy="CANONICAL_PARENT",
            guarded=True,
            guard_location="inherits deploy_vps.sh guard",
            guard_precedes_mutation=True,
            exit_code_propagated=True,
            status=GUARDED_BY_CANONICAL_PARENT,
            evidence="CONSOLIDATED 2026-07-26. All three EXECUTED (subprocess.run), "
            "not merely emitted, and all three ran `git reset --hard origin/main` "
            "against the checkout holding live ledgers. vps_build_deploy.py was "
            "worse than it looked: each command ran in its OWN shell=True "
            "subprocess, so its leading `cd /opt/leadgen` did not apply to the "
            "reset that followed. Now: structured args, shell=False, single parent "
            "invocation, verbatim exit propagation. Proven by AST analysis in "
            "tests/test_python_builder_delegation.py (substring scans were "
            "rejected — they match this very prose).",
        )
        for stem in ("vps_build_deploy", "vps_deploy_dashboard", "vps_deploy_workflow_fix")
    ],
    _e(
        deployment_id="bootstrap.hermes",
        file="scripts/hostinger_hermes_bootstrap.sh",
        entrypoint="bash scripts/hostinger_hermes_bootstrap.sh",
        operation_class=BOOTSTRAP_PROVISIONING,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=True,
        independently_invokable=True,
        operations=["bootstrap preflight", "git clone (fresh target only)"],
        first_mutating_operation="git clone (after check-bootstrap)",
        bootstrap_classification="FRESH_HOST_BOOTSTRAP_ONLY",
        guard_strategy="BOOTSTRAP_PREFLIGHT",
        guarded=True,
        guard_location="before clone/fetch/reset/pip/config-write",
        guard_precedes_mutation=True,
        exit_code_propagated=True,
        status=GUARDED_DIRECTLY,
        evidence="PROTECTED 2026-07-26. Was EXISTING_HOST_MUTATION_CAPABLE: "
        'LOCAL_DIR="${LOCAL_DIR:-$HOME/leadgen}" defaults to a sandbox, but is '
        "env-overridable, so `LOCAL_DIR=/opt/leadgen` reached `git reset --hard "
        "origin/main` against the production checkout. A default is not a "
        "restriction and the file's `sandbox` comment enforced nothing. "
        "Now: `runtime_data_preflight.py check-bootstrap` classifies the target "
        "before ANY mutation, and the reset branch is DELETED rather than gated — "
        "an existing installation is refused (92) and the operator is directed to "
        "the release parent or a protected recovery path, so bootstrap cannot "
        "become a second deployment implementation. Codes 92/93/94 are distinct "
        "from the release parent's 90/91. Guarded DIRECTLY, not by Parent A: "
        "bootstrap may run before a checkout exists, which the release parent "
        "assumes. Proven behaviourally in tests/test_bootstrap_guard.py, including "
        "the LOCAL_DIR-override case that was the original defect.",
    ),
    # =========================== PRODUCTION BUT NOT RUNTIME-DATA MUTATION
    _e(
        deployment_id="config.sops_decrypt",
        file="scripts/sops_decrypt_env.sh",
        entrypoint="bash scripts/sops_decrypt_env.sh",
        operation_class=SECRET_CONFIG_PREPARATION,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=False,
        independently_invokable=True,
        operations=["write /opt/leadgen/.env"],
        first_mutating_operation="write .env",
        guard_strategy="NOT_REQUIRED_NON_RUNTIME_MUTATION",
        guarded=False,
        guard_precedes_mutation=False,
        exit_code_propagated=True,
        status=PRODUCTION_NON_RUNTIME_MUTATION,
        evidence="line 68 emits the compose command through `echo` as operator "
        "guidance; it is never executed. Writes .env only — cannot revert the "
        "checkout or replace containers. Needs its own config-safety controls "
        "(atomic write, backup, permissions), tracked separately.",
    ),
    # ================================================ NON-PRODUCTION
    _e(
        deployment_id="ci.tests_workflow",
        file=".github/workflows/tests.yml",
        entrypoint="GitHub Actions job",
        language="yaml",
        operation_class=TEST_CI,
        environment_scope=TEST_ONLY,
        production_capable=False,
        runtime_data_mutation_capable=False,
        independently_invokable=False,
        operations=["git checkout --orphan", "git clean -fdxq", "git push -f ci-debug"],
        first_mutating_operation="git checkout --orphan ci-debug",
        guard_strategy="NOT_REQUIRED_NON_PRODUCTION",
        guarded=False,
        guard_precedes_mutation=False,
        exit_code_propagated=True,
        status=NON_PRODUCTION,
        evidence="runs-on: ubuntu-latest; mutates only the runner's ephemeral "
        "checkout and pushes a ci-debug branch. No /opt/leadgen, no ssh, no "
        "production compose. The scanner matched the git identity ci@leadsgenai.in.",
    ),
    _e(
        deployment_id="restore.pg_drill",
        file="scripts/pg_restore_drill.sh",
        entrypoint="bash scripts/pg_restore_drill.sh (cron)",
        operation_class=DATABASE_RESTORE,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=False,
        independently_invokable=True,
        operations=["docker run --rm temp pg", "docker rm -f <temp>"],
        first_mutating_operation="docker run -d --rm --name $TMP",
        guard_strategy="NOT_REQUIRED_NON_RUNTIME_MUTATION",
        guarded=False,
        guard_precedes_mutation=False,
        exit_code_propagated=True,
        status=DIAGNOSTIC_ONLY,
        evidence="restores a backup into a THROWAWAY container; its `docker rm -f` "
        "targets that same temp container. Reads /opt/leadgen/backups. Never "
        "mutates the production checkout or production services.",
    ),
    _e(
        deployment_id="maintenance.selfheal",
        file="scripts/vps_selfheal.sh",
        entrypoint="bash scripts/vps_selfheal.sh (cron)",
        operation_class=RECOVERY_SELF_HEAL,
        environment_scope=PRODUCTION,
        production_capable=True,
        runtime_data_mutation_capable=False,
        independently_invokable=True,
        operations=[
            "docker stop (workers)",
            "docker restart (rate-limited)",
            "docker system prune -f --filter until=48h",
            "tar backup of data/",
        ],
        first_mutating_operation="docker stop -t 5 leadgen_worker ... (line 36)",
        # Out of the runtime-data denominator, but NOT risk-free. An unattended
        # `docker system prune` can remove stopped containers, unused networks,
        # unused images and build cache — which includes the ROLLBACK images the
        # release runbook depends on. That is a recovery-posture risk, not a
        # checkout-backed data-loss risk, so it is tracked here rather than
        # smuggled back into the guard count where it would distort the gate.
        operational_risks=[
            "SELF_HEAL_ROLLBACK_ASSET_RISK",
            "UNATTENDED_DOCKER_PRUNE",
            "NO_VOLUME_PRUNE_VERIFIED",
        ],
        guard_strategy="NOT_REQUIRED_NON_RUNTIME_MUTATION",
        guarded=False,
        guard_precedes_mutation=False,
        exit_code_propagated=False,
        status=PRODUCTION_NON_RUNTIME_MUTATION,
        evidence="RESOLVED by reading executable lines. It DOES mutate production: "
        "line 36 `docker stop` sheds workers, lines 64/77 `docker restart` (rate-"
        "limited 2/30min), line 92 `docker system prune -f --filter until=48h`. "
        "But none of that can destroy checkout-backed runtime data: restart is not "
        "recreate, no git operation exists anywhere in the file, and `prune` WITHOUT "
        "`--volumes` cannot remove the bind-mounted data dir. Line 110 tar is a "
        "backup (read). So: production-capable, container-affecting, but NOT "
        "runtime-data mutating. Guarded by a test asserting `--volumes` never "
        "appears — adding it would change this classification.",
    ),
]


def validate() -> list[str]:
    problems: list[str] = []
    ids = [e["deployment_id"] for e in ENTRYPOINTS]
    if len(ids) != len(set(ids)):
        problems.append("duplicate deployment_id")
    for e in ENTRYPOINTS:
        if e["status"] not in VALID_STATUSES:
            problems.append(f"{e['deployment_id']}: invalid status")
        if (
            requires_guard(e)
            and not e.get("guarded")
            and e["status"]
            not in (
                UNGUARDED_PRODUCTION_PATH,
                UNKNOWN_REQUIRES_REVIEW,
            )
        ):
            problems.append(f"{e['deployment_id']}: requires a guard but is not marked unguarded")
        if e.get("guarded") and not e.get("guard_precedes_mutation"):
            problems.append(f"{e['deployment_id']}: guarded but not before mutation")
    return problems


def requires_guard(e: dict[str, Any]) -> bool:
    """production_capable AND runtime_data_mutation_capable.

    `None` for mutation-capability means UNRESOLVED, which counts as requiring a
    guard — an unverified unattended script is not evidence of safety.
    """
    if not e.get("production_capable"):
        return False
    cap = e.get("runtime_data_mutation_capable")
    return cap is None or bool(cap)


def counts() -> dict[str, int]:
    req = [e for e in ENTRYPOINTS if requires_guard(e)]
    out = {
        "unique_logical_entrypoints": len(ENTRYPOINTS),
        "production_capable_entrypoints": sum(
            1 for e in ENTRYPOINTS if e.get("production_capable")
        ),
        "runtime_data_guard_required_entrypoints": len(req),
        "production_non_runtime_mutation_entrypoints": sum(
            1 for e in ENTRYPOINTS if e["status"] == PRODUCTION_NON_RUNTIME_MUTATION
        ),
        "non_production_entrypoints": sum(1 for e in ENTRYPOINTS if e["status"] == NON_PRODUCTION),
        "diagnostic_only_entrypoints": sum(
            1 for e in ENTRYPOINTS if e["status"] == DIAGNOSTIC_ONLY
        ),
        "directly_guarded_entrypoints": sum(1 for e in req if e["status"] == GUARDED_DIRECTLY),
        "parent_guarded_entrypoints": sum(
            1 for e in req if e["status"] == GUARDED_BY_CANONICAL_PARENT
        ),
        # An entry that REQUIRES a guard and does not have one is unguarded —
        # including UNKNOWN_REQUIRES_REVIEW. Leaving unknowns in their own
        # bucket would let the invariant balance while real exposure hid there,
        # and would let the release gate read zero before anyone had looked.
        "unguarded_runtime_data_entrypoints": sum(
            1
            for e in req
            if not e.get("guarded")
            and e["status"] in (UNGUARDED_PRODUCTION_PATH, UNKNOWN_REQUIRES_REVIEW)
        ),
        "unknown_entrypoints": sum(
            1 for e in ENTRYPOINTS if e["status"] == UNKNOWN_REQUIRES_REVIEW
        ),
        # Unknowns split by whether they land INSIDE the guard denominator. A
        # single "unknowns: 2" number hides which of them is actually exposure:
        # an unresolved script that cannot touch runtime data is bookkeeping,
        # one that can is an open hole. Both must be able to reach zero
        # independently, and the release gate reads only the first.
        "unknown_guard_required_entrypoints": sum(
            1 for e in ENTRYPOINTS if e["status"] == UNKNOWN_REQUIRES_REVIEW and requires_guard(e)
        ),
        "unknown_guard_not_required_entrypoints": sum(
            1
            for e in ENTRYPOINTS
            if e["status"] == UNKNOWN_REQUIRES_REVIEW and not requires_guard(e)
        ),
    }
    return out


__all__ = [
    "MANIFEST_VERSION",
    "ENTRYPOINTS",
    "VALID_STATUSES",
    "CANONICAL_RELEASE_PARENT",
    "requires_guard",
    "counts",
    "validate",
]
