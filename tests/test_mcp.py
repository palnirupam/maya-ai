import asyncio
import logging
from backend.tools.mcp_service import mcp_service

logging.basicConfig(level=logging.INFO)

async def test():
    print("Starting MCP Service...")
    await mcp_service.start()
    
    print("\nWaiting 5 seconds for servers to initialize...")
    await asyncio.sleep(5)
    
    print("\nFetching tools from MCP servers...")
    tools = await mcp_service.get_available_tools(limit=10)
    
    if not tools:
        print("No tools found. Check if the server started successfully.")
    else:
        print(f"Found {len(tools)} tools!")
        for t in tools:
            print(f"  - {t.function_declarations[0].name}: {t.function_declarations[0].description}")
            
    print("\nShutting down...")
    await mcp_service.shutdown()

if __name__ == "__main__":
    asyncio.run(test())
