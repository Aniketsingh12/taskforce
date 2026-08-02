"""Tool layer.

In the full version these are exposed to agents via MCP servers (see
`mcp_servers/`). For the MVP they are plain async callables registered here so
agents can be assigned tools and the orchestrator can invoke them and record
`tools_called` in the trace.
"""

from .registry import TOOL_REGISTRY, get_tool, list_tools

__all__ = ["TOOL_REGISTRY", "get_tool", "list_tools"]
