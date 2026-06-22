"""
Flow Builder
Auto-generates Dograh-style ConversationFlow graphs from niche configuration.

`build_flow_for_niche(niche_key)` turns a niche entry from app.niches.NICHES
into a ready-to-run conversation graph:

    GREETING  (uses pitch_hook + niche name)
        |
        v
    QUESTION  (one per qualification_question, each capturing its answer)
        |  ... chained ...
        v
    CONDITION (scores interest -> hot / cold)
       /        \\
   TRANSFER     END
   (hot lead)   (cold / polite close)

`build_flow_from_spec(spec)` builds a custom flow from a plain dict so callers
can hand-author graphs without importing the dataclasses directly.

Every returned flow is structurally valid (validate() -> []). If a niche key
is unknown, a safe generic flow is produced instead of raising.

Usage example:
    from app.voice_agent.flow_builder import build_flow_for_niche
    flow = build_flow_for_niche("dental_implants")
    assert flow.is_valid()
    print(flow.start_node_id, len(flow.nodes))
"""

from __future__ import annotations

from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

from app.voice_agent.flow_engine import (
    ConversationFlow,
    FlowNode,
    NodeType,
)

try:
    from app.niches import NICHES
except Exception as e:  # defensive: still usable for custom specs
    logger.warning(f"Could not import NICHES, niche flows limited: {e}")
    NICHES = {}


# =============================================================================
# NICHE -> FLOW
# =============================================================================


def build_flow_for_niche(niche_key: str) -> ConversationFlow:
    """
    Build a sensible ConversationFlow for a configured niche.

    Mapping of niche config -> graph nodes:
      - niche["name"] + niche["pitch_hook"]  -> the GREETING node text.
      - each string in niche["qualification_questions"] -> one QUESTION node,
        capturing the caller's answer under field "q1", "q2", ... and wired so
        a "no" jumps straight to the scoring CONDITION (early bail-out) while
        any other answer flows to the next question.
      - a CONDITION node scores interest (>= threshold == hot).
      - hot  -> TRANSFER node (hand to human / book demo).
      - cold -> END node (polite close).

    Args:
        niche_key: A key in app.niches.NICHES (e.g. "solar_commercial").

    Returns:
        A fully valid ConversationFlow. Unknown keys yield a generic flow.
    """
    niche = NICHES.get(niche_key)
    if not niche:
        logger.warning(f"Unknown niche '{niche_key}', building generic flow.")
        return _build_generic_flow(niche_key)

    name = niche.get("name", niche_key)
    pitch_hook = niche.get("pitch_hook") or f"help your {name} business get more qualified leads"
    questions = niche.get("qualification_questions") or []

    flow = ConversationFlow(
        id=f"flow_{niche_key}",
        name=f"{name} Qualification Flow",
        nodes={},
        start_node_id="greeting",
    )

    condition_id = "score_check"
    transfer_id = "transfer"
    end_id = "end"

    # --- Greeting -------------------------------------------------------
    first_target = "q1" if questions else condition_id
    greeting = FlowNode(
        id="greeting",
        type=NodeType.GREETING,
        text=(
            f"Hi, this is Maya calling from your AI sales team. "
            f"I work with {name} businesses to {pitch_hook}. "
            f"Do you have a quick minute?"
        ),
        transitions={
            "not_interested": end_id,
            "no": end_id,
            "default": first_target,
        },
        metadata={"niche": niche_key, "score": 5},
    )
    flow.add_node(greeting)

    # --- Question nodes (one per qualification question) ----------------
    for idx, question in enumerate(questions, start=1):
        qid = f"q{idx}"
        is_last = idx == len(questions)
        next_default = f"q{idx + 1}" if not is_last else condition_id
        node = FlowNode(
            id=qid,
            type=NodeType.QUESTION,
            text=question.strip(),
            transitions={
                # A clear "no" early-exits to scoring (still scored as a signal).
                "no": condition_id,
                "not_interested": end_id,
                "default": next_default,
            },
            metadata={
                "capture_field": qid,
                "question_text": question.strip(),
                "expected_intent": "interested",
                "score": 15,
            },
        )
        flow.add_node(node)

    # --- Condition: score the interest ----------------------------------
    condition = FlowNode(
        id=condition_id,
        type=NodeType.CONDITION,
        text="",
        transitions={
            "hot": transfer_id,
            "cold": end_id,
            "default": end_id,
        },
        metadata={"condition_kind": "interest_score", "threshold": 40},
    )
    flow.add_node(condition)

    # --- Transfer (hot lead) --------------------------------------------
    transfer = FlowNode(
        id=transfer_id,
        type=NodeType.TRANSFER,
        text=(
            "Great, you sound like a perfect fit! Let me connect you with our "
            "specialist to lock in a quick 15-minute demo. One moment please."
        ),
        transitions={"default": end_id},
        metadata={"outcome": "transfer", "action": "human_handoff"},
    )
    flow.add_node(transfer)

    # --- End (cold / polite close) --------------------------------------
    end = FlowNode(
        id=end_id,
        type=NodeType.END,
        text="No problem at all, thanks for your time. Have a great day!",
        transitions={},
        metadata={"outcome": "ended"},
    )
    flow.add_node(end)

    _warn_if_invalid(flow)
    return flow


# =============================================================================
# CUSTOM SPEC -> FLOW
# =============================================================================


def build_flow_from_spec(spec: dict[str, Any]) -> ConversationFlow:
    """
    Build a ConversationFlow from a plain dict spec (hand-authored flows).

    Expected spec shape:
        {
            "id": "my_flow",
            "name": "My Flow",
            "start": "greeting",                 # or "start_node_id"
            "nodes": [
                {
                    "id": "greeting",
                    "type": "greeting",          # NodeType value (str)
                    "text": "Hi there!",
                    "transitions": {"default": "ask"},
                    "metadata": {"score": 5}
                },
                {"id": "ask", "type": "question", "text": "...",
                 "transitions": {"default": "end"},
                 "metadata": {"capture_field": "q1"}},
                {"id": "end", "type": "end", "text": "Bye"}
            ]
        }

    Unknown node-type strings degrade to NodeType.MESSAGE. The result is NOT
    forced valid (so authoring mistakes are visible) — call flow.validate().

    Args:
        spec: The flow specification dict.

    Returns:
        A ConversationFlow assembled from the spec.
    """
    flow_id = spec.get("id", "custom_flow")
    name = spec.get("name", flow_id)
    start = spec.get("start") or spec.get("start_node_id") or ""

    flow = ConversationFlow(id=flow_id, name=name, nodes={}, start_node_id=start)

    for raw in spec.get("nodes", []):
        node_type = _coerce_node_type(raw.get("type"))
        node = FlowNode(
            id=raw["id"],
            type=node_type,
            text=raw.get("text", ""),
            transitions=dict(raw.get("transitions", {})),
            metadata=dict(raw.get("metadata", {})),
        )
        flow.add_node(node)

    # If no start was given, default to the first node we saw.
    if not flow.start_node_id and flow.nodes:
        flow.start_node_id = next(iter(flow.nodes))

    _warn_if_invalid(flow)
    return flow


# =============================================================================
# HELPERS
# =============================================================================


def _coerce_node_type(value: Any) -> NodeType:
    """Map a string/NodeType to a NodeType, defaulting to MESSAGE."""
    if isinstance(value, NodeType):
        return value
    if isinstance(value, str):
        try:
            return NodeType(value.lower())
        except ValueError:
            pass
    return NodeType.MESSAGE


def _build_generic_flow(label: str) -> ConversationFlow:
    """A minimal but valid fallback flow for unknown niches."""
    flow = ConversationFlow(
        id=f"flow_{label or 'generic'}",
        name="Generic Qualification Flow",
        nodes={},
        start_node_id="greeting",
    )
    flow.add_node(
        FlowNode(
            id="greeting",
            type=NodeType.GREETING,
            text="Hi, this is Maya from your AI sales team. Do you have a quick minute?",
            transitions={"not_interested": "end", "no": "end", "default": "q1"},
            metadata={"score": 5},
        )
    )
    flow.add_node(
        FlowNode(
            id="q1",
            type=NodeType.QUESTION,
            text="Are you currently looking to generate more qualified B2B leads?",
            transitions={"no": "score_check", "not_interested": "end", "default": "score_check"},
            metadata={"capture_field": "q1", "score": 20},
        )
    )
    flow.add_node(
        FlowNode(
            id="score_check",
            type=NodeType.CONDITION,
            text="",
            transitions={"hot": "transfer", "cold": "end", "default": "end"},
            metadata={"condition_kind": "interest_score", "threshold": 20},
        )
    )
    flow.add_node(
        FlowNode(
            id="transfer",
            type=NodeType.TRANSFER,
            text="Perfect, let me connect you with a specialist for a quick demo.",
            transitions={"default": "end"},
            metadata={"outcome": "transfer"},
        )
    )
    flow.add_node(
        FlowNode(
            id="end",
            type=NodeType.END,
            text="Thanks for your time, have a great day!",
            transitions={},
            metadata={"outcome": "ended"},
        )
    )
    _warn_if_invalid(flow)
    return flow


def _warn_if_invalid(flow: ConversationFlow) -> None:
    """Log (but never raise) if a generated flow has structural issues."""
    try:
        issues = flow.validate()
        if issues:
            logger.warning(f"Flow '{flow.id}' has {len(issues)} issue(s): {issues}")
        else:
            logger.info(f"✅ Flow '{flow.id}' built and validated ({len(flow.nodes)} nodes)")
    except Exception as e:
        logger.warning(f"Flow validation errored for '{flow.id}': {e}")
