import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from backend.brain.agents.agent_defs import AGENTS, ROUTING_PROMPT
from backend.brain.agents.agent_team import execute_workflow
from backend.brain.providers.gemini_adapter import gemini_adapter


def _mock_session_with_system_perm(enabled: bool):
    """Helper: build a mocked DB session whose single preference row decrypts
    to 'true' or 'false' for PERM_SYSTEM."""
    mock_db = MagicMock()
    mock_pref = MagicMock()
    mock_pref.value = "encrypted_blob"
    mock_db.query.return_value.filter.return_value.first.return_value = mock_pref

    def fake_decrypt(value):
        return "true" if enabled else "false"

    return mock_db, fake_decrypt

class TestMultiAgentSystem(unittest.IsolatedAsyncioTestCase):
    
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_workflow_routing_and_execution(self, mock_adapter):
        """Test that the router parses correct agents and executes them sequentially."""
        # Mock Router response to schedule RESEARCHER then CODER
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["RESEARCHER", "CODER"]}')
        
        # Mock streaming responses from sub-agents
        async def mock_stream_researcher(*args, **kwargs):
            yield "Information found on the web."
            
        async def mock_stream_coder(*args, **kwargs):
            yield "Code compiled successfully."
            
        # First call is router (generate_response), subsequent are generate_stream for agents
        mock_adapter.generate_stream.side_effect = [
            mock_stream_researcher(),
            mock_stream_researcher(),  # one completion-audit retry
            mock_stream_coder(),
            mock_stream_coder(),       # one completion-audit retry
        ]
        
        context_history = []
        chunks = []
        
        async for chunk in execute_workflow("session_123", "Search and write code", context_history):
            if isinstance(chunk, str):
                chunks.append(chunk)
                
        # By design, only the LAST agent streams its text to the user;
        # intermediate agents' output is buffered and passed downstream as
        # context (so e.g. "get news and send it" doesn't show the news twice).
        full_text = "".join(chunks)
        self.assertNotIn("Information found on the web.", full_text)
        self.assertIn("Code compiled successfully.", full_text)

        # But NO result is lost: both agents' outputs are persisted together in
        # the final assistant memory turn.
        self.assertEqual(len(context_history), 1)
        self.assertIn("Information found on the web.", context_history[0]["content"])
        self.assertIn("Code compiled successfully.", context_history[0]["content"])

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_refinement_loops_max_termination(self, mock_adapter):
        """Test that execution stops after max tool rounds but produces a real
        final summary instead of a generic 'partially complete' failure banner."""
        # The test input routes via _fast_route ("research" keyword). The only
        # generate_response call made by agent_team is for the final summary.
        mock_adapter.generate_response = AsyncMock(return_value="Summary: completed the research loop.")

        # Simulate sub-agent repeatedly making tool calls (so it loops indefinitely)
        async def mock_stream_looping(*args, **kwargs):
            yield {"type": "tool_call", "name": "web_search", "args": {"query": "test"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_looping(),
            mock_stream_looping(),
            mock_stream_looping(),
            mock_stream_looping()
        ]

        # Mock tool function execution to return success
        with patch('backend.brain.agents.agent_team.get_maya_tools') as mock_get_tools:
            mock_tool = MagicMock()
            mock_tool.__name__ = "web_search"
            mock_tool.return_value = "Search result"
            mock_get_tools.return_value = [mock_tool]

            context_history = []
            chunks = []

            async for chunk in execute_workflow("session_123", "Run a looping research task that keeps calling tools", context_history):
                if isinstance(chunk, str):
                    chunks.append(chunk)

            full_text = "".join(chunks)
            # The old vague failure banner must NOT appear.
            self.assertNotIn("Task may be partially complete", full_text)
            # Final summary from the model should be emitted.
            self.assertIn("completed the research loop", full_text)
            # The summary path used generate_response exactly once.
            self.assertEqual(mock_adapter.generate_response.call_count, 1)
            # Final summary from the model should be emitted.
            self.assertIn("completed the research loop", full_text)

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_danger_tool_safety_interception_and_timeout(self, mock_planner, mock_adapter, mock_session_local):
        """Test that dangerous tools trigger approval, and timeout acts as rejection."""
        # Mock DB query to return None (so auto_approve is False)
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["CODER"]}')
        
        # Simulate Coder agent calling a dangerous execute_python tool
        async def mock_stream_danger(*args, **kwargs):
            yield {"type": "tool_call", "name": "execute_python", "args": {"code": "print('hello')"}}
            
        mock_adapter.generate_stream.side_effect = [
            mock_stream_danger(),
            # After tool execution feedback, return final answer
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]
        
        # Mock tool planner to queue and raise TimeoutError on approval
        mock_planner.queue_tool.return_value = {"request_id": "req_123", "tool_name": "execute_python"}
        mock_planner.wait_for_approval.side_effect = asyncio.TimeoutError()
        
        context_history = []
        events = []
        
        async for chunk in execute_workflow("session_123", "Run script", context_history):
            if isinstance(chunk, dict):
                events.append(chunk)
                
        # Verify approval card event was yielded
        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        
        # Verify that permission was denied in context memory due to timeout
        func_entry = next((m for m in context_history if m.get("role") == "function"), None)
        self.assertIsNotNone(func_entry)
        self.assertIn("Permission denied", func_entry["content"])

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_pc_process_kill_requires_approval(self, mock_planner, mock_adapter, mock_session_local):
        """pc(action="process_kill") shares its func_name ("pc") with every harmless
        pc action, so it must be explicitly action-checked — a plain func_name-in-
        DANGER_TOOLS lookup would silently bypass the approval gate."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_kill(*args, **kwargs):
            yield {"type": "tool_call", "name": "pc", "args": {"action": "process_kill", "name": "notepad"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_kill(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        mock_planner.queue_tool.return_value = {"request_id": "req_456", "tool_name": "pc"}
        mock_planner.wait_for_approval.side_effect = asyncio.TimeoutError()

        context_history = []
        events = []

        async for chunk in execute_workflow("session_123", "notepad process ta kill koro", context_history):
            if isinstance(chunk, dict):
                events.append(chunk)

        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        func_entry = next((m for m in context_history if m.get("role") == "function"), None)
        self.assertIsNotNone(func_entry)
        self.assertIn("Permission denied", func_entry["content"])

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_mcp_configuration_requires_approval(
        self, mock_planner, mock_adapter, mock_session_local
    ):
        """Configuring an MCP package persists a future external code launch,
        so it must not bypass the explicit approval gate."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_configure_mcp(*args, **kwargs):
            yield {
                "type": "tool_call",
                "name": "configure_mcp_server",
                "args": {"server_name": "demo", "npm_package": "@demo/mcp"},
            }

        mock_adapter.generate_stream.side_effect = [
            mock_stream_configure_mcp(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration)),
        ]
        mock_planner.queue_tool.return_value = {
            "request_id": "req_mcp_config",
            "tool_name": "configure_mcp_server",
            "risk_level": "HIGH",
        }
        mock_planner.wait_for_approval.side_effect = asyncio.TimeoutError()

        config_tool = MagicMock()
        config_tool.__name__ = "configure_mcp_server"
        context_history = []
        events = []
        with patch('backend.brain.agents.agent_team.get_maya_tools', return_value=[config_tool]):
            async for chunk in execute_workflow(
                "session_mcp_config", "configure an MCP server", context_history
            ):
                if isinstance(chunk, dict):
                    events.append(chunk)

        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        config_tool.assert_not_called()
        func_entry = next((m for m in context_history if m.get("role") == "function"), None)
        self.assertIsNotNone(func_entry)
        self.assertIn("Permission denied", func_entry["content"])

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_pc_shutdown_requires_approval(self, mock_planner, mock_adapter, mock_session_local):
        """pc(action="shutdown") must require approval, same as process_kill."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_shutdown(*args, **kwargs):
            yield {"type": "tool_call", "name": "pc", "args": {"action": "shutdown"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_shutdown(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        mock_planner.queue_tool.return_value = {"request_id": "req_789", "tool_name": "pc"}
        mock_planner.wait_for_approval.side_effect = asyncio.TimeoutError()

        context_history = []
        events = []
        async for chunk in execute_workflow("session_123", "PC shutdown koro", context_history):
            if isinstance(chunk, dict):
                events.append(chunk)

        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        func_entry = next((m for m in context_history if m.get("role") == "function"), None)
        self.assertIsNotNone(func_entry)
        self.assertIn("Permission denied", func_entry["content"])

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_plain_shutdown_executes_unified_pc_after_approval(
        self, mock_planner, mock_adapter, mock_session_local
    ):
        """Plain "Shutdown koro" must not depend on the model to discover the tool."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        mock_planner.queue_tool.return_value = {
            "request_id": "req_plain_shutdown",
            "tool_name": "pc",
            "args": {"action": "shutdown"},
            "risk_level": "HIGH",
        }
        mock_planner.wait_for_approval = AsyncMock(return_value=True)

        with patch(
            'backend.tools.unified.pc',
            return_value='OK: shutting down in 5s',
        ) as pc_tool:
            context_history = []
            events = []
            text_chunks = []
            async for chunk in execute_workflow(
                "session_plain_shutdown", "Shutdown koro", context_history
            ):
                if isinstance(chunk, dict):
                    events.append(chunk)
                elif isinstance(chunk, str):
                    text_chunks.append(chunk)

        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        pc_tool.assert_called_once_with(action="shutdown")
        mock_adapter.generate_stream.assert_not_called()
        self.assertIn("shutdown hobe", "".join(text_chunks))

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_file_delete_requires_approval(self, mock_planner, mock_adapter, mock_session_local):
        """Audit finding: the unified `file` tool's delete shares func_name "file"
        with harmless write/read/ls actions, so it needs an explicit action-check.
        file(action="delete") must round-trip the approval gate, not run instantly."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_delete(*args, **kwargs):
            yield {"type": "tool_call", "name": "file",
                   "args": {"action": "delete", "src": "C:/Users/palni/Desktop/resume.pdf"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_delete(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        mock_planner.queue_tool.return_value = {"request_id": "req_del", "tool_name": "file"}
        mock_planner.wait_for_approval.side_effect = asyncio.TimeoutError()

        context_history = []
        events = []
        async for chunk in execute_workflow("session_del", "delete the file at C:/Users/palni/Desktop/resume.pdf", context_history):
            if isinstance(chunk, dict):
                events.append(chunk)

        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        func_entry = next((m for m in context_history if m.get("role") == "function"), None)
        self.assertIsNotNone(func_entry)
        self.assertIn("Permission denied", func_entry["content"])

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_direct_os_action_respects_perm_system_off(self, mock_adapter, mock_session_local):
        """Audit B5: when PERM_SYSTEM is disabled, deterministic zero-LLM OS
        controls must NOT run; the request falls through to the LLM path."""
        mock_db, fake_decrypt = _mock_session_with_system_perm(enabled=False)
        mock_session_local.return_value = mock_db

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_battery(*args, **kwargs):
            yield {"type": "tool_call", "name": "pc", "args": {"action": "battery"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_battery(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        with patch('backend.database.crypto.crypto_manager.decrypt', side_effect=fake_decrypt), \
             patch('backend.brain.agents.agent_team.get_maya_tools') as mock_get_tools:
            mock_tool = MagicMock()
            mock_tool.__name__ = "pc"
            mock_tool.return_value = "Battery: 80%"
            mock_get_tools.return_value = [mock_tool]

            context_history = []
            events = []
            # Short enough for the zero-LLM path, but PERM_SYSTEM off should force LLM.
            async for chunk in execute_workflow("session_ps", "battery koto", context_history):
                if isinstance(chunk, dict):
                    events.append(chunk)

            # Tool must have run through the LLM loop, not the direct fast path.
            self.assertTrue(any(
                e.get("type") == "agent_status" and
                "OS Executor" in e.get("data", {}).get("active_agent", "")
                for e in events
            ))

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_direct_os_action_runs_when_perm_system_missing(self, mock_adapter):
        """Default behavior: missing PERM_SYSTEM preference is treated as enabled
        so existing users do not lose instant volume/brightness/etc. controls."""
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        with patch('backend.tools.desktop.advanced.system_tools.change_volume') as mock_volume, \
             patch('backend.brain.agents.agent_team._is_pref_true', return_value=True):
            mock_volume.return_value = "OK: volume 50%"
            context_history = []
            async for chunk in execute_workflow("session_vol", "volume 50 koro", context_history):
                pass
            mock_volume.assert_called_once()

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_file_write_does_not_require_approval(self, mock_planner, mock_adapter, mock_session_local):
        """Counterpart: file(action="write") must stay frictionless (no approval) —
        gating saves/writes would reintroduce the 'it won't save my file' failure."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_write(*args, **kwargs):
            yield {"type": "tool_call", "name": "file",
                   "args": {"action": "write", "src": "C:/Users/palni/Desktop/new.txt", "dst": "hi"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_write(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        context_history = []
        events = []
        async for chunk in execute_workflow("session_wr", "save hi to desktop new.txt", context_history):
            if isinstance(chunk, dict):
                events.append(chunk)

        # No approval prompt should ever be raised for a write.
        self.assertFalse(any(e.get("type") == "tool_call_request" for e in events))
        mock_planner.queue_tool.assert_not_called()

    @patch('backend.database.connection.SessionLocal')
    @patch('backend.brain.agents.agent_team.gemini_adapter')
    @patch('backend.brain.agents.agent_team.tool_planner')
    async def test_perform_shortcut_restart_requires_approval(self, mock_planner, mock_adapter, mock_session_local):
        """perform_shortcut(action="restart") must require approval — it shares
        its func_name with lock/mute/sleep/hibernate, which do NOT (lock/mute
        are instant+reversible; only the harder-to-reverse power actions gate)."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_restart(*args, **kwargs):
            yield {"type": "tool_call", "name": "perform_shortcut", "args": {"action": "restart"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_restart(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        mock_planner.queue_tool.return_value = {"request_id": "req_101", "tool_name": "perform_shortcut"}
        mock_planner.wait_for_approval.side_effect = asyncio.TimeoutError()

        context_history = []
        events = []
        async for chunk in execute_workflow("session_123", "PC restart koro", context_history):
            if isinstance(chunk, dict):
                events.append(chunk)

        self.assertTrue(any(e.get("type") == "tool_call_request" for e in events))
        func_entry = next((m for m in context_history if m.get("role") == "function"), None)
        self.assertIsNotNone(func_entry)
        self.assertIn("Permission denied", func_entry["content"])

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_perform_shortcut_lock_skips_approval(self, mock_adapter):
        """perform_shortcut(action="lock") is instant/reversible — must NOT gate."""
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_lock(*args, **kwargs):
            yield {"type": "tool_call", "name": "perform_shortcut", "args": {"action": "lock"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_lock(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        with patch('backend.brain.agents.agent_team.get_maya_tools') as mock_get_tools:
            mock_tool = MagicMock()
            mock_tool.__name__ = "perform_shortcut"
            mock_tool.return_value = "OK: locked"
            mock_get_tools.return_value = [mock_tool]

            context_history = []
            events = []
            # Phrasing kept to 8 words so the zero-LLM direct-lock fast path
            # (which bails above 6 words) doesn't intercept it — this exercises
            # the LLM tool-call loop's approval gate instead.
            async for chunk in execute_workflow("session_123", "amar laptop ta ekhoni lock kore dao please", context_history):
                if isinstance(chunk, dict):
                    events.append(chunk)

            self.assertFalse(any(e.get("type") == "tool_call_request" for e in events))

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_pc_network_action_skips_approval(self, mock_adapter):
        """A harmless pc action (network) must NOT trigger the danger-tool gate.
        Uses "network" rather than "battery"/"lock" since those two now have their
        own zero-LLM deterministic fast path and would never reach generate_stream."""
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["OS_EXECUTOR"]}')

        async def mock_stream_network(*args, **kwargs):
            yield {"type": "tool_call", "name": "pc", "args": {"action": "network"}}

        mock_adapter.generate_stream.side_effect = [
            mock_stream_network(),
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]

        with patch('backend.brain.agents.agent_team.get_maya_tools') as mock_get_tools:
            mock_tool = MagicMock()
            mock_tool.__name__ = "pc"
            mock_tool.return_value = "Host: PC\nIP: 10.0.0.1"
            mock_get_tools.return_value = [mock_tool]

            context_history = []
            events = []
            async for chunk in execute_workflow("session_123", "network status dekhao", context_history):
                if isinstance(chunk, dict):
                    events.append(chunk)

            self.assertFalse(any(e.get("type") == "tool_call_request" for e in events))

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_tool_output_truncation(self, mock_adapter):
        """Test that tool outputs exceeding 3000 characters are safely truncated."""
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["CODER"]}')
        
        async def mock_stream_read_file(*args, **kwargs):
            yield {"type": "tool_call", "name": "read_file", "args": {"path": "large.txt"}}
            
        mock_adapter.generate_stream.side_effect = [
            mock_stream_read_file(),
            # Return empty response for next turn
            AsyncMock(__anext__=AsyncMock(side_effect=StopAsyncIteration))
        ]
        
        # Create an output larger than 3000 chars
        large_output = "A" * 4000
        
        with patch('backend.brain.agents.agent_team.get_maya_tools') as mock_get_tools:
            mock_tool = MagicMock()
            mock_tool.__name__ = "read_file"
            mock_tool.return_value = large_output
            mock_get_tools.return_value = [mock_tool]
            
            context_history = []
            async for _ in execute_workflow("session_123", "Read file", context_history):
                pass
                
            # Verify the function output in memory was truncated
            func_entry = next((m for m in context_history if m.get("role") == "function"), None)
            self.assertIsNotNone(func_entry)
            self.assertTrue(len(func_entry["content"]) <= 3100) # 3000 + "[output truncated]" message
            self.assertIn("[output truncated]", func_entry["content"])

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_whatsapp_lookup_success_can_continue_to_send_tool(self, mock_adapter):
        """Regression for the Pintu flow: a successful contact lookup must stay in
        OS_EXECUTOR's tool loop so the next round can actually send the message."""
        async def stream_lookup(*args, **kwargs):
            yield {"type": "tool_call", "name": "get_contact_number", "args": {"name": "Pintu"}}

        async def stream_send(*args, **kwargs):
            yield {
                "type": "tool_call",
                "name": "whatsapp_send_message",
                "args": {"contact_name": "919812345678", "message": "hi"},
            }

        async def stream_final(*args, **kwargs):
            yield "Pathiye dilam!"

        sent = []

        def get_contact_number(name):
            return "SUCCESS: Found contact 'Pintu Da' in the WhatsApp synced contacts with phone number: 919812345678."

        def whatsapp_send_message(contact_name, message):
            sent.append((contact_name, message))
            return "SUCCESS: Sent WhatsApp message to 'Pintu Da' (919812345678): hi"

        mock_adapter.generate_stream.side_effect = [
            stream_lookup(),
            stream_send(),
            stream_final(),
        ]

        with patch('backend.brain.agents.agent_team.get_maya_tools', return_value=[
            get_contact_number,
            whatsapp_send_message,
        ]):
            context_history = []
            chunks = []
            async for chunk in execute_workflow("session_pintu_lookup_send", "Pintu ke hi send koro", context_history):
                if isinstance(chunk, str):
                    chunks.append(chunk)

        self.assertEqual(sent, [("919812345678", "hi")])
        self.assertIn("SUCCESS: Sent WhatsApp message", "".join(chunks))
        self.assertEqual(mock_adapter.generate_stream.call_count, 2)

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_contact_pick_clarification_from_lookup_is_relayed_directly(self, mock_adapter):
        async def stream_lookup(*args, **kwargs):
            yield {"type": "tool_call", "name": "get_contact_number", "args": {"name": "Pintu"}}

        def get_contact_number(name):
            return (
                'CLARIFICATION_NEEDED:{"kind":"contact_pick","query":"Pintu",'
                '"candidates":[{"name":"Pintu Da","number":"919812345678"},'
                '{"name":"Pintu Kaku","number":"919811112222"}]}'
            )

        mock_adapter.generate_stream.side_effect = [stream_lookup()]

        with patch('backend.brain.agents.agent_team.get_maya_tools', return_value=[get_contact_number]):
            context_history = []
            chunks = []
            async for chunk in execute_workflow("session_pintu_pick", "Pintu ke hi send koro", context_history):
                if isinstance(chunk, str):
                    chunks.append(chunk)

        full_text = "".join(chunks)
        self.assertIn("Pintu Da", full_text)
        self.assertIn("Pintu Kaku", full_text)
        self.assertEqual(mock_adapter.generate_stream.call_count, 1)

if __name__ == "__main__":
    unittest.main()
