import asyncio
import sys
from app.voice_agent.llm_brain import LLMBrain

async def verify_maya():
    print("🤖 Initializing Maya (AI Sales Agent with Vertex AI)...")
    from app.config import settings
    # Force Vertex AI for verification
    settings.default_llm = "vertex-gemini-1.5-flash"
    
    print(f"DEBUG: Project: {settings.google_cloud_project_id}")
    print(f"DEBUG: Location: {settings.google_cloud_location}")
    print(f"DEBUG: Default LLM: {settings.default_llm}")
        
    brain = LLMBrain()
    
    # 1. Simulate the initial greeting/pitch
    print("\n--- TEST Check 1: Initial Pitch ---")
    system_prompt = brain.SYSTEM_PROMPTS["saas_sales_agent"].format(
        client_name="LeadGen AI",
        niche="Real Estate"
    )
    
    # Simulate the start of a call where the AI speaks first
    print("User (Simulated): [Answers phone] Hello?")
    response = await brain._generate_chat(
        system_prompt=system_prompt,
        conversation_history=[{"role": "user", "content": "Hello?"}]
    )
    print(f"Maya: {response}")
    
    # 2. Simulate an objection
    print("\n--- TEST Check 2: Objection Handling ---")
    history = [
        {"role": "user", "content": "Hello?"},
        {"role": "assistant", "content": response},
        {"role": "user", "content": "Is this a robot calling me?"}
    ]
    
    response_obj = await brain._generate_chat(
        system_prompt=system_prompt,
        conversation_history=history
    )
    print(f"User: Is this a robot calling me?")
    print(f"Maya: {response_obj}")
    
    # 3. Simulate interest/closing
    print("\n--- TEST Check 3: Closing ---")
    history.append({"role": "assistant", "content": response_obj})
    history.append({"role": "user", "content": "Okay, that sounds interesting. How much is it?"})
    
    response_close = await brain._generate_chat(
        system_prompt=system_prompt,
        conversation_history=history
    )
    print(f"User: Okay, that sounds interesting. How much is it?")
    print(f"Maya: {response_close}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_maya())
