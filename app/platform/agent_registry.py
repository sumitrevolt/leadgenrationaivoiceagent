"""
Canonical Agent Runtime Contract registry (Agent-OS control-plane foundation).
=============================================================================

WHY (2026-07-19, Phase-A foundation): the 31-agent workforce metadata was
SCATTERED and in places CONTRADICTORY across five sources —
``team.STAFF`` (display), ``scheduler_config.JOB_META`` (triggers/cadence),
``agent_controls.ALIAS_TO_MEMBER`` (job aliases), ``owner_os`` (supervisor /
service-identity sets) and the readiness scorecard doc. There was **no single
place** that answered the governance questions an enterprise Agent-OS needs:
what is each agent's *autonomy level*, *policy lane*, *kill switch*, *budget*,
*escalation target*, *useful-work heartbeat expectation*, and *acceptance test*.

This module is that single canonical layer. It is DERIVE-not-DUPLICATE:
  - display fields (name/team/title/duties/schedule)  ← app.platform.team.STAFF
  - triggers + cadence                                ← scheduler_config.JOB_META
  - governance (autonomy/lane/flag/kill/budget/…)     ← _GOVERNANCE table below
    (the only hand-authored data — none of it existed as data anywhere before)

⚠️  **LOAD-BEARING — NOT INERT.** (Corrected 2026-07-21; the previous docstring
claimed "nothing in the running app imports this yet", which is FALSE and was
dangerous to rely on.) This module is imported at runtime by:

  - ``app.platform.agent_runtime.evaluate_policy()``  (L507)  ← ENFORCEMENT
  - ``app.platform.agent_runtime.runtime_status()``   (L800)
  - ``app.platform.agent_status``                     (L189, L218)
  - ``app.platform.ops_assurance``                    (L82)

``evaluate_policy`` reads ``get_contract()`` as the dispatch source of truth
(L516) and blocks RED-lane / HARD_OFF agents off ``contract.lane`` (L521).

CONSEQUENCE — read before editing ``_GOVERNANCE`` below: changing an agent's
``lane`` from RED to GREEN/AMBER here does NOT merely change a report. It
directly removes the L521 dispatch block for that agent. The RED lane is the
mechanism that keeps the voice agents (swara/ananya) un-dispatchable. Treat
every ``_GOVERNANCE`` lane/mode edit as a RED-lane safety change requiring an
explicit owner mandate, not as documentation.

Invariant tests that must keep passing: L1049 (RED lane ⇒ HARD_OFF) and
L1055 (AMBER/RED must not default LIVE).

It exists so Boss (coordinator), Owner OS (control surface) and the contract
test-suite can all read ONE reconciled truth instead of five.

CANONICAL COUNT = 31 (code truth, matches owner_os.py: "manager=Boss is one of
the 31, not a 32nd agent"). Agent-OS itself (this registry + owner_os control
plane) is modelled as the 32nd *control-plane worker* via ``CONTROL_PLANE`` —
NOT as a 32nd persona. The customer-delivery-assurance responsibility that a
hypothetical "Aditi" would own is already owned by app.marketing.customer_delivery
+ delivery_ledger, so no new persona is invented (honest headcount).

Autonomy taxonomy (prompt spec):
  L0_OBSERVE      read-only checks + reporting
  L1_RECOMMEND    reason / diagnose / draft / propose (no side-effect execution)
  L2_INTERNAL     reversible internal actions from an explicit allowlist
  L3_CUSTOMER     customer-facing action under caps + policy + approval
  L4_RESTRICTED   calling / bulk / billing-mutation / destructive — mandate/HITL

Policy lanes (ceiling — the *max* the agent may ever do):
  GREEN  internal / draft / reconcile — safe to run when flag+budget+kill healthy
  AMBER  customer outreach — caps + shadow/draft/approval, starts non-live
  RED    calling / bulk / irreversible — never a simple .env flip; mandate only

Nothing here ever raises at import; ``build_registry`` degrades gracefully if an
upstream source is unavailable (import-safe, same contract as the rest of app).
"""

# ruff: noqa: C408  (the governance/CONTROL_PLANE tables use dict(...) kwargs on
# purpose: a 31-row keyword table reads and diffs far cleaner than brace-literals)
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class Team(str, Enum):
    PLATFORM = "platform"
    MARKETING = "marketing"
    VOICE = "voice"


class Lane(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class Autonomy(str, Enum):
    L0_OBSERVE = "L0_OBSERVE"
    L1_RECOMMEND = "L1_RECOMMEND"
    L2_INTERNAL = "L2_INTERNAL"
    L3_CUSTOMER = "L3_CUSTOMER"
    L4_RESTRICTED = "L4_RESTRICTED"


class TriggerType(str, Enum):
    SCHEDULED = "scheduled"  # durable Celery-beat / scheduler-loop entry
    EMBEDDED = "embedded"  # runs as a sub-engine inside another agent's job
    EVENT = "event"  # fired by an application hook / lifecycle event
    QUEUE = "queue"  # drains a durable queue (approval / cadence)
    INBOUND = "inbound"  # always-ready listener (inbound call / webhook)
    ON_DEMAND = "on_demand"  # operator / API triggered only
    NONE = "none"  # no trigger wired (drift — must be flagged)


# Start modes for the phased rollout (a lane ceiling of AMBER/RED must NOT start
# "live"; it starts in one of the non-committing modes below).
LIVE = "live"
DRAFT = "draft"
SHADOW = "shadow"
PROPOSAL = "proposal"
INBOUND_READY = "inbound_ready"
HARD_OFF = "hard_off"


# --------------------------------------------------------------------------- #
# The contract
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AgentContract:
    # identity (derived from team.STAFF)
    id: str
    name: str
    team: str
    title: str
    responsibility: str
    schedule_human: str
    # governance (hand-authored — the new canonical IP)
    autonomy: str
    lane: str
    default_mode: str
    reasoning: bool  # genuine LLM reasoning vs deterministic job
    trigger_types: tuple[str, ...]
    primary_flag: str  # Agent Runtime eligibility gate ("" = ungated/core)
    prohibited: tuple[str, ...]  # actions this agent must never take
    max_concurrency: int
    run_timeout_s: int
    retry_policy: str
    idempotency: str
    cost_budget_inr_day: float  # LLM/API rupee ceiling (0 = deterministic)
    api_calls_day: int  # external-API call ceiling
    customer_contact_cap_day: int  # outbound customer touches/day (0 = none)
    heartbeat_gap_min: int  # runtime "process alive" expected gap
    useful_work_gap_min: int | None  # business "did useful work" gap (None=event)
    escalation: str  # agent id or "owner"
    kill_switches: tuple[str, ...]  # owner_os kill keys that stop this agent
    test_ref: str
    # derived-at-build (triggers/cadence from JOB_META); default so __init__ stays tidy
    jobs: tuple[str, ...] = field(default_factory=tuple)
    cadences: tuple[str, ...] = field(default_factory=tuple)
    # Optional scheduler-only env flag (independent of Agent Runtime primary_flag).
    # Empty = no separate scheduler gate tracked on this contract.
    scheduler_flag: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]
        d["jobs"] = list(self.jobs)
        d["cadences"] = list(self.cadences)
        d["prohibited"] = list(self.prohibited)
        d["trigger_types"] = list(self.trigger_types)
        d["kill_switches"] = list(self.kill_switches)
        return d


# --------------------------------------------------------------------------- #
# Governance table — keyed by the 31 canonical team.STAFF ids.
# This is the ONLY hand-authored data. Everything else is derived.
# Tuple order: (autonomy, lane, default_mode, reasoning, trigger_types,
#   primary_flag, prohibited, max_conc, timeout_s, retry, idempotency,
#   cost_inr, api_day, contact_cap, hb_gap_min, useful_gap_min, escalation,
#   kill_switches, test_ref)
# --------------------------------------------------------------------------- #
_G = TriggerType  # local alias for brevity

_GOVERNANCE: dict[str, dict[str, Any]] = {
    # ---------------- PLATFORM (13) ---------------- #
    "manager": dict(
        autonomy=Autonomy.L2_INTERNAL,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=True,
        trigger_types=(_G.SCHEDULED, _G.ON_DEMAND),
        primary_flag="TEAM_AUTOMATION",
        prohibited=(
            "perform_red_action_directly",
            "bypass_specialist_policy",
            "customer_send_directly",
        ),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="none(coordinator idempotent)",
        idempotency="mission_key per goal",
        cost_inr=15.0,
        api_day=300,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=1560,
        escalation="owner",
        kill_switches=("owner_all_agents", "owner_schedulers"),
        test_ref="tests/test_agent_registry.py::test_boss_coordinator_contract",
    ),
    "kavya": dict(
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        # Runtime-only gate (Agent Runtime ops_health_check). Scheduler watchdog
        # stays on OPS_WATCHDOG — never OR these together for eligibility.
        primary_flag="OPS_HEALTH_AGENT",
        scheduler_flag="OPS_WATCHDOG",  # purpose=scheduler; agent_runtime_gate=false
        prohibited=("mutate_infra", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=120,
        retry_policy="skip-on-fail (next hour)",
        idempotency="run-due window marker",
        cost_inr=0.0,
        api_day=50,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="hermes",
        kill_switches=("owner_all_agents", "owner_schedulers"),
        test_ref="tests/test_agent_registry.py",
    ),
    "hermes": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=PROPOSAL,
        reasoning=False,
        trigger_types=(_G.EMBEDDED,),
        primary_flag="INFRA_HANDLER",
        prohibited=("destructive_infra_without_proposal", "restart_prod_without_approval"),
        max_concurrency=1,
        run_timeout_s=120,
        retry_policy="skip-on-fail",
        idempotency="scan snapshot",
        cost_inr=0.0,
        api_day=30,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="pranav",
        kill_switches=("owner_all_agents", "owner_schedulers"),
        test_ref="tests/test_agent_registry.py",
    ),
    "nikhil": dict(
        # Lane GREEN: capability is PURE READ (delivery_assurance.scan_missed_deliverables)
        # — no remediation/send/publish. Was AMBER historically; reconciled 2026-07-22.
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.EMBEDDED, _G.SCHEDULED),
        primary_flag="DELIVERY_ASSURANCE_AGENT",
        prohibited=(
            "mutate_billing_autonomously",
            "send_dunning_without_approval",
            "customer_contact",
        ),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="daily retry",
        idempotency="per-client per-day",
        cost_inr=5.0,
        api_day=50,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="owner",
        kill_switches=("owner_all_agents", "owner_bulk_email", "owner_payment_mutation"),
        test_ref="tests/test_agent_registry.py",
    ),
    "vikram": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=PROPOSAL,
        reasoning=True,
        trigger_types=(_G.EMBEDDED,),
        primary_flag="CODE_UPGRADER",
        prohibited=("merge_to_prod", "auto_apply_core_patch", "deploy"),
        max_concurrency=1,
        run_timeout_s=240,
        retry_policy="skip-on-fail",
        idempotency="patch proposal id",
        cost_inr=20.0,
        api_day=100,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="owner",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "guru": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.EMBEDDED,),
        primary_flag="SKILL_PACK",
        prohibited=("customer_contact",),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="skip-on-fail",
        idempotency="skill digest",
        cost_inr=5.0,
        api_day=40,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="manager",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "pranav": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="SRE_AGENT",
        prohibited=("mutate_infra_autonomously", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="skip-on-fail",
        idempotency="hourly window",
        cost_inr=0.0,
        api_day=30,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="owner",
        kill_switches=("owner_all_agents", "owner_schedulers"),
        test_ref="tests/test_owner_scheduler_kill.py",
    ),
    "vidya": dict(
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="FINOPS_AGENT",
        prohibited=("mutate_billing", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=120,
        retry_policy="daily retry",
        idempotency="daily digest",
        cost_inr=2.0,
        api_day=20,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="owner",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "arnav": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=PROPOSAL,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        # Runtime-only gate (Agent Runtime run_security core). Daily scheduler
        # stays on SECURITY_AGENT — never OR these together for eligibility.
        primary_flag="SECURITY_POSTURE_AGENT",
        scheduler_flag="SECURITY_AGENT",  # purpose=scheduler; agent_runtime_gate=false
        prohibited=("disable_compliance_gate", "rotate_secrets_autonomously", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="daily retry",
        idempotency="daily posture",
        cost_inr=2.0,
        api_day=20,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="owner",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "kabir": dict(
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="DBRE_AGENT",
        prohibited=("write_prod_db", "run_migration_autonomously", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=120,
        retry_policy="daily retry",
        idempotency="daily pg-health",
        cost_inr=0.0,
        api_day=10,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="pranav",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "diya": dict(
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="DATA_INTEGRITY_AGENT",
        prohibited=("dedupe_without_human_approval", "delete_records", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="daily retry",
        idempotency="daily integrity scan",
        cost_inr=0.0,
        api_day=10,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="owner",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "aryan": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=PROPOSAL,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="DEPS_AGENT",
        prohibited=("auto_upgrade_dependency", "commit", "deploy"),
        max_concurrency=1,
        run_timeout_s=300,
        retry_policy="weekly retry",
        idempotency="weekly audit",
        cost_inr=0.0,
        api_day=20,
        contact_cap=0,
        hb_gap_min=11520,
        useful_gap_min=11520,
        escalation="arnav",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "arya": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="MCP_ENGINEER",
        prohibited=("expose_mcp_without_auth_gate", "customer_contact"),
        max_concurrency=1,
        run_timeout_s=120,
        retry_policy="skip-on-fail",
        idempotency="hourly health",
        cost_inr=0.0,
        api_day=30,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="arnav",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    # ---------------- MARKETING (10) ---------------- #
    "dev": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.EVENT, _G.EMBEDDED),
        primary_flag="ML_NIGHTLY_TRAINING",
        prohibited=("customer_contact", "leak_cross_client_data"),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="per-client retry",
        idempotency="per-client KB seed",
        cost_inr=5.0,
        api_day=50,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="manager",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "rohan": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.AMBER,
        default_mode=DRAFT,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="AUTO_EMAIL_OUTREACH",
        prohibited=("exceed_25_email_day", "tos_blocked_scrape", "customer_call"),
        max_concurrency=2,
        run_timeout_s=240,
        retry_policy="DLQ + backoff",
        idempotency="per-lead per-step",
        cost_inr=10.0,
        api_day=100,
        contact_cap=25,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="manager",
        kill_switches=("owner_all_agents", "owner_bulk_email"),
        test_ref="tests/test_agent_registry.py",
    ),
    "isha": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=DRAFT,
        reasoning=True,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="AFTERNOON_CONTENT",
        prohibited=("publish_without_approval", "customer_contact"),
        max_concurrency=2,
        run_timeout_s=240,
        retry_policy="skip-on-fail",
        idempotency="per-client per-day content",
        cost_inr=25.0,
        api_day=150,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="manager",
        kill_switches=("owner_all_agents", "owner_publishing"),
        test_ref="tests/test_agent_registry.py",
    ),
    "ravi": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.EMBEDDED,),
        primary_flag="INDEXNOW",
        prohibited=("customer_contact",),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="skip-on-fail",
        idempotency="page slug",
        cost_inr=5.0,
        api_day=60,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="manager",
        kill_switches=("owner_all_agents", "owner_publishing"),
        test_ref="tests/test_agent_registry.py",
    ),
    "neha": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="",
        prohibited=("customer_contact",),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="daily retry",
        idempotency="daily rescore",
        cost_inr=2.0,
        api_day=20,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="rohan",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "kiran": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.AMBER,
        default_mode=PROPOSAL,
        reasoning=False,
        trigger_types=(_G.EMBEDDED,),
        primary_flag="CAMPAIGN_OPTIMIZER",
        prohibited=("change_customer_budget", "promote_without_eval_gate"),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="skip-on-fail",
        idempotency="per-100-interactions",
        cost_inr=10.0,
        api_day=50,
        contact_cap=0,
        hb_gap_min=11520,
        useful_gap_min=None,
        escalation="manager",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "priya": dict(
        autonomy=Autonomy.L2_INTERNAL,
        lane=Lane.AMBER,
        default_mode=SHADOW,
        reasoning=False,
        trigger_types=(_G.EVENT, _G.QUEUE),
        primary_flag="CRM_SYNC",
        prohibited=("delete_crm_records", "leak_cross_client_data"),
        max_concurrency=2,
        run_timeout_s=120,
        retry_policy="DLQ + backoff",
        idempotency="per-lead crm push",
        cost_inr=2.0,
        api_day=100,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="manager",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "zara": dict(
        autonomy=Autonomy.L2_INTERNAL,
        lane=Lane.AMBER,
        default_mode=SHADOW,
        reasoning=False,
        trigger_types=(_G.QUEUE,),
        primary_flag="SOCIAL_ENGINE",
        prohibited=("publish_client_brand_without_approval", "bulk_whatsapp_autosend"),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="DLQ + backoff",
        idempotency="per-content-item publish",
        cost_inr=2.0,
        api_day=80,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="isha",
        kill_switches=("owner_all_agents", "owner_publishing", "social_pause"),
        test_ref="tests/test_agent_registry.py",
    ),
    "anika": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.AMBER,
        default_mode=DRAFT,
        reasoning=False,
        trigger_types=(_G.SCHEDULED, _G.QUEUE),
        primary_flag="CADENCE_ENGINE",
        prohibited=("exceed_contact_cap", "message_suppressed_contact"),
        max_concurrency=2,
        run_timeout_s=180,
        retry_policy="DLQ + backoff",
        idempotency="per-lead per-day step",
        cost_inr=5.0,
        api_day=100,
        contact_cap=25,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="rohan",
        kill_switches=("owner_all_agents", "owner_bulk_email", "owner_whatsapp_outbound"),
        test_ref="tests/test_agent_registry.py",
    ),
    "ira": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.AMBER,
        default_mode=DRAFT,
        reasoning=False,
        trigger_types=(_G.EVENT,),
        primary_flag="JOURNEY_ENGINE",
        prohibited=("customer_send_without_approval",),
        max_concurrency=2,
        run_timeout_s=120,
        retry_policy="DLQ + backoff",
        idempotency="per-lead journey step",
        cost_inr=5.0,
        api_day=80,
        contact_cap=25,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="rohan",
        kill_switches=("owner_all_agents", "owner_bulk_email"),
        test_ref="tests/test_agent_registry.py",
    ),
    # ---------------- VOICE (8) ---------------- #
    "swara": dict(
        autonomy=Autonomy.L4_RESTRICTED,
        lane=Lane.RED,
        default_mode=HARD_OFF,
        reasoning=True,
        trigger_types=(_G.SCHEDULED, _G.ON_DEMAND),
        primary_flag="PLATFORM_DIAL_DAILY",
        prohibited=(
            "cold_outbound_without_dlt_and_mandate",
            "foreign_trunk_india_domestic",
            "call_outside_9_19_window",
        ),
        max_concurrency=1,
        run_timeout_s=600,
        retry_policy="no-auto-retry (call)",
        idempotency="campaign single-flight lock",
        cost_inr=0.0,
        api_day=0,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="raksha",
        kill_switches=("owner_all_agents", "voice_launch_kill", "platform_dial"),
        test_ref="scripts/agent_tester.py",
    ),
    "ananya": dict(
        autonomy=Autonomy.L4_RESTRICTED,
        lane=Lane.RED,
        default_mode=HARD_OFF,
        reasoning=True,
        trigger_types=(_G.ON_DEMAND, _G.EVENT),
        primary_flag="",
        prohibited=("cold_outbound_without_dlt_and_mandate", "book_without_customer_consent"),
        max_concurrency=1,
        run_timeout_s=600,
        retry_policy="no-auto-retry (call)",
        idempotency="per-booking slot",
        cost_inr=0.0,
        api_day=0,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="raksha",
        kill_switches=("owner_all_agents", "voice_launch_kill"),
        test_ref="tests/test_agent_registry.py",
    ),
    "riya": dict(
        autonomy=Autonomy.L3_CUSTOMER,
        lane=Lane.AMBER,
        default_mode=INBOUND_READY,
        reasoning=True,
        trigger_types=(_G.INBOUND,),
        primary_flag="",
        prohibited=("sales_pitch", "outbound_cold_call"),
        max_concurrency=4,
        run_timeout_s=600,
        retry_policy="no-auto-retry (call)",
        idempotency="per-inbound session",
        cost_inr=0.0,
        api_day=0,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="raksha",
        kill_switches=("owner_all_agents", "voice_launch_kill"),
        test_ref="tests/test_agent_registry.py",
    ),
    "arjun": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="VOICE_EVAL_AUTO",
        prohibited=("customer_contact",),
        max_concurrency=1,
        run_timeout_s=300,
        retry_policy="daily retry",
        idempotency="daily qa run",
        cost_inr=5.0,
        api_day=40,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="meera",
        kill_switches=("owner_all_agents",),
        test_ref="scripts/agent_tester.py",
    ),
    "meera": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="KB_WEEKLY_REFRESH",
        prohibited=("customer_contact", "promote_without_eval"),
        max_concurrency=1,
        run_timeout_s=300,
        retry_policy="daily retry",
        idempotency="daily trainer",
        cost_inr=10.0,
        api_day=60,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="manager",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "lekha": dict(
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.SCHEDULED,),
        primary_flag="",
        prohibited=("customer_contact",),
        max_concurrency=1,
        run_timeout_s=180,
        retry_policy="daily retry",
        idempotency="daily kpi digest",
        cost_inr=0.0,
        api_day=10,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=1560,
        escalation="manager",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
    "raksha": dict(
        autonomy=Autonomy.L1_RECOMMEND,
        lane=Lane.AMBER,
        default_mode=INBOUND_READY,
        reasoning=False,
        trigger_types=(_G.EVENT,),
        primary_flag="CALL_TRANSFER",
        prohibited=("fabricate_human_availability", "outbound_cold_call"),
        max_concurrency=4,
        run_timeout_s=120,
        retry_policy="no-auto-retry",
        idempotency="per-escalation",
        cost_inr=0.0,
        api_day=0,
        contact_cap=0,
        hb_gap_min=1560,
        useful_gap_min=None,
        escalation="owner",
        kill_switches=("owner_all_agents", "voice_launch_kill"),
        test_ref="tests/test_agent_registry.py",
    ),
    "tara": dict(
        autonomy=Autonomy.L0_OBSERVE,
        lane=Lane.GREEN,
        default_mode=LIVE,
        reasoning=False,
        trigger_types=(_G.EMBEDDED,),
        primary_flag="TELEPHONY_READY_ALERTS",
        prohibited=("customer_contact", "place_call"),
        max_concurrency=1,
        run_timeout_s=120,
        retry_policy="skip-on-fail",
        idempotency="hourly readiness",
        cost_inr=0.0,
        api_day=20,
        contact_cap=0,
        hb_gap_min=90,
        useful_gap_min=90,
        escalation="raksha",
        kill_switches=("owner_all_agents",),
        test_ref="tests/test_agent_registry.py",
    ),
}


# --------------------------------------------------------------------------- #
# Control-plane worker (the honest "32nd") — NOT one of the 31 personas.
# Models Agent-OS itself (this registry + owner_os control surface + scheduler
# guard) as a coordinating control-plane worker, per the prompt's fallback
# branch (delivery-assurance already owned by customer_delivery, so no new
# persona is invented).
# --------------------------------------------------------------------------- #
CONTROL_PLANE: dict[str, Any] = {
    "id": "agent_os",
    "name": "Agent-OS Control Plane",
    "team": "control_plane",
    "title": "Control-plane worker (registry + owner_os + scheduler guard)",
    "responsibility": (
        "Canonical registry, work-lifecycle governance, kill-switch/dispatch "
        "gating, heartbeat + stale detection, Boss routing surface. Not a "
        "counted persona — the coordinating layer over the 31 workforce agents."
    ),
    "autonomy": Autonomy.L0_OBSERVE.value,
    "lane": Lane.GREEN.value,
    "counts_toward_workforce": False,
}


# Known reconciliation drifts this registry canonicalises (surfaced by the test
# so they are fixed, not silently rotting). Each is (locus, drift, canonical).
KNOWN_DRIFTS: tuple[dict[str, str], ...] = (
    {
        "locus": "scheduler_config.JOB_META['social_drain'].owner",
        "drift": "owner=isha, but the publish executor is zara (Social Media Manager)",
        "canonical": "isha triggers social_drain; zara is the publish executor (owner_publishing lane)",
    },
    {
        "locus": "docs/AGENT_ENTERPRISE_READINESS_SCORECARD.md title",
        "drift": "title says '32 Agent-OS agents'",
        "canonical": "31 personas (manager=Boss is one of them); Agent-OS is the control plane, not a 32nd persona",
    },
    {
        "locus": "JOB_META.owner pseudo-keys 'boss' / 'platform'",
        "drift": "not team.STAFF keys",
        "canonical": "'boss' == 'manager' persona; 'platform' == control-plane service jobs (no persona)",
    },
)

# STAFF agents with no durable beat trigger — by-design event/on-demand, MUST
# report healthy-idle (not offline) once the useful-work heartbeat lands.
EVENT_OR_ONDEMAND_ONLY: frozenset[str] = frozenset(
    {"ananya", "riya", "raksha", "nikhil", "priya", "anika", "ira", "dev", "kiran"}
)


# --------------------------------------------------------------------------- #
# Builders (derive-not-duplicate)
# --------------------------------------------------------------------------- #
def _staff() -> dict[str, dict[str, Any]]:
    try:
        from app.platform.team import STAFF

        return dict(STAFF)
    except Exception:
        return {}


def _job_meta() -> dict[str, dict[str, str]]:
    try:
        from app.platform.scheduler_config import JOB_META

        return dict(JOB_META)
    except Exception:
        return {}


def _jobs_for_agent(
    agent_id: str, job_meta: dict[str, dict[str, str]]
) -> tuple[list[str], list[str]]:
    """Reverse-map JOB_META (owner->jobs). 'boss' owner folds into 'manager'."""
    want = {agent_id}
    if agent_id == "manager":
        want.add("boss")
    jobs: list[str] = []
    cadences: list[str] = []
    for job, meta in job_meta.items():
        if str(meta.get("owner") or "") in want:
            jobs.append(job)
            cadences.append(str(meta.get("cadence") or ""))
    return jobs, cadences


def build_registry() -> dict[str, AgentContract]:
    """Assemble the canonical contract per agent from the single sources.

    Import-safe: if team.STAFF is unavailable, falls back to the governance
    table's own keys so the registry is never empty.
    """
    staff = _staff()
    job_meta = _job_meta()
    ids = list(staff.keys()) or list(_GOVERNANCE.keys())
    out: dict[str, AgentContract] = {}
    for aid in ids:
        gov = _GOVERNANCE.get(aid)
        if gov is None:
            # Unknown STAFF key with no governance = drift; skip but it will be
            # caught by validate_registry (missing_governance).
            continue
        info = staff.get(aid, {})
        jobs, cadences = _jobs_for_agent(aid, job_meta)
        team_val = str(info.get("product") or "platform")
        out[aid] = AgentContract(
            id=aid,
            name=str(info.get("name") or aid.title()),
            team=team_val,
            title=str(info.get("title") or ""),
            responsibility=str(info.get("duties") or ""),
            schedule_human=str(info.get("schedule") or ""),
            autonomy=(
                gov["autonomy"].value
                if isinstance(gov["autonomy"], Autonomy)
                else str(gov["autonomy"])
            ),
            lane=gov["lane"].value if isinstance(gov["lane"], Lane) else str(gov["lane"]),
            default_mode=str(gov["default_mode"]),
            reasoning=bool(gov["reasoning"]),
            trigger_types=tuple(
                t.value if isinstance(t, TriggerType) else str(t) for t in gov["trigger_types"]
            ),
            primary_flag=str(gov["primary_flag"]),
            prohibited=tuple(gov["prohibited"]),
            max_concurrency=int(gov["max_concurrency"]),
            run_timeout_s=int(gov["run_timeout_s"]),
            retry_policy=str(gov["retry_policy"]),
            idempotency=str(gov["idempotency"]),
            cost_budget_inr_day=float(gov["cost_inr"]),
            api_calls_day=int(gov["api_day"]),
            customer_contact_cap_day=int(gov["contact_cap"]),
            heartbeat_gap_min=int(gov["hb_gap_min"]),
            useful_work_gap_min=(
                None if gov["useful_gap_min"] is None else int(gov["useful_gap_min"])
            ),
            escalation=str(gov["escalation"]),
            kill_switches=tuple(gov["kill_switches"]),
            test_ref=str(gov["test_ref"]),
            jobs=tuple(jobs),
            cadences=tuple(cadences),
            scheduler_flag=str(gov.get("scheduler_flag") or ""),
        )
    return out


def get_contract(agent_id: str) -> AgentContract | None:
    return build_registry().get(agent_id)


def all_contracts() -> dict[str, AgentContract]:
    return build_registry()


def by_lane(lane: str) -> list[AgentContract]:
    lv = lane.value if isinstance(lane, Lane) else str(lane)
    return [c for c in build_registry().values() if c.lane == lv]


def by_team(team: str) -> list[AgentContract]:
    tv = team.value if isinstance(team, Team) else str(team)
    return [c for c in build_registry().values() if c.team == tv]


CANONICAL_COUNT = 31
_VALID_TEAMS = {"platform", "marketing", "voice"}
_VALID_LANES = {l.value for l in Lane}
_VALID_AUTONOMY = {a.value for a in Autonomy}
_VALID_MODES = {LIVE, DRAFT, SHADOW, PROPOSAL, INBOUND_READY, HARD_OFF}


def validate_registry() -> list[str]:
    """Return a list of reconciliation problems (empty = clean). Never raises.

    Enforces the enterprise Agent-OS invariants the prompt requires + the
    project's §5 compliance gates. The contract test asserts this is empty.
    """
    problems: list[str] = []
    staff = _staff()
    reg = build_registry()

    # 1. Reconciliation: every STAFF key has exactly one contract & vice-versa.
    staff_keys = set(staff.keys())
    reg_keys = set(reg.keys())
    gov_keys = set(_GOVERNANCE.keys())
    if staff_keys:
        for k in sorted(staff_keys - gov_keys):
            problems.append(f"STAFF key '{k}' has no governance contract")
        for k in sorted(gov_keys - staff_keys):
            problems.append(f"governance key '{k}' is not a STAFF member (orphan)")
        if len(reg_keys) != len(staff_keys):
            problems.append(f"contract count {len(reg_keys)} != STAFF count {len(staff_keys)}")

    # 2. Honest canonical count.
    if staff_keys and len(staff_keys) != CANONICAL_COUNT:
        problems.append(f"STAFF count {len(staff_keys)} != canonical {CANONICAL_COUNT}")

    # 3. Per-contract field validity.
    for aid, c in reg.items():
        if c.team not in _VALID_TEAMS:
            problems.append(f"{aid}: invalid team '{c.team}'")
        if c.lane not in _VALID_LANES:
            problems.append(f"{aid}: invalid lane '{c.lane}'")
        if c.autonomy not in _VALID_AUTONOMY:
            problems.append(f"{aid}: invalid autonomy '{c.autonomy}'")
        if c.default_mode not in _VALID_MODES:
            problems.append(f"{aid}: invalid default_mode '{c.default_mode}'")
        if not c.trigger_types:
            problems.append(f"{aid}: no trigger_types (every agent needs >=1 legitimate trigger)")
        if not c.kill_switches:
            problems.append(f"{aid}: no kill switch mapped")
        if not c.test_ref:
            problems.append(f"{aid}: no test_ref")
        if not c.escalation:
            problems.append(f"{aid}: no escalation target")
        if c.customer_contact_cap_day < 0:
            problems.append(f"{aid}: negative contact cap")

    # 4. §5 compliance gates — lane/mode must encode the hard invariants.
    for aid in ("swara", "ananya"):
        c = reg.get(aid)
        if c and (c.lane != Lane.RED.value or c.default_mode != HARD_OFF):
            problems.append(
                f"{aid}: cold-outbound voice must be RED + hard_off (§5 platform_dial HARD-OFF)"
            )
    for aid, c in reg.items():
        # No AMBER/RED agent may START live — it must begin non-committing.
        if c.lane in (Lane.AMBER.value, Lane.RED.value) and c.default_mode == LIVE:
            problems.append(
                f"{aid}: lane {c.lane} must not default to LIVE (start shadow/draft/off)"
            )
        # Every agent must be stoppable by the global kill.
        if "owner_all_agents" not in c.kill_switches:
            problems.append(f"{aid}: must be covered by owner_all_agents global kill")

    # 5. Escalation targets must resolve to a real agent id or 'owner'.
    valid_targets = reg_keys | {"owner"}
    for aid, c in reg.items():
        if c.escalation not in valid_targets:
            problems.append(
                f"{aid}: escalation target '{c.escalation}' is not a known agent or 'owner'"
            )

    # 6. Dispatchable pilots/canary-ready agents MUST have an explicit primary_flag.
    #    Empty/null = ungated under AGENT_RUNTIME (production Nikhil canary blocker 2026-07-22).
    #    Allowed empty: RED hard_off / frozen voice only (never pilot-dispatchable).
    try:
        from app.platform.agent_runtime import PILOT_AGENTS

        for aid in sorted(PILOT_AGENTS):
            c = reg.get(aid)
            if not c:
                problems.append(f"{aid}: in PILOT_AGENTS but missing registry contract")
                continue
            flag = (c.primary_flag or "").strip()
            if not flag:
                problems.append(
                    f"{aid}: dispatchable pilot must have non-empty primary_flag "
                    "(ungated agents forbidden under AGENT_RUNTIME)"
                )
            if c.lane == Lane.RED.value or c.default_mode == HARD_OFF:
                problems.append(
                    f"{aid}: RED/hard_off agent must not be in PILOT_AGENTS dispatch allowlist"
                )
    except Exception as exc:
        problems.append(f"pilot_flag_validation_error:{type(exc).__name__}")

    return problems


def summary() -> dict[str, Any]:
    """Owner-facing rollup — safe to serialise into an Owner OS panel."""
    reg = build_registry()
    lanes: dict[str, int] = {}
    auton: dict[str, int] = {}
    reasoning = 0
    for c in reg.values():
        lanes[c.lane] = lanes.get(c.lane, 0) + 1
        auton[c.autonomy] = auton.get(c.autonomy, 0) + 1
        reasoning += 1 if c.reasoning else 0
    return {
        "canonical_count": len(reg),
        "expected_count": CANONICAL_COUNT,
        "by_lane": lanes,
        "by_autonomy": auton,
        "reasoning_agents": reasoning,
        "control_plane": CONTROL_PLANE["id"],
        "known_drifts": len(KNOWN_DRIFTS),
        "problems": validate_registry(),
    }


__all__ = [
    "Team",
    "Lane",
    "Autonomy",
    "TriggerType",
    "AgentContract",
    "build_registry",
    "get_contract",
    "all_contracts",
    "by_lane",
    "by_team",
    "validate_registry",
    "summary",
    "CONTROL_PLANE",
    "KNOWN_DRIFTS",
    "EVENT_OR_ONDEMAND_ONLY",
    "CANONICAL_COUNT",
]
