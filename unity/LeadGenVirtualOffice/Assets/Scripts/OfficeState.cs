// Presentation-state DTOs for the Blueprint Virtual Office.
// Source of truth: GET /api/platform/office/snapshot (docs/UNITY_OFFICE_API_CONTRACT.md §1).
// Pushed in by the web shell — Unity performs NO authenticated HTTP itself.
// RULE: no hard-coded customers/agents/counts anywhere in Unity (Phase 10).
using System;
using System.Collections.Generic;

namespace LeadGen.Office
{
    [Serializable] public class HostEvent
    {
        public string type;      // "state" | "customer_state" | "select" | "mode"
        public string origin;    // "host" | "unity" (loop guard)
        public string kind;      // for select: "room" | "agent" | "customer"
        public string id;
        public Snapshot snapshot;
        public CustomerState customer;
    }

    // ---- customer office DTO (tenant-scoped; produced by the CUSTOMER shell only) ----
    // Contains ONLY presentation fields from /api/customer/* endpoints. Never admin data,
    // never other tenants, never tokens/secrets (docs/UNITY_OFFICE_API_CONTRACT.md §2).
    [Serializable] public class CustomerState
    {
        public string business_name;      // display only
        public int setup_pct;
        public string plan_name;          // display label from packages-truth API
        public int approvals_pending;
        public string next_action;
        public string report_health;      // "green" | "yellow" | "red" | ""
        public List<Deliverable> deliverables = new();
        public List<SocialAccount> social = new();
    }

    [Serializable] public class Deliverable
    {
        public string id;        // opaque
        public string label;
        public string status;    // done|in_progress|waiting_customer|blocked|not_started
    }

    [Serializable] public class SocialAccount
    {
        public string platform;
        public string status;    // connected|provider_review_pending|not_connected
    }

    [Serializable] public class Snapshot
    {
        public List<Room> rooms = new();
        public List<Agent> agents = new();
        public List<PipelineStage> pipeline = new();
        public List<NextBestAction> next_best_actions = new();
    }

    [Serializable] public class Room
    {
        public string id;        // canonical office_hq ROOM_DEFS id — Unity adds NO ids
        public string label;
    }

    [Serializable] public class Agent
    {
        public string key;       // opaque stable id
        public string name;      // display name only
        public string room;
        public string status;    // working|waiting|reviewing|blocked|failed|offline (mapped)
        public string task;      // current task display text
    }

    [Serializable] public class PipelineStage
    {
        public string id;
        public string label;
        public int count;
        public string source;    // "real" | "partial" | "mock" — MUST be surfaced honestly
        public string note;
    }

    [Serializable] public class NextBestAction
    {
        public string title;
        public string text;
    }
}
