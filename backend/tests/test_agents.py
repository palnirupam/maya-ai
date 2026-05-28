import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from backend.brain.agents.agent_defs import AGENTS, ROUTING_PROMPT
from backend.brain.agents.agent_team import execute_workflow
from backend.brain.providers.gemini_adapter import gemini_adapter

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
            mock_stream_coder()
        ]
        
        context_history = []
        chunks = []
        
        async for chunk in execute_workflow("session_123", "Search and write code", context_history):
            if isinstance(chunk, str):
                chunks.append(chunk)
                
        # Verify that both agents executed and produced yields
        full_text = "".join(chunks)
        self.assertIn("Information found on the web.", full_text)
        self.assertIn("Code compiled successfully.", full_text)
        
        # Verify memory update
        self.assertEqual(len(context_history), 1)
        self.assertIn("Information found on the web.", context_history[0]["content"])
        self.assertIn("Code compiled successfully.", context_history[0]["content"])

    @patch('backend.brain.agents.agent_team.gemini_adapter')
    async def test_refinement_loops_max_termination(self, mock_adapter):
        """Test that execution stops if max refinement loops (3) is exceeded."""
        mock_adapter.generate_response = AsyncMock(return_value='{"agents": ["RESEARCHER"]}')
        
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
            
            async for chunk in execute_workflow("session_123", "Loop task", context_history):
                if isinstance(chunk, str):
                    chunks.append(chunk)
                    
            # Verify termination message
            full_text = "".join(chunks)
            self.assertIn("Max refinement loops reached for Researcher Agent", full_text)

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

if __name__ == "__main__":
    unittest.main()
