"""
Conversation Flow Engine
A Dograh-inspired node-graph workflow engine for voice conversations.

Instead of a flat linear script, a conversation is modelled as a directed
graph of nodes (greeting -> questions -> conditional branches ->
transfer-to-human / end). Each node decides the agent's response text and,
based on the caller's utterance + detected intent, which node to go to next.

The engine reuses the project's LLMBrain (app.voice_agent.llm_brain) and
IntentDetector (app.voice_agent.intent_detector) when available, and degrades
gracefully to a pure rule-based path (using each node's transitions) if those
modules are missing or fail.

Usage example:
    from app.voice_agent.flow_builder import build_flow_for_niche
    from app.voice_agent.flow_engine import FlowRunner

    flow = build_flow_for_niche("solar_commercial")
    runner = FlowRunner()                 # LLM auto-detected, optional
    state = runner.start(flow)            # -> FlowState at start node

    # first turn: no user input yet, emits the greeting
    result = await runner.step(flow, state, user_input=None)
    print(result["agent_text"])

    # subsequent turns feed the caller's words back in
    result = await runner.step(flow, state, user_input="Yes, above 100kW")
    while not runner.is_complete(state):
        result = await runner.step(flow, state, user_input="...")
    print(state.captured, state.outcome)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover - logger should always import
    import logging

    logger = logging.getLogger(__name__)


# =============================================================================
# NODE / FLOW MODEL
# =============================================================================


class NodeType(Enum):
    """Types of nodes in a conversation flow graph."""

    GREETING = "greeting"  # opening line of the call
    QUESTION = "question"  # asks a qualification question, expects an answer
    CONDITION = "condition"  # branches based on captured signals (no caller text)
    CAPTURE = "capture"  # stores a piece of info (name/email/phone/etc.)
    TRANSFER = "transfer"  # hand off to a human / book a meeting
    MESSAGE = "message"  # speak a line, then move on
    END = "end"  # terminal node, call finishes


@dataclass
class FlowNode:
    """
    A single node in the conversation graph.

    Attributes:
        id:          Unique node identifier within a flow.
        type:        A NodeType describing the node's role.
        text:        The prompt/text the agent says (or LLM instruction).
        transitions: Mapping of condition-label -> next node id. Common
                     condition labels: "yes", "no", "interested",
                     "not_interested", "default". "default" is the fallback.
        metadata:    Free-form dict. Recognised keys:
                       - capture_field: qualification field name to store the
                         caller's answer under (QUESTION / CAPTURE nodes).
                       - expected_intent: intent that should advance the node.
                       - score: integer interest score contribution.
                       - condition_kind: how a CONDITION node evaluates
                         ("interest_score" is the built-in default).
    """

    id: str
    type: NodeType
    text: str = ""
    transitions: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def next_for(self, condition: str) -> str | None:
        """Return the next node id for a condition label, or the default."""
        if condition in self.transitions:
            return self.transitions[condition]
        return self.transitions.get("default")


@dataclass
class ConversationFlow:
    """
    A full conversation flow: a named graph of FlowNodes.

    Attributes:
        id:            Flow identifier (e.g. "flow_solar_commercial").
        name:          Human-readable name.
        nodes:         Mapping of node id -> FlowNode.
        start_node_id: Where the conversation begins.
    """

    id: str
    name: str
    nodes: dict[str, FlowNode] = field(default_factory=dict)
    start_node_id: str = ""

    def get_node(self, node_id: str | None) -> FlowNode | None:
        """Look up a node by id (None-safe)."""
        if not node_id:
            return None
        return self.nodes.get(node_id)

    def add_node(self, node: FlowNode) -> None:
        """Register a node in the flow."""
        self.nodes[node.id] = node

    def validate(self) -> list[str]:
        """
        Structural validation of the graph.

        Checks:
          - start node exists
          - every transition target points to a real node (no dangling)
          - at least one END node exists and is reachable from start
          - no orphan nodes (unreachable from start), start excluded

        Returns:
            A list of human-readable issue strings. Empty list == valid.
        """
        issues: list[str] = []

        if not self.nodes:
            issues.append("Flow has no nodes.")
            return issues

        if not self.start_node_id or self.start_node_id not in self.nodes:
            issues.append(f"Start node '{self.start_node_id}' is missing.")

        # Dangling transitions
        for node in self.nodes.values():
            for cond, target in node.transitions.items():
                if target not in self.nodes:
                    issues.append(
                        f"Node '{node.id}' has dangling transition "
                        f"'{cond}' -> '{target}' (no such node)."
                    )

        # Reachability via BFS from start
        reachable = set()
        if self.start_node_id in self.nodes:
            frontier = [self.start_node_id]
            while frontier:
                current = frontier.pop()
                if current in reachable:
                    continue
                reachable.add(current)
                node = self.nodes.get(current)
                if node:
                    for target in node.transitions.values():
                        if target in self.nodes and target not in reachable:
                            frontier.append(target)

        orphans = [nid for nid in self.nodes if nid not in reachable]
        for nid in orphans:
            issues.append(f"Node '{nid}' is unreachable from start (orphan).")

        # Reachable END node
        end_nodes = [n.id for n in self.nodes.values() if n.type == NodeType.END]
        if not end_nodes:
            issues.append("Flow has no END node.")
        elif not any(nid in reachable for nid in end_nodes):
            issues.append("No END node is reachable from start.")

        return issues

    def is_valid(self) -> bool:
        """Convenience boolean wrapper around validate()."""
        return len(self.validate()) == 0


# =============================================================================
# RUNTIME STATE
# =============================================================================


@dataclass
class FlowState:
    """
    Mutable runtime state for one conversation walking through a flow.

    Attributes:
        current_node_id: The node we are currently sitting on.
        captured:        Qualification answers + captured fields
                         (field_name -> value).
        history:         Ordered turn log; each entry is a dict with keys
                         role, content, node_id, intent, timestamp.
        finished:        True once an END/TRANSFER terminal is reached.
        outcome:         Final outcome label, e.g. "transfer", "ended",
                         "not_interested".
        interest_score:  Running interest/lead signal score (0..100-ish).
        meta:            Free-form scratch space.
    """

    current_node_id: str = ""
    captured: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    outcome: str | None = None
    interest_score: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def log(self, role: str, content: str, node_id: str, intent: str | None = None) -> None:
        """Append a turn to the history log."""
        self.history.append(
            {
                "role": role,
                "content": content,
                "node_id": node_id,
                "intent": intent,
                "timestamp": datetime.now().isoformat(),
            }
        )


# =============================================================================
# FLOW RUNNER
# =============================================================================

# Intent labels (from intent_detector) that signal negative / exit sentiment.
_NEGATIVE_INTENTS = {"not_interested", "opt_out"}
# Intent labels that signal a positive / advancing sentiment.
_POSITIVE_INTENTS = {"interested", "appointment_interest"}

# Cheap rule-based yes/no detection for the LLM-free fallback path.
_YES_WORDS = {
    "yes",
    "yeah",
    "yep",
    "haan",
    "ha",
    "ji",
    "sure",
    "ok",
    "okay",
    "of course",
    "definitely",
    "absolutely",
    "bilkul",
    "han",
}
_NO_WORDS = {"no", "nope", "nahi", "nahin", "not", "never", "na"}


class FlowRunner:
    """
    Executes a ConversationFlow one turn at a time.

    The runner is stateless with respect to a specific call: all per-call data
    lives in the FlowState you pass to step(). One FlowRunner can drive many
    concurrent conversations.

    LLM + intent detection are optional. If they are unavailable (import error
    or runtime error), the runner falls back to a deterministic rule-based
    walk using each node's transitions and simple keyword matching.
    """

    def __init__(self, llm_brain: Any | None = None, intent_detector: Any | None = None):
        """
        Args:
            llm_brain:        Optional pre-built LLMBrain instance. If None the
                              runner tries to lazily build one; if that fails it
                              stays in rule-based mode.
            intent_detector:  Optional IntentDetector. Same lazy/fallback rules.
        """
        self._llm = llm_brain
        self._llm_attempted = llm_brain is not None
        self._intent = intent_detector
        self._intent_attempted = intent_detector is not None
        logger.info("🕸️ FlowRunner initialized")

    # ----- public API ----------------------------------------------------

    def start(self, flow: ConversationFlow) -> FlowState:
        """Create a fresh FlowState positioned at the flow's start node."""
        return FlowState(current_node_id=flow.start_node_id)

    def is_complete(self, state: FlowState) -> bool:
        """True if the conversation has reached a terminal node."""
        return state.finished

    async def step(
        self,
        flow: ConversationFlow,
        state: FlowState,
        user_input: str | None = None,
    ) -> dict[str, Any]:
        """
        Advance the conversation by one turn.

        Given the current node and the caller's latest utterance, this:
          1. records the user turn (if any) + detects intent,
          2. captures qualification data for QUESTION/CAPTURE nodes,
          3. updates the interest score,
          4. picks the next node (CONDITION nodes branch automatically),
          5. produces the agent's response text for that next node.

        Args:
            flow:        The ConversationFlow being executed.
            state:       The mutable FlowState (modified in place).
            user_input:  The caller's latest words, or None for the very first
                         turn (just emits the greeting).

        Returns:
            A dict: {
                "agent_text": str,        # what the agent should say now
                "node_id": str,           # node we landed on
                "node_type": str,
                "intent": Optional[str],  # detected intent of user_input
                "finished": bool,
                "outcome": Optional[str],
            }
        """
        current = flow.get_node(state.current_node_id)
        if current is None:
            # Defensive: corrupt state -> finish gracefully.
            state.finished = True
            state.outcome = state.outcome or "error"
            return self._result("", state, None)

        intent: str | None = None

        # 1) Process the caller's utterance against the current node.
        if user_input:
            intent = await self._detect_intent(user_input)
            state.log("user", user_input, current.id, intent)
            self._capture(current, state, user_input)
            self._score(current, state, user_input, intent)

            # Decide where to go next from the *current* node.
            next_id = self._choose_next(current, state, user_input, intent)
        else:
            # First turn (no input): we stay on the start node and speak it.
            next_id = current.id if not state.history else current.id

        # 2) Advance the pointer (only if user actually responded, or first turn).
        if user_input:
            target = flow.get_node(next_id)
            # Auto-resolve any CONDITION nodes we pass through (no caller text).
            target, next_id = self._resolve_conditions(flow, target, state)
            if target is None:
                state.finished = True
                state.outcome = state.outcome or "ended"
                return self._result("", state, intent)
            state.current_node_id = target.id
            current = target

        # 3) Generate the agent's response for the node we now sit on.
        agent_text = await self._render(current, flow, state)
        state.log("assistant", agent_text, current.id, None)

        # 4) Terminal handling.
        if current.type == NodeType.END:
            state.finished = True
            state.outcome = state.outcome or current.metadata.get("outcome", "ended")
        elif current.type == NodeType.TRANSFER:
            state.finished = True
            state.outcome = state.outcome or "transfer"

        return self._result(agent_text, state, intent, current.type)

    # ----- internal: next-node selection ---------------------------------

    def _resolve_conditions(self, flow, node, state, _guard: int = 0):
        """
        Walk through any chain of CONDITION nodes automatically, since those
        branch on captured state rather than on caller speech. Returns the
        first non-CONDITION node (and its id) reached. Guarded against loops.
        """
        while node is not None and node.type == NodeType.CONDITION and _guard < 50:
            branch = self._eval_condition(node, state)
            nxt = node.next_for(branch)
            node = flow.get_node(nxt)
            _guard += 1
        return node, (node.id if node else None)

    def _eval_condition(self, node: FlowNode, state: FlowState) -> str:
        """
        Evaluate a CONDITION node and return its branch label.

        Built-in kind 'interest_score': compares state.interest_score against a
        threshold (metadata['threshold'], default 50) -> "hot" or "cold".
        Falls back to "default" for unknown kinds.
        """
        kind = node.metadata.get("condition_kind", "interest_score")
        if kind == "interest_score":
            threshold = node.metadata.get("threshold", 50)
            if state.interest_score >= threshold:
                return "hot"
            return "cold"
        return "default"

    def _choose_next(self, node, state, user_input, intent) -> str | None:
        """
        Pick the next node id from the current node given the caller's reply.

        Priority:
          1. Intent-based labels present in transitions
             (interested/not_interested/...).
          2. Yes/No keyword match (rule-based, LLM-free safe).
          3. Explicit "default" transition.
          4. If no transitions at all -> None (will end the call).
        """
        if not node.transitions:
            return None

        # Negative intent short-circuits to an exit branch if one exists.
        if intent in _NEGATIVE_INTENTS:
            for label in ("not_interested", "no", "end", "default"):
                if label in node.transitions:
                    return node.transitions[label]

        if intent in _POSITIVE_INTENTS:
            for label in ("interested", "yes", "default"):
                if label in node.transitions:
                    return node.transitions[label]

        # Yes/No keyword fallback.
        yn = self._yes_no(user_input)
        if yn == "yes" and "yes" in node.transitions:
            return node.transitions["yes"]
        if yn == "no" and "no" in node.transitions:
            return node.transitions["no"]

        # Intent label that exactly matches a transition key.
        if intent and intent in node.transitions:
            return node.transitions[intent]

        return node.transitions.get("default") or next(iter(node.transitions.values()))

    @staticmethod
    def _yes_no(text: str | None) -> str | None:
        """Very small rule-based yes/no classifier (Hinglish aware)."""
        if not text:
            return None
        words = {w.strip(".,!?").lower() for w in text.split()}
        if words & _NO_WORDS:
            return "no"
        if words & _YES_WORDS:
            return "yes"
        return None

    # ----- internal: capture + scoring -----------------------------------

    def _capture(self, node: FlowNode, state: FlowState, user_input: str) -> None:
        """Store the caller's answer under the node's capture_field, if set."""
        field_name = node.metadata.get("capture_field")
        if field_name and node.type in (NodeType.QUESTION, NodeType.CAPTURE):
            state.captured[field_name] = user_input.strip()

    def _score(self, node, state, user_input, intent) -> None:
        """
        Update the running interest score based on this turn.

        Signals:
          - explicit per-node score weight (metadata['score']) on a 'yes'
          - positive/negative intent
        """
        weight = node.metadata.get("score", 10)
        yn = self._yes_no(user_input)

        if intent in _POSITIVE_INTENTS:
            state.interest_score += 20
        if intent in _NEGATIVE_INTENTS:
            state.interest_score -= 25

        if node.type == NodeType.QUESTION:
            if yn == "yes":
                state.interest_score += weight
            elif yn == "no":
                state.interest_score -= max(5, weight // 2)

        state.interest_score = max(0, min(100, state.interest_score))

    # ----- internal: response rendering ----------------------------------

    async def _render(self, node, flow, state) -> str:
        """
        Produce the agent's spoken text for a node.

        Tries the LLM brain to phrase the node's `text` naturally given the
        captured context; on any failure falls back to the raw node text.
        """
        base = node.text or ""

        # CONDITION nodes have no speech of their own.
        if node.type == NodeType.CONDITION:
            return ""

        llm = self._get_llm()
        if llm is None or not base:
            return base

        try:
            captured_summary = (
                ", ".join(f"{k}={v}" for k, v in list(state.captured.items())[:6]) or "none yet"
            )
            prompt = (
                "You are a friendly B2B voice sales agent on a live call. "
                "Rephrase the following line so it sounds natural and "
                "conversational (Hinglish is fine). Keep it to 1-2 short "
                "sentences. Do NOT add explanations.\n\n"
                f'Line: "{base}"\n'
                f"Known so far: {captured_summary}\n\n"
                "Rephrased line:"
            )
            text = await llm._generate(prompt)
            text = (text or "").strip()
            return text or base
        except Exception as e:  # graceful degrade
            logger.warning(f"LLM render failed, using raw node text: {e}")
            return base

    # ----- internal: lazy LLM / intent acquisition -----------------------

    def _get_llm(self):
        """Lazily build an LLMBrain; cache failures so we don't retry forever."""
        if self._llm is not None:
            return self._llm
        if self._llm_attempted:
            return None
        self._llm_attempted = True
        try:
            from app.voice_agent.llm_brain import LLMBrain

            self._llm = LLMBrain()
            logger.info("🧠 FlowRunner attached LLMBrain")
        except Exception as e:
            logger.warning(f"LLMBrain unavailable, rule-based mode: {e}")
            self._llm = None
        return self._llm

    async def _detect_intent(self, text: str) -> str | None:
        """Detect intent via IntentDetector; fall back to keyword heuristics."""
        detector = self._get_intent()
        if detector is not None:
            try:
                result = await detector.detect(text)
                # DetectedIntent has .intent_type
                return getattr(result, "intent_type", None)
            except Exception as e:
                logger.warning(f"Intent detection failed, heuristic fallback: {e}")

        # Heuristic fallback.
        low = text.lower()
        if any(w in low for w in ("not interested", "nahi chahiye", "stop calling")):
            return "not_interested"
        yn = self._yes_no(text)
        if yn == "yes":
            return "interested"
        return "neutral"

    def _get_intent(self):
        """Lazily build an IntentDetector (no LLM fallback to stay light)."""
        if self._intent is not None:
            return self._intent
        if self._intent_attempted:
            return None
        self._intent_attempted = True
        try:
            from app.voice_agent.intent_detector import IntentDetector

            # use_llm_fallback=False keeps it fast + side-effect free here.
            self._intent = IntentDetector(use_llm_fallback=False)
            logger.info("🎯 FlowRunner attached IntentDetector")
        except Exception as e:
            logger.warning(f"IntentDetector unavailable, heuristics only: {e}")
            self._intent = None
        return self._intent

    # ----- internal: result helper ---------------------------------------

    @staticmethod
    def _result(agent_text, state, intent, node_type=None) -> dict[str, Any]:
        node_type_value = node_type.value if isinstance(node_type, NodeType) else node_type
        return {
            "agent_text": agent_text,
            "node_id": state.current_node_id,
            "node_type": node_type_value,
            "intent": intent,
            "finished": state.finished,
            "outcome": state.outcome,
            "interest_score": state.interest_score,
            "captured": dict(state.captured),
        }
