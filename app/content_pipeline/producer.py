import asyncio
import json
import os
from pathlib import Path

import edge_tts
from groq import Groq

# Settings
BASE_DIR = Path("C:/Users/Ratanshila/WorkBuddy/Worktrees/leadgenrationaivoiceagent/main-554fb586")
OUTPUT_DIR = BASE_DIR / "data/content_pipeline"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Clients (Simulated loading from app configuration)
# Note: Ensure GROQ_API_KEY is set in environment
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

async def generate_script(topic):
    prompt = f"Write a 60-second engaging, high-conversion script for a short-form video about {topic}. Focus on a hooking opening, actionable value, and a strong CTA."
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-70b-versatile"
    )
    return chat_completion.choices[0].message.content

async def generate_voice(script, filename):
    voice = "hi-IN-SwaraNeural"
    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(str(OUTPUT_DIR / filename))
    return str(OUTPUT_DIR / filename)

async def main(topic):
    print(f"Generating pipeline for: {topic}")
    script = await generate_script(topic)
    script_path = OUTPUT_DIR / "script.txt"
    script_path.write_text(script, encoding="utf-8")

    print("Generating voiceover...")
    voice_path = await generate_voice(script, "voiceover.mp3")

    print(f"Pipeline complete. Script: {script_path}, Voice: {voice_path}")

if __name__ == "__main__":
    asyncio.run(main("Best local SEO tips for Indian small businesses"))
