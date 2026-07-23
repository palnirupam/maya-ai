import os
import re
import json
import asyncio
import logging
import psutil
import random
from enum import Enum
from pydantic import BaseModel, Field, model_validator
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client
from ..brain.gemini.function_calls import get_maya_tools

logger = logging.getLogger(__name__)

MAX_GEMINI_TOOLS = 64
TOOL_SAFETY_BUFFER = 5

_cached_native_tools_count = None
def get_native_tools_count():
    global _cached_native_tools_count
    if _cached_native_tools_count is None:
        _cached_native_tools_count = len(get_maya_tools())
    return _cached_native_tools_count

class MCPServerUnavailableError(Exception):
    pass

class ServerState(Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RESTARTING = "RESTARTING"
    READY = "READY"
    FAILED = "FAILED"
    PERMANENTLY_FAILED = "PERMANENTLY_FAILED"

class MCPServerConfig(BaseModel):
    transport: str = Field(pattern="^(stdio|sse)$")
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    max_tools: int = Field(default=20, ge=1)
    priority: int = Field(default=50, ge=0)
    health_check_interval_seconds: int = Field(default=30, ge=5)
    startup_timeout_seconds: int = Field(default=15, ge=5)

    @model_validator(mode="after")
    def validate_transport_requirements(self):
        if self.transport == "stdio" and not self.command:
            raise ValueError("transport 'stdio' requires a 'command'")
        if self.transport == "sse" and not self.url:
            raise ValueError("transport 'sse' requires a 'url'")
        return self

def _resolve_string(text: str) -> str:
    def repl(match):
        var_name = match.group(1)
        val = os.environ.get(var_name)
        if not val:
            raise EnvironmentError(f"Required env var '{var_name}' is not set.")
        return val
    return re.sub(r'\$\{([^}]+)\}', repl, text)

class MCPServerBase:
    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self.state = ServerState.IDLE
        self.ready_event = asyncio.Event()
        self._restart_lock = asyncio.Lock()
        self._health_check_task = None
        self.session: ClientSession | None = None
        self._tools = []
    
    async def start(self):
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        await self.restart()

    async def shutdown(self):
        if self._health_check_task:
            self._health_check_task.cancel()
        self.state = ServerState.PERMANENTLY_FAILED
        self.ready_event.clear()
        # Subclasses implement actual termination
    
    async def restart(self):
        async with self._restart_lock:
            if self.state in (ServerState.RESTARTING, ServerState.PERMANENTLY_FAILED):
                return
            self.state = ServerState.RESTARTING
            self.ready_event.clear()
            
        try:
            await self._perform_restart()
            # Fetch tools immediately to populate cache
            tools_response = await self.session.list_tools()
            self._tools = tools_response.tools if hasattr(tools_response, "tools") else []
            self.state = ServerState.READY
            self.ready_event.set()
        except Exception as e:
            self.ready_event.clear()
            logger.warning(f"MCP Server {self.name} failed to restart: {e}")
            self.state = ServerState.FAILED
            raise

    async def _perform_restart(self):
        raise NotImplementedError

    async def _ping(self):
        if not self.session:
            raise Exception("No active session")
        await self.session.list_tools()

    async def _health_check_loop(self):
        attempts = 0
        while self.state != ServerState.PERMANENTLY_FAILED:
            await asyncio.sleep(self.config.health_check_interval_seconds)
            
            if self.state == ServerState.FAILED:
                attempts += 1
                if attempts > 5:
                    self.state = ServerState.PERMANENTLY_FAILED
                    logger.error(f"MCP Server {self.name} permanently failed after 5 retries.")
                    break
                    
                backoff = min(60, 5 * (2 ** (attempts - 1)))
                backoff += random.uniform(0, 2)
                await asyncio.sleep(backoff)
                
                try:
                    await asyncio.wait_for(self.restart(), timeout=self.config.startup_timeout_seconds)
                    attempts = 0
                except Exception:
                    pass
                continue
                
            if self.state == ServerState.READY:
                try:
                    await asyncio.wait_for(self._ping(), timeout=5.0)
                    attempts = 0
                except Exception as e:
                    logger.warning(f"Health check failed for {self.name}: {e}")
                    self.state = ServerState.FAILED

    async def call_tool(self, tool_name: str, args: dict):
        try:
            await asyncio.wait_for(self.ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            raise MCPServerUnavailableError(f"Server {self.name} not ready after 10s")
            
        if self.state != ServerState.READY or not self.session:
            raise MCPServerUnavailableError(f"Server {self.name} is not available")
            
        return await self.session.call_tool(tool_name, arguments=args)

class StdioMCPServer(MCPServerBase):
    def __init__(self, name: str, config: MCPServerConfig):
        super().__init__(name, config)
        self._connection_task = None
        self._shutdown_event = asyncio.Event()

    async def _perform_restart(self):
        if self._connection_task:
            self._shutdown_event.set()
            # Wait briefly for teardown
            await asyncio.sleep(0.5)
            if not self._connection_task.done():
                self._connection_task.cancel()
                
        self._shutdown_event.clear()
        self._connection_task = asyncio.create_task(self._run_connection())
        # We don't await session.initialize here, the task does it. 
        # But restart() expects session to be ready to list tools.
        # Wait until session is populated by the task.
        for _ in range(self.config.startup_timeout_seconds * 10):
            if self.session:
                break
            await asyncio.sleep(0.1)
            
        if not self.session:
            raise Exception("Session failed to initialize in time")

    async def _run_connection(self):
        try:
            command = _resolve_string(self.config.command)
            args = [_resolve_string(arg) for arg in self.config.args]
            
            merged_env = os.environ.copy()
            for k, v in self.config.env.items():
                merged_env[k] = _resolve_string(v)
                
            server_params = StdioServerParameters(command=command, args=args, env=merged_env)
            
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.session = session
                    
                    # Block until shutdown is requested
                    await self._shutdown_event.wait()
                    
        except Exception as e:
            logger.warning(f"Stdio connection task failed for {self.name}: {e}")
        finally:
            self.session = None

    async def shutdown(self):
        await super().shutdown()
        if self._connection_task:
            self._shutdown_event.set()
            await asyncio.sleep(0.1)
            self._connection_task.cancel()
            self._connection_task = None

class SSEMCPServer(MCPServerBase):
    def __init__(self, name: str, config: MCPServerConfig):
        super().__init__(name, config)
        self._connection_task = None
        self._shutdown_event = asyncio.Event()

    async def _perform_restart(self):
        if self._connection_task:
            self._shutdown_event.set()
            await asyncio.sleep(0.5)
            if not self._connection_task.done():
                self._connection_task.cancel()
                
        self._shutdown_event.clear()
        self._connection_task = asyncio.create_task(self._run_connection())
        
        for _ in range(self.config.startup_timeout_seconds * 10):
            if self.session:
                break
            await asyncio.sleep(0.1)
            
        if not self.session:
            raise Exception("SSE Session failed to initialize in time")

    async def _run_connection(self):
        try:
            url = _resolve_string(self.config.url)
            headers = {k: _resolve_string(v) for k, v in self.config.headers.items()}
            
            async with sse_client(url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self.session = session
                    
                    await self._shutdown_event.wait()
                    
        except Exception as e:
            logger.warning(f"SSE connection task failed for {self.name}: {e}")
        finally:
            self.session = None

    async def shutdown(self):
        await super().shutdown()
        if self._connection_task:
            self._shutdown_event.set()
            await asyncio.sleep(0.1)
            self._connection_task.cancel()
            self._connection_task = None


class MCPService:
    def __init__(self):
        self.servers: dict[str, MCPServerBase] = {}
        self.config_path = os.path.join(os.path.dirname(__file__), "..", "config", "mcp_servers.json")

    async def start(self):
        if not os.path.exists(self.config_path):
            return
            
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        servers_config = data.get("mcpServers", {})
        for name, cfg_dict in servers_config.items():
            try:
                config = MCPServerConfig(**cfg_dict)
                if config.transport == "stdio":
                    server = StdioMCPServer(name, config)
                else:
                    server = SSEMCPServer(name, config)
                    
                self.servers[name] = server
                # Start non-blocking
                asyncio.create_task(self._safe_start(server))
            except Exception as e:
                logger.error(f"Failed to configure MCP server {name}: {e}")

    async def _safe_start(self, server: MCPServerBase):
        try:
            await server.start()
        except Exception as e:
            logger.error(f"MCP Server {server.name} failed initial startup: {e}")

    async def shutdown(self):
        for server in self.servers.values():
            await server.shutdown()

    async def get_available_tools(self, limit: int | None = None) -> list:
        if limit is None:
            limit = MAX_GEMINI_TOOLS - get_native_tools_count() - TOOL_SAFETY_BUFFER
            
        all_server_tools = []
        for server in self.servers.values():
            if server.state == ServerState.READY:
                # server._tools is cached during restart/health check
                server_tools = server._tools[:server.config.max_tools]
                all_server_tools.append({
                    "priority": server.config.priority,
                    "server_name": server.name,
                    "tools": server_tools
                })
                
        # Sort servers by priority descending
        all_server_tools.sort(key=lambda x: x["priority"], reverse=True)
        
        final_tools = []
        for st in all_server_tools:
            if len(final_tools) >= limit:
                break
            
            tools_to_add = st["tools"]
            available_for_server = limit - len(final_tools)
            if len(tools_to_add) > available_for_server:
                # Documented behavior: truncate from the tail
                logger.warning(f"Truncating {len(tools_to_add) - available_for_server} tools from {st['server_name']} due to context limits.")
                tools_to_add = tools_to_add[:available_for_server]
                
            for t in tools_to_add:
                # Keep discovery provider-neutral. The active LLM adapter
                # converts this schema to Gemini/OpenAI/Anthropic format later.
                safe_schema = t.inputSchema.copy() if t.inputSchema else {}
                safe_schema.pop("$schema", None)

                final_tools.append({
                    "name": f"{st['server_name']}__{t.name}",
                    "description": t.description or f"Tool {t.name} from {st['server_name']}",
                    "parameters": safe_schema,
                })
                
        return final_tools

    async def call_tool(self, namespaced_tool_name: str, args: dict):
        if "__" not in namespaced_tool_name:
            raise ValueError(f"Invalid namespaced tool name: {namespaced_tool_name}")
            
        server_name, tool_name = namespaced_tool_name.split("__", 1)
        server = self.servers.get(server_name)
        if not server:
            raise MCPServerUnavailableError(f"Server {server_name} not found")
            
        result = await server.call_tool(tool_name, args)
        
        # Result format handling for Gemini
        if hasattr(result, "content") and result.content:
            return "\n".join([c.text for c in result.content if hasattr(c, "text")])
        return "Success"

mcp_service = MCPService()
