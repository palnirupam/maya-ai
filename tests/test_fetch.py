import asyncio
import logging
from backend.tools.mcp_service import mcp_service

logging.basicConfig(level=logging.INFO)

async def test():
    await mcp_service.start()
    await asyncio.sleep(5)
    
    server = mcp_service.servers.get("memory")
    print(f"State: {server.state}")
    
    if server.session:
        res = await server.session.list_tools()
        print(f"Result type: {type(res)}")
        print(f"Result dir: {dir(res)}")
        if hasattr(res, "tools"):
            print(f"Tools length: {len(res.tools)}")
            if len(res.tools) > 0:
                t = res.tools[0]
                print(f"Tool 0 attrs: {dir(t)}")
        else:
            print("res does not have 'tools'")
            
    await mcp_service.shutdown()

if __name__ == "__main__":
    asyncio.run(test())
