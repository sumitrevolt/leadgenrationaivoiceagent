# =====================================================================
# INCIDENT KNOWLEDGE RECORD — template (Phase 9: learning loop)
# File: incidents/TEMPLATE.md
#
# Every meaningful incident creates/updates a record here. The goal:
# "The same failure should become easier to resolve the second time."
# Each record feeds: search/retrieval (knowledge_query.py) + runbook
# registry updates + freshness metadata.
# =====================================================================

incident_id: "INC-YYYY-NNN"          # sequential
date: "YYYY-MM-DDTHH:MM:SSZ"
impacted_service: "voice|infra|sales|video|agents|providers"
severity: "P0|P1|P2|P3"
status: "OPEN|MITIGATED|RESOLVED|POSTMORTEM_DONE"

# --- SYMPTOMS (what was observed) ---
symptoms:
  - "exact observable symptom 1"
  - "exact observable symptom 2"

# --- DETECTION ---
trigger: "what surfaced this (alert / health check / user report)"
detection_source: "Uptime/Gatus|Sentry issue id|call_health_check|owner report"

# --- ROOT CAUSE (evidence-backed, no causal claims without timestamps) ---
root_cause: "verified root cause"
root_cause_evidence:
  - "log line / error series END timestamp / diff sha (prove causation, ADR-097)"

# --- CORRECTIVE ACTION ---
corrective_action: "what fixed it"
corrective_files_changed: ["path1", "path2"]
tests_run: ["pytest target", "prod_check"]
rollback: "previous sha / revert path"

# --- FINAL EVIDENCE ---
final_evidence:
  - "health probe after fix"
  - "error series end timestamp"
  - "/health version"

# --- PREVENTION / LEARNING ---
prevention:
  - "guard added"
new_runbook: "RB-XXXX-NNN if new"
modified_runbook: "RB-XXXX-NNN if updated"
owner_decision: "any owner gate hit during incident"
decision_record: "ADR-XXX if recorded"

# --- FRESHNESS ---
created_at: "YYYY-MM-DDTHH:MM:SSZ"
updated_at: "YYYY-MM-DDTHH:MM:SSZ"
last_verified_at: "YYYY-MM-DDTHH:MM:SSZ"
validity: "verified|stale|superseded"
supersedes: ""
superseded_by: ""