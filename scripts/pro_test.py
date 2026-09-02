"""Free text test: professional TelecallerBrain reply quality (VPS, no phone cost)."""

import asyncio
import sys

sys.path.insert(0, "/opt/leadgen")


async def main() -> None:
    from app.voice_agent.telecaller_brain import TelecallerBrain

    b = TelecallerBrain(niche="solar_residential", client_name="SunGrow Solar")

    turns = [
        "haan bolo",
        "bijli ka bill bahut zyada aata hai",
        "lekin solar to bahut mehenga hota hai na",
        "abhi nahi, baad me sochenge",
    ]
    hist = []
    for u in turns:
        hist.append({"role": "user", "content": u})
        reply = await b.reply(hist, u)
        print(f"USER: {u}")
        print(f"BOT : {reply}\n")
        hist.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    asyncio.run(main())
