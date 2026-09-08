"""
Flow QA / Linting
Pure-python quality analysis for ConversationFlow graphs and individual
prompts. No LLM or network calls — fast enough to run on every flow save.

`analyze_flow(flow)` returns a structured QA report: a list of issues (each
tagged severity) plus an overall quality score 0-100. It checks for missing
greeting, unreachable nodes, questions without a capture field, prompts that
are empty / too long / too vague, no end node, and no transfer (handoff) path.

`analyze_prompt(text)` scores a single prompt on length, clarity and whether
it contains a call-to-action.

Usage example:
    from app.voice_agent.flow_builder import build_flow_for_niche
    from app.voice_agent.qa_node import analyze_flow, analyze_prompt

    report = analyze_flow(build_flow_for_niche("hvac_commercial"))
    print(report["score"], report["passed"])
    for issue in report["issues"]:
        print(issue["severity"], issue["message"])

    print(analyze_prompt("Do you take AMC contracts for IT parks?"))
"""

from __future__ import annotations

from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

from app.voice_agent.flow_engine import ConversationFlow, FlowNode, NodeType

# Severity weights subtracted from the perfect score of 100.
_SEVERITY_PENALTY = {
    "error": 20,
    "warning": 8,
    "info": 2,
}

# Heuristics for prompt quality.
_MAX_PROMPT_WORDS = 45  # above this a spoken line is too long
_MIN_PROMPT_WORDS = 2  # below this it's basically empty
_VAGUE_WORDS = {
    "stuff",
    "things",
    "something",
    "etc",
    "whatever",
    "some",
    "various",
    "general",
    "anything",
}
_CTA_HINTS = {
    "?",
    "book",
    "schedule",
    "demo",
    "meeting",
    "call",
    "connect",
    "minute",
    "interested",
    "let me",
    "can you",
    "would you",
    "are you",
    "do you",
    "shall we",
}


# =============================================================================
# PROMPT-LEVEL ANALYSIS
# =============================================================================


def analyze_prompt(text: str) -> dict[str, Any]:
    """
    Score a single prompt/utterance for quality.

    Checks:
      - empty / too short
      - too long for a spoken line
      - vague filler words
      - presence of a call-to-action / question

    Args:
        text: The prompt text to evaluate.

    Returns:
        {
            "score": int 0-100,
            "word_count": int,
            "has_cta": bool,
            "issues": [str, ...],      # human-readable notes
        }
    """
    issues: list[str] = []
    text = (text or "").strip()
    words = text.split()
    word_count = len(words)

    score = 100

    if word_count == 0:
        issues.append("Prompt is empty.")
        return {"score": 0, "word_count": 0, "has_cta": False, "issues": issues}

    if word_count < _MIN_PROMPT_WORDS:
        issues.append("Prompt is too short to be meaningful.")
        score -= 30

    if word_count > _MAX_PROMPT_WORDS:
        issues.append(f"Prompt is long ({word_count} words); spoken lines should be concise.")
        score -= 20

    lowered = {w.strip(".,!?").lower() for w in words}
    vague_hits = lowered & _VAGUE_WORDS
    if vague_hits:
        issues.append(f"Prompt contains vague words: {', '.join(sorted(vague_hits))}.")
        score -= 10 * len(vague_hits)

    low_text = text.lower()
    has_cta = ("?" in text) or any(h in low_text for h in _CTA_HINTS)
    if not has_cta:
        issues.append("Prompt has no clear call-to-action or question.")
        score -= 15

    score = max(0, min(100, score))
    return {
        "score": score,
        "word_count": word_count,
        "has_cta": has_cta,
        "issues": issues,
    }


# =============================================================================
# FLOW-LEVEL ANALYSIS
# =============================================================================


def analyze_flow(flow: ConversationFlow) -> dict[str, Any]:
    """
    Run a full QA pass over a ConversationFlow.

    Aggregates structural checks (reused from flow.validate(): orphans,
    dangling transitions, missing/unreachable end) with content checks:
      - missing greeting node
      - no transfer/handoff path (warning — many flows want one)
      - QUESTION nodes lacking a capture_field
      - per-node prompt quality (empty/long/vague) via analyze_prompt

    Args:
        flow: The ConversationFlow to inspect.

    Returns:
        {
            "score": int 0-100,
            "passed": bool,            # True if no 'error' severity issues
            "node_count": int,
            "issues": [
                {"severity": "error|warning|info",
                 "node_id": str|None,
                 "message": str},
                ...
            ],
        }
    """
    issues: list[dict[str, Any]] = []

    if flow is None or not getattr(flow, "nodes", None):
        return {
            "score": 0,
            "passed": False,
            "node_count": 0,
            "issues": [{"severity": "error", "node_id": None, "message": "Flow is empty or None."}],
        }

    nodes = flow.nodes

    # --- Structural issues from the engine's own validator (errors) ------
    try:
        for msg in flow.validate():
            issues.append({"severity": "error", "node_id": None, "message": msg})
    except Exception as e:
        issues.append(
            {"severity": "error", "node_id": None, "message": f"Structural validation crashed: {e}"}
        )

    # --- Greeting presence ----------------------------------------------
    greetings = [n for n in nodes.values() if n.type == NodeType.GREETING]
    if not greetings:
        issues.append(
            {
                "severity": "warning",
                "node_id": None,
                "message": "Flow has no GREETING node; calls open abruptly.",
            }
        )

    # --- Transfer / handoff path ----------------------------------------
    transfers = [n for n in nodes.values() if n.type == NodeType.TRANSFER]
    if not transfers:
        issues.append(
            {
                "severity": "warning",
                "node_id": None,
                "message": "Flow has no TRANSFER node; hot leads cannot be handed off.",
            }
        )

    # --- End node presence (also covered structurally, kept as info) ----
    ends = [n for n in nodes.values() if n.type == NodeType.END]
    if not ends:
        issues.append({"severity": "error", "node_id": None, "message": "Flow has no END node."})

    # --- Per-node checks -------------------------------------------------
    for node in nodes.values():
        _analyze_node(node, issues)

    # --- Score ----------------------------------------------------------
    score = 100
    for issue in issues:
        score -= _SEVERITY_PENALTY.get(issue["severity"], 5)
    score = max(0, min(100, score))

    passed = not any(i["severity"] == "error" for i in issues)

    logger.info(
        f"🧪 QA flow '{getattr(flow, 'id', '?')}': score={score} "
        f"passed={passed} issues={len(issues)}"
    )

    return {
        "score": score,
        "passed": passed,
        "node_count": len(nodes),
        "issues": issues,
    }


def _analyze_node(node: FlowNode, issues: list[dict[str, Any]]) -> None:
    """Append content-quality issues for a single node."""
    # CONDITION nodes legitimately have no spoken text — skip prompt checks.
    if node.type == NodeType.CONDITION:
        if not node.transitions:
            issues.append(
                {
                    "severity": "warning",
                    "node_id": node.id,
                    "message": "CONDITION node has no branches.",
                }
            )
        return

    # QUESTION nodes must capture their answer.
    if node.type == NodeType.QUESTION and not node.metadata.get("capture_field"):
        issues.append(
            {
                "severity": "warning",
                "node_id": node.id,
                "message": "QUESTION node has no capture_field; the answer is lost.",
            }
        )

    # Prompt quality for any speaking node.
    if node.type != NodeType.END or node.text:
        prompt_report = analyze_prompt(node.text)
        if not node.text.strip():
            if node.type in (
                NodeType.GREETING,
                NodeType.QUESTION,
                NodeType.MESSAGE,
                NodeType.TRANSFER,
            ):
                issues.append(
                    {
                        "severity": "error",
                        "node_id": node.id,
                        "message": f"{node.type.value.upper()} node has empty prompt.",
                    }
                )
        else:
            for note in prompt_report["issues"]:
                # Map a couple of prompt notes to friendlier severities.
                severity = "info"
                if "empty" in note.lower():
                    severity = "error"
                elif "long" in note.lower() or "no clear call-to-action" in note.lower():
                    severity = "warning"
                issues.append({"severity": severity, "node_id": node.id, "message": note})

    # Non-terminal nodes should be able to go somewhere.
    if node.type not in (NodeType.END,) and not node.transitions:
        issues.append(
            {
                "severity": "warning",
                "node_id": node.id,
                "message": f"Node '{node.id}' is a dead end (no transitions).",
            }
        )
