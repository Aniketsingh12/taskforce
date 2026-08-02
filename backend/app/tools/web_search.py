"""Web search tool.

Attempts a real DuckDuckGo lookup; if the network is unavailable it returns
clearly-labelled mock results so demos and tests still work offline. In the
full version this is backed by the `search_server` MCP server.
"""

from __future__ import annotations

import httpx


async def web_search(query: str, max_results: int = 5) -> str:
    query = (query or "").strip()
    if not query:
        return "No query provided."

    try:
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
        if lines:
            return "Web search results:\n" + "\n".join(lines)
    except Exception:  # noqa: BLE001 - offline / rate-limited → fall back
        pass

    return (
        f"[mock] Web search results for '{query}':\n"
        "- Result 1: representative source on the topic.\n"
        "- Result 2: secondary source with supporting data.\n"
        "- Result 3: an opposing perspective to consider."
    )
