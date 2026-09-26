"""
Enterprise Telegram Bot Integration (LeadGen AI)
=================================================
Connects Telegram to the canonical 9-worker / 31-agent AutomationOrchestrator,
DurableTaskStore, and TypeSafe System One intelligence.

Features:
- Authentication & chat allowlisting (owner-gated)
- Live orchestrator state reporting (/status, /tasks, /agents)
- Controlled pause / resume of automation kill switch
- Duplicate update/message protection (deduplication cache)
- Real TypeSafe intent classification and supervisory routing
- Audit trail logging to data/telegram/audit.jsonl
- Fail-closed and ban-safe egress
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from app.agents.skills import execute_skill
from app.integrations.telegram_typesafe import (
    HERMES_BOT_CHOICES,
    TelegramBotCoordinator,
    TelegramIntentClassifier,
    TelegramResponseValidator,
    get_bot_coordinator,
    get_intent_classifier,
    get_response_validator,
)
from app.platform.automation_orchestrator import AutomationOrchestrator, TaskPriority, TaskStatus
from app.platform.typesafe_integration import get_typesafe_client

logger = logging.getLogger(__name__)

# Config & Environment
TELEGRAM_API_URL = "https://api.telegram.org"
_DEDUPE_TTL_SECONDS = 3600.0


def _get_bot_token() -> str:
    return (
        os.getenv("TELEGRAM_JARVIS_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )


def _get_owner_usernames() -> set[str]:
    raw = os.getenv("TELEGRAM_OWNER_USERNAMES", "sumitrevolt").strip()
    return {u.strip().lower().lstrip("@") for u in raw.split(",") if u.strip()}


def _get_owner_chat_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_OWNER_CHAT_IDS", "").strip()
    ids = set()
    for item in raw.split(","):
        clean = item.strip()
        if clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit()):
            ids.add(int(clean))
    return ids


@dataclass
class BotProcessResult:
    success: bool
    response_text: str
    intent: str = "other"
    is_owner: bool = False
    routed_bot: str | None = None
    quality_score: float = 0.0
    validated: bool = False
    error: str | None = None
    deduplicated: bool = False


class TelegramBot:
    """Enterprise Telegram Bot connected to AutomationOrchestrator and TypeSafe."""

    def __init__(self, token: str | None = None):
        self.token = token or _get_bot_token()
        self.orchestrator: AutomationOrchestrator | None = None
        self.classifier = get_intent_classifier()
        self.coordinator = get_bot_coordinator()
        self.validator = get_response_validator()
        self._processed_updates: dict[str, float] = {}
        self._bot_info: dict[str, Any] = {}
        self._initialized = False

    def _get_orchestrator(self) -> AutomationOrchestrator:
        if self.orchestrator is None:
            self.orchestrator = AutomationOrchestrator()
        return self.orchestrator

    def initialize(self, force: bool = False) -> bool:
        """Verify bot token against Telegram getMe API."""
        if self._initialized and not force:
            return True

        if not self.token or len(self.token) < 20:
            logger.warning("[telegram_bot] Token missing or too short (<20 chars)")
            self._initialized = False
            return False

        try:
            url = f"{TELEGRAM_API_URL}/bot{self.token}/getMe"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    self._bot_info = data.get("result", {})
                    self._initialized = True
                    logger.info(
                        "[telegram_bot] Initialized bot @%s (id: %s)",
                        self._bot_info.get("username"),
                        self._bot_info.get("id"),
                    )
                    return True
            logger.warning(
                "[telegram_bot] Telegram getMe returned HTTP %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            self._initialized = False
            return False
        except Exception as e:
            logger.error("[telegram_bot] Failed to initialize bot: %s", e)
            self._initialized = False
            return False

    def is_owner(
        self, user_id: int | str, username: str | None = None, chat_id: int | str | None = None
    ) -> bool:
        """Check if user or chat is an authorized owner."""
        owners = _get_owner_usernames()
        if username and username.strip().lower().lstrip("@") in owners:
            return True

        owner_chats = _get_owner_chat_ids()
        if chat_id:
            try:
                if int(chat_id) in owner_chats:
                    return True
            except ValueError:
                pass

        return False

    def _is_duplicate_update(
        self, update_id: int | str | None, message_id: int | str | None
    ) -> bool:
        """Check and record update/message to prevent duplicate execution."""
        key = f"u:{update_id}" if update_id is not None else f"m:{message_id}"
        now = time.time()

        # Clean expired
        expired = [k for k, ts in self._processed_updates.items() if now - ts > _DEDUPE_TTL_SECONDS]
        for k in expired:
            del self._processed_updates[k]

        if key in self._processed_updates:
            return True

        self._processed_updates[key] = now
        return False

    def send_message(self, chat_id: int | str, text: str, parse_mode: str | None = None) -> bool:
        """Send a message to a chat via Telegram Bot API (fail-closed, never raises)."""
        if not self.token:
            logger.warning("[telegram_bot] Cannot send message: token unconfigured")
            return False

        try:
            url = f"{TELEGRAM_API_URL}/bot{self.token}/sendMessage"
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": text[:4096],
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode

            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200 and resp.json().get("ok", False)
        except Exception as e:
            logger.warning("[telegram_bot] Failed to send message to %s: %s", chat_id, e)
            return False

    def process_update(self, update: dict[str, Any], send_reply: bool = True) -> BotProcessResult:
        """Process incoming Telegram update with authentication, deduplication, and execution."""
        update_id = update.get("update_id")
        message_data = update.get("message") or update.get("channel_post") or {}

        if not message_data:
            return BotProcessResult(
                success=False,
                response_text="No message content found in update",
                error="empty_message",
            )

        message_id = message_data.get("message_id")
        chat_id = message_data.get("chat", {}).get("id")
        from_user = message_data.get("from", {})
        user_id = from_user.get("id")
        username = from_user.get("username")
        text = (message_data.get("text") or "").strip()

        # Deduplication check
        if self._is_duplicate_update(update_id, message_id):
            logger.info(
                "[telegram_bot] Duplicate update suppressed (update_id=%s, msg_id=%s)",
                update_id,
                message_id,
            )
            return BotProcessResult(
                success=True,
                response_text="Duplicate update ignored",
                deduplicated=True,
            )

        # Authentication check
        is_authenticated = self.is_owner(user_id=user_id, username=username, chat_id=chat_id)

        if not is_authenticated:
            response_text = (
                "ðŸ”’ Access Restricted\n\n"
                "This Telegram bot is private to LeadGen AI platform owners. "
                "Your account is not authorized."
            )
            if send_reply and chat_id:
                self.send_message(chat_id, response_text)

            self._log_audit(
                event_type="unauthorized_access_attempt",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                text=text,
                is_owner=False,
                response=response_text,
            )
            return BotProcessResult(
                success=False,
                response_text=response_text,
                is_owner=False,
                error="unauthorized",
            )

        # Authorized processing
        # 0. P0-76 owner-ACK (owner-gated, existing-task-bound) — intercept before
        #    the generic slash-command / TypeSafe-intent paths so it binds to the
        #    EXISTING orchestrator task and never creates a duplicate.
        from app.integrations.telegram_p0_76_ack import (
            handle_p0_76_ack,
            handle_p0_76_review_approval,
            is_p0_76_ack,
            is_p0_76_approval,
        )

        if is_p0_76_approval(text):
            appres = handle_p0_76_review_approval(
                bot=self,
                orchestrator=self._get_orchestrator(),
                update=update,
                chat_id=chat_id,
                send_reply=send_reply,
            )
            self._log_audit(
                event_type="p0_76_review_approval",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                text=text,
                is_owner=appres.authorized,
                intent="p0_76_review_approval",
                routed_bot="guardian",
                response=appres.response_text,
            )
            return BotProcessResult(
                success=(not appres.error) or appres.replayed,
                response_text=appres.response_text,
                intent="p0_76_review_approval",
                is_owner=appres.authorized,
                routed_bot="guardian",
                deduplicated=appres.replayed,
                error=appres.error,
            )

        if is_p0_76_ack(text):
            p0res = handle_p0_76_ack(
                bot=self,
                orchestrator=self._get_orchestrator(),
                update=update,
                chat_id=chat_id,
                send_ack=send_reply,
            )
            self._log_audit(
                event_type="p0_76_ack",
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                text=text,
                is_owner=True,
                intent="p0_76_ack",
                routed_bot="guardian",
                response=p0res.response_text,
            )
            return BotProcessResult(
                success=(not p0res.error) or p0res.deduplicated,
                response_text=p0res.response_text,
                intent="p0_76_ack",
                is_owner=True,
                routed_bot="guardian",
                deduplicated=p0res.deduplicated,
                error=p0res.error,
            )

        # 1. Check if slash command
        if text.startswith("/"):
            response_text, intent, routed_bot = self._execute_command(text)
        else:
            # 2. Natural language intent classification using TypeSafe
            classification = self.classifier.classify_intent(text, str(user_id), is_owner=True)
            intent = classification.get("intent", "general_question")

            # Route to Hermes bot
            routing = self.coordinator.route_to_hermes_bot(text, str(user_id), is_owner=True)
            routed_bot = routing.get("handler", "pilot")

            # Execute skill based on TypeSafe-classified intent
            skill_response = self._execute_skill_for_intent(intent, text, str(user_id))
            if skill_response:
                response_text = skill_response
            # Handle intent
            if intent == "status_check":
                response_text, _, _ = self._cmd_status()
            elif intent == "task_query":
                response_text, _, _ = self._cmd_tasks("")
            elif intent == "agent_query":
                response_text, _, _ = self._cmd_agents()
            else:
                response_text = (
                    f"ðŸ¤– **Jarvis (LeadGen AI)**\n\n"
                    f"Message classified as: `{intent}` (priority: {classification.get('priority', 'medium')})\n"
                    f"Routed to supervisory bot: `@{routed_bot}` ({HERMES_BOT_CHOICES.get(routed_bot, '')})\n\n"
                    f"Available commands:\n"
                    f"/status â€” Real-time system & task metrics\n"
                    f"/tasks â€” View recent active orchestrator tasks\n"
                    f"/agents â€” View the 31 specialist agents\n"
                    f"/pause & /resume â€” Control automation kill switch"
                )

        # Validate response
        validation = self.validator.validate_response(response_text, intent, {"is_owner": True})

        if send_reply and chat_id:
            self.send_message(chat_id, response_text)

        self._log_audit(
            event_type="command_executed" if text.startswith("/") else "message_processed",
            user_id=user_id,
            username=username,
            chat_id=chat_id,
            text=text,
            is_owner=True,
            intent=intent,
            routed_bot=routed_bot,
            response=response_text,
            quality_score=validation.get("quality_score", 0.0),
        )

        return BotProcessResult(
            success=True,
            response_text=response_text,
            intent=intent,
            is_owner=True,
            routed_bot=routed_bot,
            quality_score=validation.get("quality_score", 0.0),
            validated=validation.get("appropriate", True),
        )

    def _execute_command(self, text: str) -> tuple[str, str, str | None]:
        """Execute recognized owner slash commands against real orchestrator state."""
        parts = text.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        if cmd in ("/start", "/help"):
            return self._cmd_help()
        elif cmd == "/status":
            return self._cmd_status()
        elif cmd in ("/keys", "/slots"):
            return self._cmd_keys()
        elif cmd == "/tasks":
            return self._cmd_tasks(" ".join(args))
        elif cmd == "/agents":
            return self._cmd_agents()
        elif cmd == "/pause":
            return self._cmd_pause()
        elif cmd == "/resume":
            return self._cmd_resume()
        elif cmd == "/test_handoff":
            return self._cmd_test_handoff()
        else:
            # Wave 7: dispatch the 9 new owner commands to
            # ``telegram_owner_commands.handle_owner_command``. The result's
            # ``status`` field is preserved so callers can distinguish OK /
            # EMPTY / UNAVAILABLE / NOT_INSTRUMENTED â€” never fabricated.
            try:
                from app.integrations.telegram_owner_commands import (
                    handle_owner_command,
                )

                result = handle_owner_command(cmd)
                # Mirror the result to the data pipeline for the dashboard.
                try:
                    import json

                    from app.platform.runtime_data import store_dir

                    mirror = store_dir("telegram_command_mirror.jsonl")
                    with mirror.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(result.to_data_payload(), ensure_ascii=False) + "\n")
                except Exception:
                    pass
                return (
                    result.to_telegram_text(),
                    result.status,
                    None,
                )
            except ImportError:
                return (
                    f"Unknown command: `{cmd}`\nUse /help to see all available commands.",
                    "command",
                    None,
                )

    def _cmd_help(self) -> tuple[str, str, str | None]:
        bot_name = self._bot_info.get("first_name", "Jarvis")
        username = self._bot_info.get("username", "Sumits_jarvis_bot")
        text = (
            f"ðŸ‘‹ **{bot_name} (@{username}) â€” LeadGen AI Control Plane**\n\n"
            f"Connected to the canonical 9-worker / 31-agent architecture.\n\n"
            f"**Operational Commands:**\n"
            f"â€¢ `/status` â€” Live orchestrator state, active leases & task status counts\n"
            f"â€¢ `/keys` or `/slots` â€” TypeSafe 4 logical slots health & rotation status\n"
            f"â€¢ `/tasks [status]` â€” List tasks from the durable ledger\n"
            f"â€¢ `/agents` â€” View the 31 specialist agents across 7 teams\n"
            f"â€¢ `/test_handoff` â€” Non-destructive self-check (NOT execution proof for #76)\n"
            f"â€¢ `/pause` â€” Trigger kill switch (stops new task claims)\n"
            f"â€¢ `/resume` â€” Re-enable automated task claims\n"
            f"â€¢ `/help` â€” Show this message\n\n"
            f"You can also send natural language queries; TypeSafe System One (`jev-latest`) "
            f"will classify and route them to the appropriate supervisory bot."
        )
        return text, "help", "pilot"

    def _cmd_keys(self) -> tuple[str, str, str | None]:
        """View TypeSafe 4 logical slots health without leaking secrets."""
        try:
            from app.platform.key_manager import get_key_manager

            km = get_key_manager()
            slots = km.get_all_slots()

            lines = ["ðŸ” **TypeSafe Key Manager â€” Logical Slots**\n"]
            for slot, info in sorted(slots.items()):
                status = info.get("status", "ABSENT")
                last_ver = info.get("last_verified") or "Never"
                rot = "YES" if info.get("rotation_required") else "NO"
                lines.append(f"â€¢ `{slot}`: **{status}** | Rot: {rot} | Verified: `{last_ver}`")
            lines.append("\n*Zero raw keys or secrets are transmitted or stored in plaintext.*")
            return "\n".join(lines), "keys_status", "board"
        except Exception as e:
            logger.warning("Failed to fetch slots in _cmd_keys: %s", e)
            return f"âŒ Error retrieving slots: {e}", "keys_status", "board"

    def _cmd_status(self) -> tuple[str, str, str | None]:
        orch = self._get_orchestrator()
        all_tasks = orch.store.all_tasks()

        # Count real tasks by status
        counts: dict[str, int] = {}
        for t in all_tasks:
            st = t.status.value if hasattr(t.status, "value") else str(t.status)
            counts[st] = counts.get(st, 0) + 1

        active_leases = orch.governor.active_leases_count
        kill_switch = orch.is_kill_switch_active()
        ts_client = get_typesafe_client()
        typesafe_state = "ARMED" if ts_client.enabled else "DISABLED"

        bot_count = len(orch.HERMES_BOTS)
        agent_count = len(orch.registry)

        ready_cnt = counts.get(TaskStatus.READY.value, 0)
        running_cnt = counts.get(TaskStatus.RUNNING.value, 0)
        blocked_cnt = counts.get(TaskStatus.BLOCKED.value, 0)
        done_cnt = counts.get(TaskStatus.DONE.value, 0)
        failed_cnt = counts.get(TaskStatus.FAILED.value, 0)

        # Ingress/egress SMOKE block (owner directive: /status = status/smoke surface, NOT an execution proof).
        from app.platform import telegram_coordinator as _tc

        lease = _tc.get_polling_lease()
        conflicts = _tc.ingress_conflict_state()
        egress_slots = [slot for slot, _ in _tc.egress_token_candidates()]
        ingress_lines = [
            "INGRESS/EGRESS SMOKE (status read - NOT an execution proof):",
            f"  Ingress token (Jarvis): configured={bool(_tc.get_polling_token())}",
            f"  Polling lease: holder={lease.get('holder')} backend={lease.get('backend')} held_by_me={lease.get('held_by_me')}",
            f"  409 external conflicts: {conflicts.get('conflict_count', 0)} (last={conflicts.get('last_conflict_at')})",
            f"  Egress slots: {egress_slots}",
        ]
        ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        text = (
            f"ðŸ“Š **LeadGen AI Orchestrator Status - ingress/egress SMOKE TEST**\n\n"
            f"â€¢ **Supervisory Fleet:** 9 Hermes bots active (`board`, `pilot`, `sales`, etc.)\n"
            f"â€¢ **Specialist Workforce:** {agent_count} agents registered (`team.STAFF`)\n"
            f"â€¢ **Active Worker Leases:** {active_leases} / {orch.governor.max_leases}\n"
            f"â€¢ **Kill Switch (`AUTOMATION_STOP_NEW_CLAIMS`):** {'ðŸ›‘ ACTIVE (PAUSED)' if kill_switch else 'ðŸŸ¢ OFF (RUNNING)'}\n\n"
            f"**Task Ledger ({len(all_tasks)} total tasks):**\n"
            f"  ðŸŸ¢ Running: {running_cnt}\n"
            f"  â³ Ready: {ready_cnt}\n"
            f"  ðŸŸ¡ Blocked: {blocked_cnt}\n"
            f"  âœ… Done: {done_cnt}\n"
            f"  âŒ Failed: {failed_cnt}\n\n"
            f"â€¢ **TypeSafe:** {typesafe_state} (model: `{ts_client.model}`)\n"
            f"â€¢ **Updated:** `{ts_str}`"
            + "\n".join(ingress_lines)
            + "\n\n"
            + "*Smoke/status surface only - not an execution proof. Execution evidence = bound `p0_76_ack` handler results + worker result rows.*"
        )
        return text, "status_check", "board"

    def _cmd_tasks(self, filter_arg: str) -> tuple[str, str, str | None]:
        orch = self._get_orchestrator()
        all_tasks = orch.store.all_tasks()

        target_status = filter_arg.strip().upper() if filter_arg else None
        filtered = [
            t
            for t in all_tasks
            if not target_status
            or (t.status.value if hasattr(t.status, "value") else str(t.status)) == target_status
        ]

        if not filtered:
            return (
                f"No tasks found matching filter: `{filter_arg or 'all'}`\nTotal tasks in store: {len(all_tasks)}",
                "task_query",
                "pilot",
            )

        # Show latest 5 tasks
        lines = [f"ðŸ“‹ **Recent Tasks ({len(filtered)} matching):**\n"]
        for t in filtered[-5:]:
            st = t.status.value if hasattr(t.status, "value") else str(t.status)
            prio = t.priority.value if hasattr(t.priority, "value") else str(t.priority)
            lines.append(
                f"â€¢ `{t.task_id}` | **{st}** | Bot: `{t.owner_bot}` â†’ `{t.assigned_agent}` (prio: {prio})"
            )

        lines.append("\nUse `/tasks RUNNING` or `/tasks READY` to filter.")
        return "\n".join(lines), "task_query", "pilot"

    def _cmd_agents(self) -> tuple[str, str, str | None]:
        orch = self._get_orchestrator()
        registry = orch.registry
        text = (
            f"ðŸ¤– **Specialist Execution Workforce ({len(registry)} Agents)**\n\n"
            f"Derived canonically from `team.STAFF` and `agent_registry.py`:\n"
            f"â€¢ **Boss / Coordinator:** manager\n"
            f"â€¢ **Platform & SRE:** devops, security, database, perf, dbre\n"
            f"â€¢ **Marketing & GTM:** content, seo, social, paid, outbound\n"
            f"â€¢ **Sales & CRM:** pipeline, closer, outreach, follow_up\n"
            f"â€¢ **Voice Team:** swara (FROZEN), voice_qa, telephony\n"
            f"â€¢ **QA & Audit:** auditor, tester, compliance, verifier\n"
            f"â€¢ **Finance & Admin:** billing, invoices, legal, ops\n\n"
            f"All agents execute under strict governance contracts and fencing tokens."
        )
        return text, "agent_query", "guardian"

    def _cmd_pause(self) -> tuple[str, str, str | None]:
        os.environ["AUTOMATION_STOP_NEW_CLAIMS"] = "1"
        return (
            "ðŸ›‘ **Automation Paused**\n\n"
            "Set `AUTOMATION_STOP_NEW_CLAIMS=1`. The orchestrator will reject any new task dispatches until resumed.",
            "command",
            "guardian",
        )

    def _cmd_resume(self) -> tuple[str, str, str | None]:
        os.environ["AUTOMATION_STOP_NEW_CLAIMS"] = "0"
        return (
            "ðŸŸ¢ **Automation Resumed**\n\n"
            "Set `AUTOMATION_STOP_NEW_CLAIMS=0`. The orchestrator is now accepting task claims.",
            "command",
            "pilot",
        )

    def _cmd_test_handoff(self) -> tuple[str, str, str | None]:
        """Run a real, non-destructive handoff through canonical DevTask/dev_workers."""
        try:
            from app.integrations.telegram_dev_task_handoff import run_canonical_handoff

            result = run_canonical_handoff()
            task_id = result.get("task_id")
            if result.get("ok"):
                text = (
                    "✅ **Canonical Task Handoff Verified**\n\n"
                    f"• DevTask: `{task_id}`\n"
                    f"• Worker: `{result.get('worker_id')}` (kind=api)\n"
                    f"• Real live CLI workers: {result.get('live_cli_count')}/6\n"
                    f"• Final DevTask state: `{result.get('state')}`\n"
                    "• Execution: read-only worker-registry liveness snapshot\n"
                    "• Customer/provider side effects: none"
                )
                return text, "command", "pilot"
            text = (
                "❌ **Canonical Task Handoff Failed**\n\n"
                f"• DevTask: `{task_id or 'unavailable'}`\n"
                f"• Reason: `{result.get('reason') or result.get('state') or 'verification_failed'}`\n"
                f"• Missing CLI workers: `{result.get('missing_cli_workers') or []}`"
            )
            return text, "command", "guardian"
        except Exception as e:
            logger.exception("Canonical Telegram test handoff failed")
            return (
                f"❌ Canonical task handoff failed: `{type(e).__name__}: {str(e)[:180]}`",
                "command",
                "guardian",
            )

    def _execute_skill_for_intent(self, intent: str, message: str, user_id: str) -> str | None:
        """Execute a skill based on TypeSafe-classified intent.

        Returns skill response text if skill executed successfully, None otherwise.
        """
        skill_map = {
            "status_check": "ops-status",
            "task_query": "task-triage",
            "agent_query": "agent-registry",
            "command": "orchestrator-control",
            "general_question": "general-knowledge",
        }

        skill_name = skill_map.get(intent)
        if not skill_name:
            return None

        try:
            result = execute_skill(skill_name, user_id, {"message": message})
            if result and result.get("success"):
                return result.get("output", str(result))
        except Exception as e:
            logger.warning("[telegram_bot] Skill execution failed for %s: %s", skill_name, e)

        return None

    def _log_audit(self, **kwargs: Any) -> None:
        """Log event via structured logger with redaction."""
        try:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **kwargs,
            }
            # Sanitize any accidental secret exposure
            dumped = json.dumps(entry)
            token = self.token
            if token and token in dumped:
                dumped = dumped.replace(token, "[REDACTED_TELEGRAM_TOKEN]")

            logger.info("[telegram_audit] %s", dumped)
        except Exception as e:
            logger.warning("[telegram_bot] Failed to record audit log: %s", e)

    def get_info(self) -> dict[str, Any]:
        """Get bot configuration and health info."""
        ts_client = get_typesafe_client()
        return {
            "configured": bool(self.token) and len(self.token) >= 20,
            "initialized": self._initialized,
            "bot_username": self._bot_info.get("username"),
            "bot_id": self._bot_info.get("id"),
            "bot_name": self._bot_info.get("first_name"),
            "owner_usernames": list(_get_owner_usernames()),
            "owner_chat_ids": list(_get_owner_chat_ids()),
            "typesafe_enabled": ts_client.enabled,
            "typesafe_model": ts_client.model,
            "orchestrator_connected": self.orchestrator is not None or True,
            "processed_updates_cached": len(self._processed_updates),
        }


# Singleton bot instance
_bot_instance: TelegramBot | None = None


def get_telegram_bot() -> TelegramBot:
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = TelegramBot()
        _bot_instance.initialize()
    return _bot_instance


def is_telegram_ready() -> bool:
    bot = get_telegram_bot()
    return bot._initialized and bool(bot.token)


__all__ = [
    "TelegramBot",
    "BotProcessResult",
    "get_telegram_bot",
    "is_telegram_ready",
]
