# Agent Runtime ? Local Canary Proof

- **When (UTC):** `2026-07-21T15:31:23.689729+00:00`
- **Scope:** LOCAL real-engine canary only (`AGENT_RUNTIME=1`, `SRE_AGENT=1`). **NOT production.**
- **Production:** flags remain OFF; no deploy; Swara frozen; calling/voice untouched.
- **Idempotency key:** `canary-local-pranav-20260721T153123Z`
- **Pilots (12):** `arnav, arya, aryan, diya, hermes, isha, kabir, kavya, nikhil, pranav, vidya, zara`

## Cases

### pranav_run_1

- status: `succeeded`
- reason: ``
- output_keys: `['check', 'read_only', 'result']`
- lifecycle: `['queued', 'leased', 'running', 'succeeded']`
- output_safe: `{"check": "sre", "read_only": true, "result_ok": null, "result_score": 53.3, "result_keys": ["actions", "agent", "kpis", "role", "score", "status", "summary", "ts"]}`

### pranav_run_2_same_idem

- status: `skipped`
- reason: `duplicate_suppressed`
- output_keys: `None`
- lifecycle: `['queued', 'leased', 'skipped']`

### pranav_unknown_action

- status: `blocked`
- reason: `capability_not_registered:totally_unknown_action_xyz`
- output_keys: `None`
- lifecycle: `['queued', 'blocked']`

### swara_frozen

- status: `blocked`
- reason: `red_lane_hard_off_mandate_required`
- output_keys: `None`
- lifecycle: `['queued', 'blocked']`

### pranav_after_cancel

- status: `blocked`
- reason: `cancel_requested`
- output_keys: `None`
- lifecycle: `['queued', 'blocked']`

### pranav_after_clear_cancel

- status: `succeeded`
- reason: ``
- output_keys: `['check', 'read_only', 'result']`
- lifecycle: `['queued', 'leased', 'running', 'succeeded']`
- output_safe: `{"check": "sre", "read_only": true, "result_ok": null, "result_score": 53.3, "result_keys": ["actions", "agent", "kpis", "role", "score", "status", "summary", "ts"]}`

## Cancel / clear

- request_cancel(pranav): `{"ok": true, "agent_id": "pranav", "cancelled": true}`
- clear_cancel(pranav): `{"ok": true, "agent_id": "pranav", "cancelled": false}`

## Verdict

- idempotent pranav double-submit: **PASS**
- unknown action blocked: **PASS**
- swara frozen red blocked: **PASS**
- cancel blocks (or clear+succeed path exercised): **PASS**

Machine JSON (no secrets):

```json
{
  "when_utc": "2026-07-21T15:31:23.689729+00:00",
  "env": {
    "AGENT_RUNTIME": "1",
    "SRE_AGENT": "1"
  },
  "note": "LOCAL real-engine canary only. NOT production. No secrets.",
  "pilots": [
    "arnav",
    "arya",
    "aryan",
    "diya",
    "hermes",
    "isha",
    "kabir",
    "kavya",
    "nikhil",
    "pranav",
    "vidya",
    "zara"
  ],
  "idempotency_key": "canary-local-pranav-20260721T153123Z",
  "cases": [
    {
      "label": "pranav_run_1",
      "status": "succeeded",
      "reason": "",
      "output_keys": [
        "check",
        "read_only",
        "result"
      ],
      "lifecycle": [
        "queued",
        "leased",
        "running",
        "succeeded"
      ],
      "agent_id": "pranav",
      "action": "run_owned_workflow",
      "output_safe": {
        "check": "sre",
        "read_only": true,
        "result_ok": null,
        "result_score": 53.3,
        "result_keys": [
          "actions",
          "agent",
          "kpis",
          "role",
          "score",
          "status",
          "summary",
          "ts"
        ]
      }
    },
    {
      "label": "pranav_run_2_same_idem",
      "status": "skipped",
      "reason": "duplicate_suppressed",
      "output_keys": null,
      "lifecycle": [
        "queued",
        "leased",
        "skipped"
      ],
      "agent_id": "pranav",
      "action": "run_owned_workflow"
    },
    {
      "label": "pranav_unknown_action",
      "status": "blocked",
      "reason": "capability_not_registered:totally_unknown_action_xyz",
      "output_keys": null,
      "lifecycle": [
        "queued",
        "blocked"
      ],
      "agent_id": "pranav",
      "action": "totally_unknown_action_xyz"
    },
    {
      "label": "swara_frozen",
      "status": "blocked",
      "reason": "red_lane_hard_off_mandate_required",
      "output_keys": null,
      "lifecycle": [
        "queued",
        "blocked"
      ],
      "agent_id": "swara",
      "action": "frozen_transfer_status"
    },
    {
      "label": "pranav_after_cancel",
      "status": "blocked",
      "reason": "cancel_requested",
      "output_keys": null,
      "lifecycle": [
        "queued",
        "blocked"
      ],
      "agent_id": "pranav",
      "action": "run_owned_workflow"
    },
    {
      "label": "pranav_after_clear_cancel",
      "status": "succeeded",
      "reason": "",
      "output_keys": [
        "check",
        "read_only",
        "result"
      ],
      "lifecycle": [
        "queued",
        "leased",
        "running",
        "succeeded"
      ],
      "agent_id": "pranav",
      "action": "run_owned_workflow",
      "output_safe": {
        "check": "sre",
        "read_only": true,
        "result_ok": null,
        "result_score": 53.3,
        "result_keys": [
          "actions",
          "agent",
          "kpis",
          "role",
          "score",
          "status",
          "summary",
          "ts"
        ]
      }
    }
  ],
  "cancel_request": {
    "ok": true,
    "agent_id": "pranav",
    "cancelled": true
  },
  "clear_cancel": {
    "ok": true,
    "agent_id": "pranav",
    "cancelled": false
  }
}
```
