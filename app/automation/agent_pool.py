"""
Async Agent Worker Pool.

`AgentWorkerPool` runs many client campaigns CONCURRENTLY through the
LeadGenPipeline, bounded by a configurable concurrency limit (asyncio
Semaphore, default 5). This is the "multiple agents handling the project"
layer: each in-flight campaign is tracked as a virtual agent with its own
status, current client, calls made and leads found.

Typical use:

    pool = AgentWorkerPool(concurrency=5)
    pool.submit(CampaignSpec(client_id="c1", niche="solar", cities=["Mumbai"]))
    pool.submit(CampaignSpec(client_id="c2", niche="dental_implants"))
    results = await pool.run_all()
"""

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.automation.orchestrator_pipeline import CampaignResult, LeadGenPipeline
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AgentStatus(str, Enum):
    """Lifecycle status of a single worker agent."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class CampaignSpec:
    """A single campaign request handed to the pool."""

    client_id: str
    niche: str
    cities: list[str] | None = None
    sources: list[str] | None = None
    max_leads: int = 100
    channels: list[str] | None = None
    client_name: str = ""
    client_service: str = ""
    notify_whatsapp: list[str] | None = None
    spreadsheet_id: str | None = None
    spec_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class AgentInfo:
    """In-memory registry entry describing one worker agent."""

    agent_id: str
    current_client: str | None = None
    status: AgentStatus = AgentStatus.IDLE
    calls_made: int = 0
    leads_found: int = 0
    qualified: int = 0
    spec_id: str | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["started_at"] = self.started_at.isoformat() if self.started_at else None
        data["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        return data


class AgentWorkerPool:
    """
    Runs queued campaigns concurrently with a bounded worker count.

    A new virtual agent is registered per campaign for observability, but the
    asyncio.Semaphore caps how many actually execute the pipeline at once.
    """

    def __init__(
        self,
        concurrency: int = 5,
        pipeline: LeadGenPipeline | None = None,
    ):
        self.concurrency = max(1, concurrency)
        self.semaphore = asyncio.Semaphore(self.concurrency)
        # A single pipeline instance is reused (its deps are stateless enough);
        # built lazily so importing the pool never hard-fails on missing deps.
        self._pipeline = pipeline
        self._specs: list[CampaignSpec] = []
        self.agents: dict[str, AgentInfo] = {}
        self._results: dict[str, CampaignResult] = {}
        logger.info(f"👥 AgentWorkerPool initialized (concurrency={self.concurrency})")

    @property
    def pipeline(self) -> LeadGenPipeline | None:
        """Lazily construct the shared pipeline, degrading on failure."""
        if self._pipeline is None:
            try:
                self._pipeline = LeadGenPipeline()
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Failed to build LeadGenPipeline: {e}")
                self._pipeline = None
        return self._pipeline

    # ------------------------------------------------------------------ #
    # Submission
    # ------------------------------------------------------------------ #
    def submit(self, campaign_spec: CampaignSpec) -> str:
        """
        Queue a campaign for execution.

        Returns the spec_id so the caller can correlate results/agents.
        """
        self._specs.append(campaign_spec)
        logger.info(
            f"Queued campaign spec={campaign_spec.spec_id} "
            f"client={campaign_spec.client_id} niche={campaign_spec.niche}"
        )
        return campaign_spec.spec_id

    def submit_many(self, specs: list[CampaignSpec]) -> list[str]:
        """Queue several campaigns at once."""
        return [self.submit(s) for s in specs]

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    async def run_all(self) -> dict[str, Any]:
        """
        Execute every queued campaign concurrently and return aggregated results.

        Returns:
            Dict with overall totals, per-spec CampaignResults and the final
            agent registry snapshot.
        """
        if not self._specs:
            logger.warning("run_all() called with no queued campaigns")
            return self._aggregate()

        logger.info(f"▶️ Running {len(self._specs)} campaigns (max {self.concurrency} concurrent)")

        tasks = [asyncio.create_task(self._run_one(spec)) for spec in self._specs]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Clear queue so the pool can be reused for a fresh batch.
        self._specs = []

        aggregated = self._aggregate()
        logger.info(
            f"🏁 Batch complete | campaigns={aggregated['total_campaigns']} "
            f"leads_found={aggregated['total_leads_found']} "
            f"qualified={aggregated['total_qualified']} "
            f"errors={aggregated['total_errors']}"
        )
        return aggregated

    async def _run_one(self, spec: CampaignSpec) -> None:
        """Run a single campaign under the concurrency semaphore."""
        agent = AgentInfo(
            agent_id=f"agent-{uuid.uuid4().hex[:8]}",
            current_client=spec.client_id,
            spec_id=spec.spec_id,
            status=AgentStatus.IDLE,
        )
        self.agents[agent.agent_id] = agent

        async with self.semaphore:
            agent.status = AgentStatus.RUNNING
            agent.started_at = datetime.now()
            logger.info(f"{agent.agent_id} ▶ client={spec.client_id} niche={spec.niche}")

            pipeline = self.pipeline
            if pipeline is None:
                agent.status = AgentStatus.ERROR
                agent.error = "pipeline unavailable"
                agent.finished_at = datetime.now()
                logger.error(f"{agent.agent_id} aborted: pipeline unavailable")
                return

            try:
                result = await pipeline.run_campaign(
                    client_id=spec.client_id,
                    niche=spec.niche,
                    cities=spec.cities,
                    sources=spec.sources,
                    max_leads=spec.max_leads,
                    channels=spec.channels,
                    client_name=spec.client_name,
                    client_service=spec.client_service,
                    notify_whatsapp=spec.notify_whatsapp,
                    spreadsheet_id=spec.spreadsheet_id,
                )
                self._results[spec.spec_id] = result

                # Sync agent registry from result.
                agent.calls_made = result.called
                agent.leads_found = result.scraped
                agent.qualified = result.qualified
                agent.status = AgentStatus.DONE
                if result.errors:
                    # Stage-level errors don't fail the whole campaign, but
                    # surface the first one for visibility.
                    agent.error = result.errors[0]
                logger.info(
                    f"{agent.agent_id} ✔ done | scraped={result.scraped} "
                    f"called={result.called} qualified={result.qualified}"
                )
            except Exception as e:
                agent.status = AgentStatus.ERROR
                agent.error = str(e)
                logger.error(f"{agent.agent_id} ✖ error: {e}")
            finally:
                agent.finished_at = datetime.now()

    # ------------------------------------------------------------------ #
    # Aggregation + status
    # ------------------------------------------------------------------ #
    def _aggregate(self) -> dict[str, Any]:
        results = list(self._results.values())
        total_errors = sum(1 for a in self.agents.values() if a.status == AgentStatus.ERROR)
        return {
            "total_campaigns": len(results),
            "total_leads_found": sum(r.scraped for r in results),
            "total_cleaned": sum(r.cleaned for r in results),
            "total_called": sum(r.called for r in results),
            "total_qualified": sum(r.qualified for r in results),
            "total_delivered": sum(r.delivered for r in results),
            "total_cost_estimate": round(sum(r.cost_estimate for r in results), 2),
            "total_billing_records": sum(len(r.billing_records) for r in results),
            "total_errors": total_errors,
            "results": {sid: r.to_dict() for sid, r in self._results.items()},
            "agents": self.status(),
        }

    def status(self) -> list[dict[str, Any]]:
        """Snapshot of every agent's current status."""
        return [a.to_dict() for a in self.agents.values()]

    def status_counts(self) -> dict[str, int]:
        """Count of agents grouped by status."""
        counts: dict[str, int] = {s.value: 0 for s in AgentStatus}
        for a in self.agents.values():
            counts[a.status.value] += 1
        return counts

    def get_result(self, spec_id: str) -> CampaignResult | None:
        """Fetch the CampaignResult for a given submitted spec."""
        return self._results.get(spec_id)


__all__ = ["AgentWorkerPool", "CampaignSpec", "AgentInfo", "AgentStatus"]
