"""Free-AI brain test — prove Cerebras/xAI answers a Hinglish sales turn (VPS)."""

import asyncio
import sys

sys.path.insert(0, "/opt/leadgen")


async def main() -> None:
    import app.voice_agent.free_ai as f

    print("PROVIDERS:", f.describe()["providers"])

    sys_prompt = (
        "Tum Swara ho — ek Indian solar lead-gen telecaller. Hinglish me, "
        "max 2 chhote sentence, ek sawaal. User ke jawab ko acknowledge karke aage badho."
    )
    msgs = [
        {
            "role": "assistant",
            "content": "Namaste! Kya aap apne ghar ke liye solar me interested hain?",
        },
        {"role": "user", "content": "haan bijli ka bill bahut zyada aata hai"},
    ]
    reply, provider = await f.chat(sys_prompt, msgs, max_tokens=90)
    print(f"PROVIDER_USED: {provider}")
    print(f"REPLY: {reply}")


if __name__ == "__main__":
    asyncio.run(main())
