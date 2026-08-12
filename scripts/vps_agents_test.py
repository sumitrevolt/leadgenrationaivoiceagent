"""VPS smoke: LangGraph supervisor run + Qdrant KB backend check."""

import asyncio
import os


async def main() -> None:
    from app.agents import AGENTS_AVAILABLE, run_supervisor_task

    print("agents available:", AGENTS_AVAILABLE)

    r1 = await run_supervisor_task(
        "research and seed knowledge for this client's business profile",
        niche="solar_residential",
    )
    print("DATA route:", r1["route"], "| result:", str(r1["result"])[:140])

    r2 = await run_supervisor_task(
        "qualify a new lead for rooftop solar and plan the outreach call",
        niche="solar_residential",
    )
    print("LEADS route:", r2["route"], "| result:", str(r2["result"])[:140])

    # Qdrant KB backend check
    from app.voice_agent.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    kb.add_documents(
        ["Qdrant smoke fact: solar site surveys booked within 24h."],
        source="smoke",
        namespace="smoke_test",
    )
    hits = kb.retrieve("site survey booking", k=1, namespace="smoke_test")
    print("KB hit:", hits[0]["text"][:60] if hits else "NONE")
    import requests

    qdrant_url = (os.getenv("QDRANT_URL") or "").strip()
    if not qdrant_url:
        qdrant_url = (
            "http://qdrant:6333" if os.path.exists("/.dockerenv") else "http://127.0.0.1:6333"
        )
    cols = requests.get(f"{qdrant_url.rstrip('/')}/collections", timeout=5).json()
    print("Qdrant collections:", [c["name"] for c in cols["result"]["collections"]])


if __name__ == "__main__":
    asyncio.run(main())
