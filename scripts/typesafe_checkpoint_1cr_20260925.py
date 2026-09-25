#!/usr/bin/env python3
"""TypeSafe checkpoint trace for the 2026-09-25 1CR OmniRoute recovery.

The owner directive requires a real TypeSafe judgment at intake, intermediate QA
and delivery, with requested/resolved model + latency recorded, and forbids
fabricating a call when the credential is unavailable. This uses the platform's
OWN canonical entrypoints (typesafe_choice / typesafe_noul / typesafe_score) --
no second SDK, no second key pool, no direct HTTP.

A transport failure is reported as a transport failure, never as a bad credential.

Read-only: it judges, it changes nothing.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.platform import typesafe_integration as ts  # noqa: E402

STATE = {
    "incident": "OmniRoute VPS inference outage, 2026-09-25",
    "gateway": "srv1736379 leadgen_omniroute, storage.sqlite volume",
    "layer1_provider_connections": "0 rows -> 6 seeded (cerebras,gemini,groq,mistral,nvidia,openrouter)",
    "layer2_combo_slots": "42 -> 8 per combo, 476 credential-less slots dropped",
    "layer3_retired_models": "112 slots repointed to live ids from each provider /models",
    "app_container": "leadgen_app healthy b5d806fe, never restarted",
    "combo_verify": "14 sequential probes with latency",
}

CHECKPOINTS = [
    (
        "intake",
        ts.typesafe_choice,
        "Are these three layers the true root causes of the OmniRoute outage, in this order?",
        ["yes_ordered_three_layers", "credential_only", "slot_count_only", "reject_diagnosis"],
    ),
    (
        "intermediate_qa",
        ts.typesafe_noul,
        "After seeding credentials and pruning credential-less slots, combos still timed out. "
        "Provider /models returns live ids; the surviving slots named retired ones "
        "(groq 404 llama-3.3-70b-versatile, cerebras 404 llama-3.3-70b, "
        "gemini-2.5-pro no longer available to new users). Is repointing slots to "
        "provider-reported live ids the correct fix, and what is the main risk?",
        None,
    ),
    (
        "delivery",
        ts.typesafe_score,
        "Rate delivery readiness: 112 slot repoints applied with backup + idempotency, "
        "gateway restarted, 14/14 combo inference verification, 4 new scripts on a "
        "feature branch, no app deploy, no main edit.",
        ["ready_to_open_draft_pr", "ready_after_one_more_check", "hold_for_owner_gate", "reject"],
    ),
]


def redact(obj) -> str:
    s = json.dumps(obj, default=str)
    s = re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-***REDACTED***", s)
    s = re.sub(r"\b[A-Za-z0-9_\-]{40,}\b", "<REDACTED>", s)
    return s[:500]


def main() -> int:
    print("TypeSafe checkpoint trace — requested model: jev-latest")
    print(f"credential state: {ts.credential_state()}\n")
    unavailable = 0

    for i, (name, fn, question, criteria) in enumerate(CHECKPOINTS, 1):
        t0 = time.time()
        try:
            if criteria is None:
                r = fn(question, STATE)
            else:
                r = fn(question, STATE, criteria)
            dt = time.time() - t0
            print(f"[{i}] {name}")
            print(f"    requested=jev-latest resolved={getattr(r, 'model', '?')} latency={dt:.2f}s")
            print(f"    result: {redact(getattr(r, 'answer', r))}")
        except Exception as e:  # noqa: BLE001 - report honestly, never fake
            unavailable += 1
            dt = time.time() - t0
            print(f"[{i}] {name}")
            print(
                f"    TypeSafe call UNAVAILABLE after {dt:.2f}s — "
                f"{type(e).__name__}: {str(e)[:200]}"
            )
        print()

    if unavailable:
        print(
            f"{unavailable}/{len(CHECKPOINTS)} checkpoints: TypeSafe call unavailable "
            "(transport/credential issue, not a fabricated result)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
