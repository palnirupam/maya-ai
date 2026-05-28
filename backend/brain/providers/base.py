from abc import ABC, abstractmethod
from typing import AsyncGenerator

class LLMProvider(ABC):
    """
    Abstract base class for all LLM providers (Gemini, OpenAI, Local).
    Ensures that Maya AI can easily swap intelligence engines.
    """
    
    @abstractmethod
    async def generate_response(self, context: list[dict], prompt: str, image_base64: str = None, override_tools: list = None) -> str:
        """Generate a single complete response."""
        pass

    @abstractmethod
    async def generate_stream(self, context: list[dict], prompt: str, image_base64: str = None, override_tools: list = None) -> AsyncGenerator[str, None]:
        """Generate a streaming response for low latency TTS."""
        pass
