"""
Test Maya AI Agent System with Wallpaper Request
Simulates: "Ekta hacker er wallpaper lagiye dao"
"""

import sys
import asyncio
sys.path.insert(0, r"c:\maya-ai\backend")

from brain.agents._workflow import agent_team_workflow
from brain.language_style import set_conversation_style

async def test_wallpaper_agent():
    print("=" * 70)
    print("🧪 TESTING MAYA AI AGENT — WALLPAPER REQUEST")
    print("=" * 70)
    
    # Set conversation style to Banglish
    set_conversation_style("banglish")
    
    # Test input
    user_request = "Ekta hacker er wallpaper lagiye dao"
    
    print(f"\n📝 User Request: {user_request}")
    print("\n🤖 Maya Processing...\n")
    
    try:
        # Call agent team workflow
        result = await agent_team_workflow(
            user_text=user_request,
            session_id="test_session_wallpaper",
            mode="professional"
        )
        
        print("\n" + "=" * 70)
        print("✅ AGENT RESPONSE:")
        print("=" * 70)
        print(result)
        
        # Check if camera was incorrectly triggered
        if "camera" in result.lower() and "wallpaper" not in result.lower():
            print("\n❌ FAILED: Camera was triggered instead of wallpaper!")
        elif "wallpaper" in result.lower() or "download" in result.lower():
            print("\n✅ SUCCESS: Wallpaper workflow triggered correctly!")
        else:
            print("\n⚠️  UNCLEAR: Check the response manually")
            
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_wallpaper_agent())
