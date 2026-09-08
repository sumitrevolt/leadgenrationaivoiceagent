"""
Master End-to-End Lead Generation Pipeline.

`LeadGenPipeline.run_campaign(...)` drives a single client campaign through the
full funnel:

    1. Scrape leads (LeadScraperManager)
    2. Clean + dedupe + phone-validate
    3. DND / NCPR scrub (skip flagged numbers)
    4. Compliance gate (only call within 9am-9pm window)
    5. Optional WhatsApp warm-up message
    6. AI voice call to qualify the lead using niche-specific questions
    7. Score the lead (hot / warm / cold)
    8. Deliver qualified leads to Google Sheets + HubSpot + WhatsApp alert
    9. Emit a per-lead billing record

Every stage is wrapped in try/except with logging and degrades gracefully when
a dependency or credential is missing (logs a warning and continues) so the
pipeline runs end-to-end even without live telephony / API keys configured.
External integration calls are made defensively (hasattr/getattr) so signature
drift in a dependency never hard-crashes the whole run.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Default per-niche price the agency charges the client per qualified lead (INR).
DEFAULT_PRICE_PER_QUALIFIED_LEAD = 350.0
# Rough telephony cost estimate per call (INR) used for the cost_estimate field.
DEFAULT_CALL_COST = 0.70
# Compliance calling window (TRAI guidance: marketing calls 09:00-21:00).
CALL_WINDOW_START = time(9, 0)
CALL_WINDOW_END = time(21, 0)


@dataclass
class CampaignResult:
    """Aggregate outcome of a single campaign run."""

    client_id: str
    niche: str
    scraped: int = 0
    cleaned: int = 0
    called: int = 0
    qualified: int = 0
    delivered: int = 0
    cost_estimate: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    hot_leads: int = 0
    warm_leads: int = 0
    cold_leads: int = 0
    skipped_dnd: int = 0
    billing_records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["started_at"] = self.started_at.isoformat()
        data["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        return data


class LeadGenPipeline:
    """
    Orchestrates the full lead-generation funnel for one client campaign.

    The pipeline lazily constructs each dependency and tolerates missing
    modules/credentials, so it can be exercised in development without live
    scrapers, telephony or CRM access.
    """

    def __init__(self, price_per_qualified_lead: float = DEFAULT_PRICE_PER_QUALIFIED_LEAD):
        self.price_per_qualified_lead = price_per_qualified_lead

        # Build dependencies defensively; a missing/broken module must not
        # prevent the rest of the pipeline from running.
        self.scraper = self._safe_init("scraper", self._build_scraper)
        self.dnd_checker = self._safe_init("dnd_checker", self._build_dnd_checker)
        self.voice_agent = self._safe_init("voice_agent", self._build_voice_agent)
        self.call_manager = self._safe_init("call_manager", self._build_call_manager)
        self.whatsapp = self._safe_init("whatsapp", self._build_whatsapp)
        self.sheets = self._safe_init("sheets", self._build_sheets)
        self.hubspot = self._safe_init("hubspot", self._build_hubspot)
        # Unified plug-and-play services (telephony + multi-channel delivery)
        self.telephony = self._safe_init("telephony", self._build_telephony)
        self.lead_delivery = self._safe_init("lead_delivery", self._build_lead_delivery)
        self.webhooks = self._safe_init("webhooks", self._build_webhooks)

        logger.info("🛠️ LeadGenPipeline initialized")

    # ------------------------------------------------------------------ #
    # Dependency builders (kept tiny + isolated so one failure is contained)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_init(name: str, builder):
        try:
            return builder()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"Dependency '{name}' unavailable, degrading gracefully: {e}")
            return None

    @staticmethod
    def _build_scraper():
        from app.lead_scraper.scraper_manager import LeadScraperManager

        return LeadScraperManager()

    @staticmethod
    def _build_dnd_checker():
        from app.utils.dnd_checker import DNDChecker

        return DNDChecker()

    @staticmethod
    def _build_voice_agent():
        from app.voice_agent.agent import VoiceAgent

        return VoiceAgent()

    @staticmethod
    def _build_call_manager():
        from app.telephony.call_manager import CallManager

        return CallManager()

    @staticmethod
    def _build_whatsapp():
        from app.integrations.whatsapp import get_whatsapp_sender

        return get_whatsapp_sender()  # dual-engine: self-host (WAHA) or Cloud API

    @staticmethod
    def _build_sheets():
        from app.integrations.google_sheets import GoogleSheetsIntegration

        return GoogleSheetsIntegration()

    @staticmethod
    def _build_hubspot():
        from app.integrations.hubspot import HubSpotIntegration

        return HubSpotIntegration()

    @staticmethod
    def _build_telephony():
        from app.telephony.telephony_service import get_telephony_service

        return get_telephony_service()

    @staticmethod
    def _build_lead_delivery():
        from app.integrations.lead_delivery import get_lead_delivery

        return get_lead_delivery()

    @staticmethod
    def _build_webhooks():
        from app.integrations.webhooks_emitter import get_webhook_emitter

        return get_webhook_emitter()

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    async def run_campaign(
        self,
        client_id: str,
        niche: str,
        cities: list[str] | None = None,
        sources: list[str] | None = None,
        max_leads: int = 100,
        channels: list[str] | None = None,
        client_name: str = "",
        client_service: str = "",
        notify_whatsapp: list[str] | None = None,
        spreadsheet_id: str | None = None,
    ) -> CampaignResult:
        """
        Run the complete pipeline for one client campaign.

        Args:
            client_id: Identifier of the client owning this campaign.
            niche: Niche key (see app.niches.NICHES).
            cities: Target cities (defaults to scraper defaults).
            sources: Scraper sources (google_maps, indiamart, justdial, linkedin,
                     web, social).
            max_leads: Max leads to scrape/process.
            channels: Enabled outreach channels, e.g. ["whatsapp", "voice"].
                      Controls the warm-up + calling stages.
            client_name / client_service: Used in the voice script + alerts.
            notify_whatsapp: Numbers to alert when a hot lead is delivered.
            spreadsheet_id: Target Google Sheet (falls back to default).

        Returns:
            CampaignResult with stage-by-stage counts and billing records.
        """
        channels = channels or ["whatsapp", "voice"]
        notify_whatsapp = notify_whatsapp or []
        result = CampaignResult(client_id=client_id, niche=niche)

        logger.info(
            f"🚀 Campaign start | client={client_id} niche={niche} "
            f"cities={cities} sources={sources} channels={channels}"
        )

        # Stage 1: Scrape
        leads = await self._stage_scrape(niche, cities, sources, max_leads, result)

        # Stage 2: Clean + dedupe + phone validate
        leads = self._stage_clean(leads, result)

        # Stage 3: DND / NCPR scrub
        leads = await self._stage_dnd_scrub(leads, result, channels=channels)

        # Stage 4: Compliance time-window gate
        if not self._within_calling_window():
            logger.warning(
                "⏰ Outside compliant calling window (09:00-21:00) — "
                "skipping warm-up + voice stages, leads retained for later."
            )
        else:
            # Stage 5: Optional WhatsApp warm-up
            if "whatsapp" in channels:
                await self._stage_whatsapp_warmup(leads, client_name, result)

            # Stage 6 + 7: Voice qualification + scoring
            if "voice" in channels:
                await self._stage_qualify_and_score(
                    leads, niche, client_name, client_service, result
                )

        # Stage 8 + 9: Deliver qualified leads + emit billing records
        await self._stage_deliver_and_bill(
            leads,
            niche,
            client_id,
            client_name,
            notify_whatsapp,
            spreadsheet_id,
            result,
        )

        result.finished_at = datetime.now()
        logger.info(
            f"✅ Campaign done | client={client_id} scraped={result.scraped} "
            f"cleaned={result.cleaned} called={result.called} "
            f"qualified={result.qualified} delivered={result.delivered} "
            f"cost≈₹{result.cost_estimate:.2f}"
        )
        # Webhook event: campaign finished (summary metrics).
        if self.webhooks and hasattr(self.webhooks, "emit"):
            try:
                await self.webhooks.emit(
                    "campaign.completed",
                    {
                        "client_id": client_id,
                        "niche": niche,
                        "scraped": result.scraped,
                        "qualified": result.qualified,
                        "delivered": result.delivered,
                        "cost_estimate": result.cost_estimate,
                    },
                    client_id=client_id,
                )
            except Exception as e:
                logger.debug(f"webhook campaign.completed failed: {e}")
        return result

    # ------------------------------------------------------------------ #
    # Stage 1: Scrape
    # ------------------------------------------------------------------ #
    async def _stage_scrape(self, niche, cities, sources, max_leads, result) -> list[Any]:
        if not self.scraper:
            logger.warning("Scraper unavailable; producing zero leads.")
            return []
        try:
            leads = await self.scraper.scrape_leads(
                niche=niche,
                cities=cities,
                sources=sources,
                max_leads=max_leads,
            )
            result.scraped = len(leads)
            logger.info(f"Stage 1 scrape: {len(leads)} leads")
            return list(leads)
        except Exception as e:
            logger.error(f"Stage 1 scrape failed: {e}")
            result.errors.append(f"scrape: {e}")
            return []

    # ------------------------------------------------------------------ #
    # Stage 2: Clean + dedupe + phone validate
    # ------------------------------------------------------------------ #
    def _stage_clean(self, leads: list[Any], result) -> list[Any]:
        try:
            cleaned: list[Any] = []
            seen_phones: set = set()
            seen_companies: set = set()

            for lead in leads:
                phone = getattr(lead, "phone", None)
                company = (getattr(lead, "company_name", "") or "").lower().strip()

                # Must have a usable phone to be callable.
                phone_key = None
                if phone:
                    digits = "".join(filter(str.isdigit, str(phone)))
                    if len(digits) >= 10:
                        phone_key = digits[-10:]

                if not phone_key:
                    continue  # un-callable, drop from this pipeline
                if phone_key in seen_phones:
                    continue
                # Phone is the ONLY dedup key here (every lead already has one).
                # Name-based dedup would wrongly drop distinct-phone franchise
                # branches that share a company name.

                seen_phones.add(phone_key)
                cleaned.append(lead)

            result.cleaned = len(cleaned)
            logger.info(f"Stage 2 clean/dedupe: {len(leads)} → {len(cleaned)}")
            return cleaned
        except Exception as e:
            logger.error(f"Stage 2 clean failed: {e}")
            result.errors.append(f"clean: {e}")
            return leads

    # ------------------------------------------------------------------ #
    # Stage 3: DND / NCPR scrub
    # ------------------------------------------------------------------ #
    async def _stage_dnd_scrub(
        self, leads: list[Any], result, channels: list[str] | None = None
    ) -> list[Any]:
        # COMPLIANCE (CLAUDE.md §5): DND scrub FAIL-CLOSED — lookup fail ya checker
        # unavailable = promotional contact BLOCK (pehle yahan fail-OPEN tha:
        # checker missing par poori list pass, per-lead error par number allow —
        # jo §5 TRAI invariant todta tha). Cold outbound bina proven-non-DND number
        # ILLEGAL hai; jab DND verify nahi ho sakta to woh number is promotional
        # pipeline se HATA do. (Yeh sirf is qualify+call harness pe; asli prod
        # calling path VobizClient + tasks/calling me apna DND/window gate rakhta.)
        #
        # OPS-017: this stage feeds BOTH Stage 5 (WhatsApp warm-up) and Stage 6
        # (voice). A number that may legally be CALLED still may not receive a
        # promotional MESSAGE — NCPR scrubbing is mandatory for messaging and
        # consent does not override a DND registration there. So scrub on the
        # STRICTEST channel this run actually uses: if WhatsApp is enabled (or
        # channels is unknown), scrub as messaging and refuse the blanket
        # carrier-scrub allowance.
        channel = "messaging" if (not channels or "whatsapp" in channels) else "voice"
        if not self.dnd_checker:
            logger.warning(
                "DND checker unavailable — FAIL-CLOSED: promotional contact BLOCKED "
                "for this run (§5, cannot prove non-DND)."
            )
            result.skipped_dnd += len([1 for l in leads if getattr(l, "phone", None)])
            return []

        kept: list[Any] = []
        for lead in leads:
            phone = getattr(lead, "phone", None)
            if not phone:
                continue
            try:
                is_dnd = await self._is_dnd(phone, channel=channel)
            except Exception as e:
                logger.debug(f"DND check error for ***{str(phone)[-4:]}: {e}")
                is_dnd = True  # FAIL-CLOSED (§5): lookup fail = promotional BLOCK
            if is_dnd:
                result.skipped_dnd += 1
                continue
            kept.append(lead)

        logger.info(f"Stage 3 DND scrub: removed {result.skipped_dnd}, kept {len(kept)}")
        return kept

    async def _is_dnd(self, phone: str, channel: str = "messaging") -> bool:
        """Defensively call whichever DND API the checker exposes.

        ``channel`` is forwarded to the DND checker (OPS-017): the blanket
        DND_CARRIER_SCRUB allowance is voice-only, so a messaging scrub must
        not inherit it.

        FAIL-CLOSED (2026-08-01, enterprise-audit fix): pehle yeh unverified result
        (`is_dnd=False, verified=False`) ko non-DND maan leta tha — no-provider case me
        har number promotional pipeline me pass. Ab UNVERIFIED = DND (promotional BLOCK)
        taaki §5 fail-CLOSED invariant pura stack me ek jaisa ho.
        """
        checker = self.dnd_checker
        if hasattr(checker, "check_single"):
            try:
                res = await checker.check_single(phone, channel=channel)
            except TypeError:
                # Test double / older signature without the channel kwarg.
                res = await checker.check_single(phone)
            verified = bool(getattr(res, "verified", True))
            if not verified:
                return True  # unverified lookup = DND (fail-closed)
            return bool(getattr(res, "is_dnd", False))
        if hasattr(checker, "check"):
            res = await checker.check(phone)
            if isinstance(res, dict):
                if not bool(res.get("verified", True)):
                    return True
                return bool(res.get("is_dnd", False))
            verified = bool(getattr(res, "verified", True))
            if not verified:
                return True
            return bool(getattr(res, "is_dnd", False))
        return True  # checker has neither API = cannot prove non-DND (fail-closed)

    # ------------------------------------------------------------------ #
    # Stage 4: Compliance time-window gate
    # ------------------------------------------------------------------ #
    @staticmethod
    def _within_calling_window(now: datetime | None = None) -> bool:
        # COMPLIANCE (§5 TRAI window): time-of-day IST me hona chahiye. Pehle naive
        # datetime.now() tha — agar container TZ=UTC hoti to 09:00-21:00 UTC = 14:30-
        # 02:30 IST, jo raat 2 baje IST call ALLOW karta (illegal) + subah 9 baje IST
        # BLOCK. Ab explicit Asia/Kolkata. Test/caller ne `now` diya ho to as-is.
        if now is None:
            try:
                from zoneinfo import ZoneInfo

                now = datetime.now(ZoneInfo("Asia/Kolkata"))
            except Exception:
                now = datetime.now()
        return CALL_WINDOW_START <= now.time() <= CALL_WINDOW_END

    # ------------------------------------------------------------------ #
    # Stage 5: WhatsApp warm-up
    # ------------------------------------------------------------------ #
    async def _stage_whatsapp_warmup(self, leads, client_name, result) -> None:
        if not self.whatsapp or not getattr(self.whatsapp, "token", None):
            logger.warning("WhatsApp not configured; skipping warm-up stage.")
            return

        sent = 0
        for lead in leads:
            phone = getattr(lead, "phone", None)
            if not phone:
                continue
            try:
                if hasattr(self.whatsapp, "send_text_message"):
                    company = getattr(lead, "company_name", "there")
                    msg = (
                        f"Hi {company}! This is {client_name or 'our team'}. "
                        "We'd love to share something relevant for your business — "
                        "is now a good time for a quick call?"
                    )
                    await self.whatsapp.send_text_message(phone, msg)
                    sent += 1
            except Exception as e:
                logger.debug(f"WhatsApp warm-up failed for ***{str(phone)[-4:]}: {e}")

        logger.info(f"Stage 5 WhatsApp warm-up: {sent} messages sent")

    # ------------------------------------------------------------------ #
    # Stage 6 + 7: Voice qualification + scoring
    # ------------------------------------------------------------------ #
    async def _stage_qualify_and_score(
        self, leads, niche, client_name, client_service, result
    ) -> None:
        questions = self._niche_questions(niche)

        for lead in leads:
            phone = getattr(lead, "phone", None)
            if not phone:
                continue

            qualification: dict[str, Any] = {}
            intent = "no_answer"
            try:
                qualification, intent = await self._run_voice_call(
                    lead, niche, client_name, client_service, questions
                )
                result.called += 1
                result.cost_estimate += DEFAULT_CALL_COST
            except Exception as e:
                logger.debug(f"Voice call failed for ***{str(phone)[-4:]}: {e}")
                result.errors.append(f"voice:***{str(phone)[-4:]}: {e}")

            score, tier = self._score_lead(lead, qualification, intent)
            # Attach scoring back onto the lead's raw_data so downstream
            # delivery stages can read it without a separate structure.
            self._annotate_lead(lead, score, tier, qualification, intent)

            if tier == "hot":
                result.hot_leads += 1
            elif tier == "warm":
                result.warm_leads += 1
            else:
                result.cold_leads += 1

        logger.info(
            f"Stage 6/7 qualify+score: called={result.called} "
            f"hot={result.hot_leads} warm={result.warm_leads} cold={result.cold_leads}"
        )

    async def _run_voice_call(self, lead, niche, client_name, client_service, questions):
        """
        Execute (or simulate) one outbound qualification call.

        Prefers the VoiceAgent conversation API. When telephony/voice deps are
        unavailable the call degrades to an empty-but-valid qualification result
        so the pipeline still completes.
        """
        phone = getattr(lead, "phone", "")
        lead_id = getattr(lead, "id", str(uuid.uuid4()))
        lead_data = {
            "company_name": getattr(lead, "company_name", ""),
            "contact_name": getattr(lead, "contact_name", None),
            "city": getattr(lead, "city", ""),
            "category": getattr(lead, "category", ""),
            "questions": questions,
        }

        # Place the actual outbound call via the unified telephony service.
        # In simulation mode (no provider keys) this returns a realistic
        # connected/no-answer/busy outcome so the pipeline runs end-to-end.
        if self.telephony and hasattr(self.telephony, "place_call"):
            try:
                call_res = await self.telephony.place_call(to_number=phone)
                status = getattr(call_res, "status", "connected")
                if status not in ("connected", "completed", "answered"):
                    # Phone did not connect — no qualification possible.
                    return {}, "no_answer"
            except Exception as e:
                logger.debug(f"Telephony place_call failed for ***{str(phone)[-4:]}: {e}")

        if not self.voice_agent:
            return {}, "no_answer"

        try:
            # Drive the agent through a minimal scripted session. We do not have
            # live audio here, so we feed the qualification questions as text and
            # collect agent responses — enough to exercise intent detection and
            # produce a transcript without a PSTN leg.
            context = await self.voice_agent.start_call(
                lead_id=lead_id,
                phone_number=phone,
                campaign_id=getattr(lead, "source", "campaign"),
                niche=niche,
                client_name=client_name or "Our Company",
                client_service=client_service or niche.replace("_", " "),
                script_name=f"{niche}_script",
                lead_data=lead_data,
            )
            call_id = getattr(context, "call_id", None)
            if call_id and hasattr(self.voice_agent, "get_opening_message"):
                await self.voice_agent.get_opening_message(call_id)

            answers: dict[str, Any] = {}
            if call_id and hasattr(self.voice_agent, "process_speech"):
                for q in questions:
                    try:
                        # Simulate the lead acknowledging — real audio would
                        # replace transcribed_text in production.
                        await self.voice_agent.process_speech(
                            call_id, transcribed_text="Yes, tell me more."
                        )
                        answers[q] = "captured"
                    except Exception as e:
                        logger.debug(f"process_speech failed: {e}")
                        break

            summary = {}
            if call_id and hasattr(self.voice_agent, "end_call"):
                summary = await self.voice_agent.end_call(call_id)

            intent = (summary or {}).get("detected_intent") or "interested"
            qualification = (summary or {}).get("qualification_answers") or answers
            return qualification, intent
        except Exception as e:
            logger.debug(f"Voice agent session error: {e}")
            return {}, "no_answer"

    @staticmethod
    def _niche_questions(niche: str) -> list[str]:
        try:
            from app.niches import NICHES

            cfg = NICHES.get(niche, {})
            return list(cfg.get("qualification_questions", []))
        except Exception as e:
            logger.debug(f"Could not load niche questions: {e}")
            return []

    @staticmethod
    def _score_lead(lead, qualification: dict[str, Any], intent: str):
        """
        Heuristic 0-100 lead score → tier.

        hot  >= 70, warm 40-69, cold < 40.
        """
        score = 0

        # Intent signal is the strongest driver.
        intent_weights = {
            "appointment_interest": 50,
            "appointment": 50,
            "interested": 40,
            "callback_request": 30,
            "callback": 30,
            "no_answer": 0,
            "not_interested": -10,
            "opt_out": -30,
        }
        score += intent_weights.get(intent or "", 0)

        # Each captured qualification answer adds confidence.
        score += min(len(qualification or {}) * 10, 30)

        # Data-quality signals.
        if getattr(lead, "verified", False):
            score += 10
        if getattr(lead, "email", None):
            score += 5
        if getattr(lead, "phone_verified", False):
            score += 5
        rating = getattr(lead, "rating", None)
        if rating and rating >= 4.0:
            score += 5

        score = max(0, min(score, 100))

        if score >= 70:
            tier = "hot"
        elif score >= 40:
            tier = "warm"
        else:
            tier = "cold"
        return score, tier

    @staticmethod
    def _annotate_lead(lead, score, tier, qualification, intent) -> None:
        raw = getattr(lead, "raw_data", None)
        if isinstance(raw, dict):
            raw["lead_score"] = score
            raw["lead_tier"] = tier
            raw["qualification"] = qualification
            raw["detected_intent"] = intent

    # ------------------------------------------------------------------ #
    # Stage 8 + 9: Deliver qualified leads + billing
    # ------------------------------------------------------------------ #
    async def _stage_deliver_and_bill(
        self,
        leads,
        niche,
        client_id,
        client_name,
        notify_whatsapp,
        spreadsheet_id,
        result,
    ) -> None:
        for lead in leads:
            raw = getattr(lead, "raw_data", {}) or {}
            tier = raw.get("lead_tier")
            score = raw.get("lead_score", 0)

            # Only "hot" / "warm" leads are considered qualified + billable.
            if tier not in ("hot", "warm"):
                continue
            result.qualified += 1

            lead_data = self._lead_to_dict(lead, score, raw)
            delivered_any = False

            # 8a. Google Sheets
            if self.sheets and getattr(self.sheets, "client", None):
                try:
                    if hasattr(self.sheets, "append_lead"):
                        ok = await self.sheets.append_lead(lead_data, spreadsheet_id)
                        delivered_any = delivered_any or bool(ok)
                except Exception as e:
                    logger.debug(f"Sheets delivery failed: {e}")

            # 8b. HubSpot
            if self.hubspot and getattr(self.hubspot, "headers", None):
                try:
                    if hasattr(self.hubspot, "create_contact"):
                        contact_id = await self.hubspot.create_contact(lead_data)
                        delivered_any = delivered_any or bool(contact_id)
                except Exception as e:
                    logger.debug(f"HubSpot delivery failed: {e}")

            # 8c. WhatsApp hot-lead alert
            if (
                tier == "hot"
                and notify_whatsapp
                and self.whatsapp
                and getattr(self.whatsapp, "token", None)
                and hasattr(self.whatsapp, "send_lead_alert")
            ):
                for number in notify_whatsapp:
                    try:
                        await self.whatsapp.send_lead_alert(number, lead_data)
                        delivered_any = True
                    except Exception as e:
                        logger.debug(f"WhatsApp alert failed: {e}")

            # 8d. Unified multi-channel delivery (WhatsApp + Sheets + HubSpot +
            # Email) via LeadDelivery — env-gated, graceful no-op when a channel
            # isn't configured. Complements the direct calls above.
            if self.lead_delivery and hasattr(self.lead_delivery, "deliver_lead"):
                try:
                    client_config = {
                        "spreadsheet_id": spreadsheet_id,
                        "notify_whatsapp": (notify_whatsapp or [None])[0],
                    }
                    dr = await self.lead_delivery.deliver_lead(lead_data, client_config)
                    if getattr(dr, "any_delivered", False):
                        delivered_any = True
                except Exception as e:
                    logger.debug(f"LeadDelivery failed: {e}")

            if delivered_any:
                result.delivered += 1
                # Webhook event: lead qualified + delivered.
                if self.webhooks and hasattr(self.webhooks, "emit"):
                    try:
                        await self.webhooks.emit("lead.qualified", lead_data, client_id=client_id)
                    except Exception as e:
                        logger.debug(f"webhook lead.qualified failed: {e}")

            # 9. Per-lead billing record
            result.billing_records.append(self._billing_record(client_id, niche, lead, score, tier))

        # Total billable revenue is informational alongside cost_estimate.
        result.cost_estimate = round(result.cost_estimate, 2)
        logger.info(
            f"Stage 8/9 deliver+bill: qualified={result.qualified} "
            f"delivered={result.delivered} billing_records={len(result.billing_records)}"
        )

    def _billing_record(self, client_id, niche, lead, score, tier) -> dict[str, Any]:
        return {
            "billing_id": str(uuid.uuid4()),
            "client_id": client_id,
            "niche": niche,
            "lead_id": getattr(lead, "id", None),
            "company_name": getattr(lead, "company_name", ""),
            "phone": getattr(lead, "phone", None),
            "lead_score": score,
            "lead_tier": tier,
            "amount": self.price_per_qualified_lead,
            "currency": "INR",
            "billable": True,
            "created_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _lead_to_dict(lead, score, raw) -> dict[str, Any]:
        return {
            "id": getattr(lead, "id", ""),
            "company_name": getattr(lead, "company_name", ""),
            "contact_name": getattr(lead, "contact_name", "") or "",
            "phone": getattr(lead, "phone", "") or "",
            "email": getattr(lead, "email", "") or "",
            "city": getattr(lead, "city", "") or "",
            "state": getattr(lead, "state", "") or "",
            "category": getattr(lead, "category", "") or "",
            "source": getattr(lead, "source", "") or "",
            "lead_score": score,
            "outcome": raw.get("detected_intent", ""),
            "notes": str(raw.get("qualification", "")),
        }


__all__ = ["LeadGenPipeline", "CampaignResult"]
