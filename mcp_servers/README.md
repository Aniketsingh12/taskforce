# MCP Servers

Tools are exposed to agents through [Model Context Protocol](https://modelcontextprotocol.io)
servers. This is TaskForce's differentiator: agents get clean, standardized tool
access instead of bespoke per-integration glue.

Each subdirectory is one MCP server exposing a related set of tools.

**Present today:**

| Server | Tools |
|--------|-------|
| `search_server/` | web search |

**Planned** (not in this repo yet): `database_server/` (query app data),
`email_server/` (send / read mail), `slack_server/` (post / read channels).

## How it connects

Today tools are plain async callables registered in
`backend/app/tools/registry.py`, so the platform runs with zero extra processes:

```
agent.tools = ["web_search"]          # configured per-agent in the workflow
        │
        ▼
backend/app/tools/registry.py         # name → async callable (current path)
```

`search_server/server.py` shows that same `web_search` tool re-exposed as a real
MCP server — the drop-in for the full version:

```
agent.tools = ["web_search"]
        │
        ▼
backend/app/tools/mcp_client.py       # ⚠ not implemented yet
        │
        ▼
mcp_servers/search_server/server.py   # the MCP server that owns the tool
```

To wire it up, add `mcp_client.py`, point it at these servers, and register the
tools they expose in the registry.

## Running an MCP server

```bash
pip install "mcp[cli]"
python mcp_servers/search_server/server.py
```
