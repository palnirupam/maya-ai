import logging
from typing import Dict
from .providers.base import LLMProvider
from .providers.gemini_adapter import GeminiAdapter

logger = logging.getLogger(__name__)

class ConversationOrchestrator:
    """
    Manages conversation memory, session context, and routes queries 
    to the appropriate LLM provider.
    """
    def __init__(self):
        self.provider: LLMProvider = GeminiAdapter()
        self.sessions: Dict[str, list[dict]] = {}
        self.MAX_MEMORY_WINDOW = 20

    def get_session(self, session_id: str, initial_context: str = "") -> list[dict]:
        if session_id not in self.sessions:
            from .personality.maya_personality import prompt_builder
            from .memory.long_term_memory import build_memory_context_block
            from ..system.state_manager import state_manager
            
            system_prompt = prompt_builder.get_system_prompt()
            memory_block = build_memory_context_block(
                active_category=state_manager.state.active_mode, 
                context_text=initial_context
            )
            
            if memory_block:
                system_prompt += "\n" + memory_block
                
            self.sessions[session_id] = [
                {"role": "system", "content": system_prompt}
            ]
        return self.sessions[session_id]

    def add_to_memory(self, session_id: str, role: str, content: str, reasoning_content: str = None):
        session = self.get_session(session_id, initial_context=content if role == "user" else "")
        msg = {"role": role, "content": content}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        session.append(msg)
        
        # Enforce memory window limit
        if len(session) > self.MAX_MEMORY_WINDOW:
            # Keep system prompt, remove oldest messages
            self.sessions[session_id] = [session[0]] + session[-(self.MAX_MEMORY_WINDOW-1):]

    async def process_user_input(self, session_id: str, text: str, image_base64: str = None) -> str:
        """Process a full text input from the user and get a response."""
        logger.info(f"Processing input for session {session_id}: {text}")
        
        self.add_to_memory(session_id, "user", text)
        context = self.get_session(session_id)
        
        # In a real pipeline, we might stream this directly to the TTS router.
        # For now, we fetch the full response.
        response_text = await self.provider.generate_response(context, text, image_base64)
        
        self.add_to_memory(session_id, "assistant", response_text)
        return response_text
        
    async def process_user_input_stream(self, session_id: str, text: str, image_base64: str = None):
        """Process input and stream the response back in chunks, delegating to the Multi-Agent team workflow."""
        logger.info(f"Streaming input for session {session_id} using multi-agent workflow: {text}")
        
        self.add_to_memory(session_id, "user", text)
        context_history = self.get_session(session_id)
        
        from .agents import agent_team
        
        async for chunk in agent_team.execute_workflow(
            session_id=session_id, 
            text=text, 
            context_history=context_history, 
            image_base64=image_base64
        ):
            yield chunk

orchestrator = ConversationOrchestrator()
