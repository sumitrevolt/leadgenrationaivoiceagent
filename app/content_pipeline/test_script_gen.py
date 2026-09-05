import os
import sys

sys.path.append(r"C:\Users\Ratanshila\WorkBuddy\Worktrees\leadgenrationaivoiceagent\main-554fb586")

import asyncio
import traceback

try:
    from app.voice_agent.free_ai import chat
except Exception:
    print(traceback.format_exc())
    sys.exit(1)

async def main():
    try:
        topic = "AI Automated Marketing for local businesses"
        system_prompt = "You are an expert marketing scriptwriter."
        messages = [{"role": "user", "content": f"Create a short video script about {topic}."}]

        script, provider = await chat(system_prompt, messages, max_tokens=200, profile="bulk")
        print(f"Script generated using {provider}:\n{script}")
    except Exception:
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
