import sys
sys.path.append("C:/maya-ai")

from backend.tools.desktop.advanced.memory_tools import configure_mcp_server
import json
from pathlib import Path

print("--- Test 1: Happy Path ---")
res1 = configure_mcp_server("youtube", "@modelcontextprotocol/server-youtube", {"YOUTUBE_API_KEY": "fake_key_123"})
print(res1)

print("\n--- Test 2: Invalid Package Injection ---")
res2 = configure_mcp_server("hack", "@modelcontextprotocol/server-youtube && calc.exe", {"YOUTUBE_API_KEY": "fake_key_123"})
print(res2)

print("\n--- Test 3: Invalid Env Value Injection ---")
res3 = configure_mcp_server("hack", "safe-package", {"HACK": "$(calc.exe)"})
print(res3)

print("\n--- Test 4: Merge Integrity ---")
# Pre-configure another dummy server
configure_mcp_server("dummy", "dummy-package", {})
# Update youtube server again
configure_mcp_server("youtube", "@modelcontextprotocol/server-youtube", {"YOUTUBE_API_KEY": "updated_key_456"})

# Read final json to verify 'dummy' and 'youtube' both exist and 'dummy' is unchanged
config_path = Path("C:/maya-ai/backend/config/mcp_servers.json")
with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)
print("\nFinal Config State:")
print(json.dumps(config, indent=2))
