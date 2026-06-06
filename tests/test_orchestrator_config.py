import sys
import asyncio
sys.path.append(r'c:\maya-ai')
sys.stdout.reconfigure(encoding='utf-8')

# Load env variables
from dotenv import load_dotenv
load_dotenv('backend/.env')

from backend.brain.orchestrator import orchestrator

async def main():
    session_id = "test_config_session"
    prompt = "আমার জিমেইল হলো abc@gmail.com এবং পাসওয়ার্ড হলো xxxx, সেভ করো"
    print(f"Sending prompt to Maya's Orchestrator: '{prompt}'")
    print("--- STARTING ORCHESTRATOR LOOP ---")
    
    try:
        async for chunk in orchestrator.process_user_input_stream(session_id, prompt):
            # We print the raw chunk to see tool calls and text generation
            if isinstance(chunk, dict):
                print(f"\n[TOOL CALL] -> {chunk.get('name')} with args: {chunk.get('args')}")
            else:
                print(chunk, end="", flush=True)
        print("\n--- LOOP COMPLETED ---")
    except Exception as e:
        print("\nERROR during execution:", e)

if __name__ == "__main__":
    asyncio.run(main())
