import os
import asyncio
import edge_tts
from app.voice_agent.free_ai import chat

# Configuration
OUTPUT_DIR = "data/content_gen"
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def generate_script(topic):
    """Generates a script using your existing free AI stack wrapper."""
    system = "You are a professional content creator for small Indian businesses. Write engaging script."
    prompt = f"Create a short, engaging 60-second video script about {topic}. Provide only the script text."
    
    # Use chat() directly as it is an async function
    script, _ = await chat(system=system, messages=[{"role": "user", "content": prompt}])
    return script

async def generate_voiceover(script, filename="voiceover.mp3"):
    """Generates high-quality voiceover using EdgeTTS."""
    output_path = os.path.join(OUTPUT_DIR, filename)
    communicate = edge_tts.Communicate(script, "hi-IN-SwaraNeural")
    await communicate.save(output_path)
    return output_path

async def run_pipeline(topic):
    print(f"Generating script for: {topic}")
    script = await generate_script(topic)
    print("Script generated. Generating voiceover...")
    voice_path = await generate_voiceover(script)
    print(f"Voiceover saved to: {voice_path}")
    
    # Save script to text file
    with open(os.path.join(OUTPUT_DIR, "script.txt"), "w", encoding="utf-8") as f:
        f.write(script)
    
    return script, voice_path

if __name__ == "__main__":
    topic = "Benefits of AI Marketing for small businesses"
    asyncio.run(run_pipeline(topic))
