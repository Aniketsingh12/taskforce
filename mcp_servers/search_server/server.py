"""Example MCP server exposing a web-search tool.

Reference implementation for the full version. Uses FastMCP (the Python MCP
SDK). Run it standalone with:

    pip install "mcp[cli]" httpx
    python server.py

In the full version the backend connects to this over stdio/SSE via
`app/tools/mcp_client.py` (not implemented yet) and registers the exposed tools
so agents can call them. Today the backend uses the in-process equivalent in
`app/tools/registry.py`.
"""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("taskforce-search")


@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web and return a short list of relevant results.

    Args:
        query: The search query.
        max_results: Maximum number of related results to include.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
        )
        resp.raise_for_status()
        data = resp.json()

    lines: list[str] = []
    if abstract := data.get("AbstractText"):
        lines.append(f"Summary: {abstract}")
    for topic in (data.get("RelatedTopics") or [])[:max_results]:
        if text := topic.get("Text"):
            lines.append(f"- {text}")
    return "\n".join(lines) or f"No results for '{query}'."


if __name__ == "__main__":
    mcp.run()
