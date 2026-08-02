"""Model layer — routes each agent to the right provider.

Ollama (local, free) | OpenRouter (unified hosted gateway) | mock (offline demo).
The router maps an agent's (provider, model) choice to a concrete client.
"""

from .base import ChatMessage, ModelClient, StreamResult, Usage
from .router import ModelRouter, get_router

__all__ = ["ChatMessage", "ModelClient", "StreamResult", "Usage", "ModelRouter", "get_router"]
