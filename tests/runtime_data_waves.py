"""Declared registry: wave name → store ids that wave migrated.

Each wave ratchet used to hardcode an exact global set (moved == A1 | A2,
moved == A1 | A3, …). Those assertions are true alone and false once another
wave lands — and because manifest edits touch different rows, git merges them
without complaint. The failure then shows up in CI on whichever branch merged
second.

This module is the single declared source of wave → ids. The exact-global
assertion lives in ``test_runtime_data_waves.py`` and is derived from the
union of every wave here. Ids are taken from the existing ratchet files, not
retyped from the manifest — the non-vacuity test is what proves the two
sources agree.
"""

from __future__ import annotations

#: Stores A1 migrated (telephony kill switches / dial suppression).
A1_STORE_IDS = frozenset(
    {
        "telephony.voice_kill_switch",
        "telephony.calling_safety_config",
        "telephony.dial_suppression",
    }
)

#: Stores A2 migrated (WA / consent / voice suppression).
A2_STORE_IDS = frozenset(
    {
        "compliance.wa_suppression",
        "compliance.consent_ledger",
        "compliance.voice_suppression",
    }
)

#: Stores A3 migrated (email suppression + DPDP audit).
A3_STORE_IDS = frozenset(
    {
        "compliance.email_suppression",
        "compliance.dpdp_audit",
    }
)

#: Stores A4 migrated (customer delivery: content queue/approvals + delivery ledger).
A4_STORE_IDS = frozenset(
    {
        "content.queue",
        "content.approvals",
        "delivery.ledger",
    }
)

#: Stores A5 migrated (billing invoices/UPI + customer identity registry).
A5_STORE_IDS = frozenset(
    {
        "billing.invoices",
        "billing.upi_payments",
        "customers.identity",
    }
)

#: Stores A6 migrated (ops telemetry: cadence / job runs / interactions JSONL).
A6_STORE_IDS = frozenset(
    {
        "automation.cadence_runs",
        "automation.job_runs",
        "communications.interactions",
    }
)

#: Stores A7 migrated (sales prospect JSONL — large file, code-only this wave).
A7_STORE_IDS = frozenset(
    {
        "sales.prospects",
    }
)

#: Stores A8 migrated (external agent mission root — EXTERNAL_MISSION_DIR).
A8_STORE_IDS = frozenset(
    {
        "devcontrol.external_missions",
    }
)

#: Stores A9 migrated (call recordings + transcripts — last LEGACY blockers).
A9_STORE_IDS = frozenset(
    {
        "artifacts.call_recordings",
        "telephony.call_recordings",
    }
)

#: wave name → frozenset of store ids. Add a new wave here; do not invent a
#: second exact-global assertion in that wave's own ratchet.
WAVE_STORE_IDS: dict[str, frozenset[str]] = {
    "A1": A1_STORE_IDS,
    "A2": A2_STORE_IDS,
    "A3": A3_STORE_IDS,
    "A4": A4_STORE_IDS,
    "A5": A5_STORE_IDS,
    "A6": A6_STORE_IDS,
    "A7": A7_STORE_IDS,
    "A8": A8_STORE_IDS,
    "A9": A9_STORE_IDS,
}


def all_declared_store_ids() -> frozenset[str]:
    """Union of every store id declared in any wave."""
    out: set[str] = set()
    for ids in WAVE_STORE_IDS.values():
        out |= set(ids)
    return frozenset(out)
