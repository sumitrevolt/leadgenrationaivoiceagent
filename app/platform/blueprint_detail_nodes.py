"""blueprint_detail_nodes.py — verified L1/L2 detail nodes.

A SPLIT SOURCE FILE, NOT A SECOND GRAPH. ``blueprint_graph`` imports
``DETAIL_NODES`` and appends it to the one canonical ``NODES`` registry, so IDs,
validators, traversal and the public whitelist all operate globally.

Every node here cleared the ``scripts/blueprint_derive.py`` evidence bar on
graph ``84b4d2f7``:

* reviewed domain ownership (``app/platform/blueprint_ownership.py``), plus
* at least one independent current-source signal (route / Celery task /
  scheduler membership / agent registry / feature-flag gate), and
* for critical domains, at least two non-AST signals in total.

Everything that did not clear the bar stayed ``REVIEW_REQUIRED`` — it is NOT
imported here. Status is ``CODE-PRESENT``: the source exists and is reachable,
which is all the evidence proves. Nothing is marked live, and harness controls
stay ``None`` unless independently proven.
"""

from __future__ import annotations

from typing import Any

# (id, title, layer, domain, type, status, files, desc, extra)
DETAIL_NODE_SPECS: list[tuple] = [
    (
        "detail_call_transfer",
        "Live human transfer",
        6,
        "voice_telephony",
        "engine",
        "CODE-PRESENT",
        ["app/telephony/call_transfer.py"],
        "Warm/cold transfer of a live call to a human. Gated by CALL_TRANSFER.",
        {
            "depth_level": 1,
            "legacy_node_id": "gap_transfer",
            "source_provenance": "legacy-migrated",
            "flags": ["CALL_TRANSFER"],
            "safety_lane": "RED",
        },
    ),
    (
        "detail_meter_watch",
        "Billing meter watch",
        7,
        "billing_payments",
        "engine",
        "CODE-PRESENT",
        ["app/billing/meter_watch.py", "app/billing/usage_alerts.py"],
        "Usage metering watchdog + threshold alerts; runs as a scheduled job.",
        {
            "depth_level": 1,
            "legacy_node_id": "meter_watch",
            "source_provenance": "legacy-migrated",
            "safety_lane": "AMBER",
        },
    ),
    (
        "detail_kb_rag",
        "RAG knowledge base",
        5,
        "kb_rag",
        "store",
        "CODE-PRESENT",
        ["app/voice_agent/knowledge_base.py"],
        "Qdrant-backed retrieval used to ground answers. Physically nested "
        "under app/voice_agent/ but owned by the RAG domain.",
        {
            "depth_level": 1,
            "legacy_node_id": "rag",
            "source_provenance": "legacy-migrated",
            "flags": ["KB_REPLACE_ON_RESEED", "KB_EMBED_LOAD_TIMEOUT_S", "KB_HNSW_EF"],
            "safety_lane": "GREEN",
        },
    ),
    (
        "detail_turnstile",
        "Cloudflare Turnstile",
        2,
        "security_compliance",
        "compliance",
        "CODE-PRESENT",
        ["app/security/turnstile.py"],
        "Bot/abuse challenge on public signup and lead-capture entry points.",
        {
            "depth_level": 1,
            "legacy_node_id": "turnstile",
            "source_provenance": "legacy-migrated",
            "safety_lane": "GREEN",
        },
    ),
    (
        "detail_stt_tts",
        "STT / TTS pipeline",
        6,
        "voice_telephony",
        "engine",
        "CODE-PRESENT",
        [
            "app/voice_agent/stt.py",
            "app/voice_agent/free_stt.py",
            "app/voice_agent/tts.py",
            "app/voice_agent/kokoro_tts.py",
            "app/voice_agent/llm_stream_tts.py",
        ],
        "Speech-to-text and text-to-speech providers behind the voice agent.",
        {
            # Domain-rooted L1. It was briefly modelled as L2 under
            # `voice_agent`, but `voice_agent` is an L0 curated aggregate —
            # parenting L2 directly onto L0 skips the L1 domain/flow layer and
            # makes progressive disclosure inconsistent. No independently
            # verified L1 voice-runtime group exists yet, and inventing one
            # purely to satisfy the validator would be fabrication, so this
            # stays L1 rooted on its domain until such a group is evidenced.
            "depth_level": 1,
            "legacy_node_id": "s_stttts",
            "source_provenance": "legacy-migrated",
            "flags": ["USE_LLM_STREAM_TTS", "ALLOW_MOCK_STT"],
            "safety_lane": "AMBER",
        },
    ),
    (
        "detail_agentic_rag",
        "Agentic / graph RAG",
        5,
        "kb_rag",
        "store",
        "CODE-PRESENT",
        ["app/agents/agentic_rag.py", "app/voice_agent/graph_rag.py"],
        "Multi-step agentic retrieval over the graph/vector knowledge base.",
        {
            # First genuine L2: hangs off the L1 group `detail_kb_rag` in the
            # SAME domain. Cleared the bar on graph 3ac33e3f with reviewed
            # exact-file ownership (graph_rag.py -> kb_rag) plus a feature-flag
            # signal, and a dominant kb_rag dependency neighbourhood (10 vs 2).
            "depth_level": 2,
            "parent_node_id": "detail_kb_rag",
            "legacy_node_id": "s_ragadv",
            "source_provenance": "legacy-migrated",
            "flags": ["AGENTIC_RAG_MIN_SCORE", "LIGHTRAG_DIR", "LIGHTRAG_EMBED_DIM"],
            "safety_lane": "GREEN",
        },
    ),
    # --- New canonical L1 detail (not legacy-migrated; CODE-PRESENT / inert) ---
    (
        "detail_sales_autopilot",
        "Sales Autopilot (canary)",
        3,
        "email_outreach",
        "engine",
        "CODE-PRESENT",
        [
            "app/platform/sales_autopilot/send.py",
            "app/api/sales_autopilot_admin.py",
            "app/platform/sales_autopilot/scheduler.py",
        ],
        "Allowlisted sales canary engine. Master flag OFF + RUN_DUE_EXCLUDE; "
        "not live until owner enables SALES_AUTOPILOT_ENABLED with dry-run.",
        {
            "depth_level": 1,
            "source_provenance": "canonical",
            "flags": [
                "SALES_AUTOPILOT_ENABLED",
                "SALES_AUTOPILOT_DRY_RUN",
                "SALES_AUTOPILOT_WHATSAPP_ENABLED",
                "SALES_AUTOPILOT_EMAIL_ENABLED",
            ],
            "safety_lane": "AMBER",
            "admin_links": ["/api/sales-autopilot/summary"],
        },
    ),
    (
        "detail_creative_os",
        "Creative Automation OS",
        3,
        "content_gen",
        "engine",
        "CODE-PRESENT",
        [
            "app/marketing/creative_os/service.py",
            "app/marketing/creative_os/brief.py",
            "app/marketing/creative_os/licence.py",
        ],
        "ADR-143 Creative OS — extends video_ad_cycle/Postiz; CREATIVE_OS_ENABLED "
        "defaults OFF; providers return provider_unavailable until provisioned.",
        {
            "depth_level": 1,
            "source_provenance": "canonical",
            "flags": [
                "CREATIVE_OS_ENABLED",
                "CREATIVE_GPU_LAB_ENABLED",
            ],
            "safety_lane": "RED",
        },
    ),
    (
        "detail_owner_email_canary",
        "Owner inbox email canary",
        3,
        "email_outreach",
        "engine",
        "CODE-PRESENT",
        [
            "app/api/owner_email_canary.py",
            "app/platform/owner_email_canary.py",
        ],
        "Super-admin one-shot owner-inbox email canary with preflight + ledger "
        "(PR #187). Not bulk outreach.",
        {
            "depth_level": 1,
            "source_provenance": "canonical",
            "safety_lane": "AMBER",
            "admin_links": [
                "/api/admin/owner-email-canary/preflight",
                "/api/admin/owner-email-canary/last",
            ],
        },
    ),
]


def build_detail_nodes(node_factory) -> list[dict[str, Any]]:
    """Materialise detail nodes through the canonical ``_n`` factory.

    Using the same factory is what keeps this a split file rather than a second
    schema: defaults, harness fields and hierarchy fields all come from one
    place.
    """
    out: list[dict[str, Any]] = []
    for nid, title, layer, domain, ntype, status, files, desc, extra in DETAIL_NODE_SPECS:
        extra = dict(extra)
        extra.setdefault("default_visibility", "collapsed")
        out.append(
            node_factory(nid, title, layer, domain, ntype, status, list(files), desc, **extra)
        )
    return out
