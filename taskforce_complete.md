# TaskForce — Complete Specification

A platform where users build and deploy teams of AI agents that complete entire business workflows autonomously. Each agent has a role, tools, and instructions; they hand work off to each other like a real team. Built to run on open-source models locally, hosted APIs, or a hybrid of both.

---

## 1. Brief Description

TaskForce turns multi-step knowledge work into repeatable automated pipelines. A user defines a workflow once — content production, research, lead qualification — assigns each step to a specialized agent, and triggers runs manually, on a schedule, or via webhook. Agents execute in order, hand off context, use tools, and deliver a finished result while the user watches the pipeline run live.

This is the premium tier of AI freelance work: clients pay $1,000–5,000+ for production multi-agent systems, and almost no freelancer can build them cleanly with proper tool integration.

---

## 2. Core Workflow

**Setup**
1. User creates a workflow and states the goal
2. User defines agents — role, instructions, tools, model, output format
3. User sets execution order — sequential, parallel, or conditional
4. User sets the trigger — manual, scheduled (cron), or webhook

**Execution**
5. A run is triggered
6. Orchestrator starts the first agent; it works using its tools and produces output
7. Output passes to the next agent as context (the handoff)
8. Agents run in turn; parallel agents run together
9. A final agent assembles or delivers the result
10. Run completes; output and full trace are saved

**Review**
11. User watches the live pipeline (active agent, streaming output)
12. After completion, user reviews each agent's output and the final deliverable
13. User can re-run, tweak an agent, or export

---

## 3. Model Layer — Open Source + APIs (the full picture)

This is the heart of the system. TaskForce supports three modes and routes per-agent.

### Mode A — Fully Local (open-source, $0 inference cost)

Runs on your RTX 4060 (8GB VRAM) via Ollama. Best for privacy-sensitive clients and zero-cost operation.

**Open-source models that fit 8GB VRAM (quantized):**
- **Llama 3.1 8B** (Q4) — solid general reasoning, good default
- **Qwen 2.5 7B / 14B** (Q4) — strong at structured output and tool calling
- **Mistral 7B / Nemo 12B** (Q4) — fast, good for writing
- **Phi-3.5** — tiny, great for classification/routing agents
- **Qwen 2.5 Coder 7B** — for any code-generation agents
- **Gemma 2 9B** — strong reasoning for its size

**Serving options:**
- **Ollama** — simplest, your default for local dev and small workflows
- **vLLM** — higher throughput if you scale, supports batching
- **LM Studio** — GUI alternative for testing

**Reality check on 8GB:** you run ONE 7–9B model at a time comfortably. For multi-agent workflows, agents share the same loaded model (swap prompts, not models) or you queue them. Bigger models (14B+) need quantization and will be slower.

### Mode B — Hosted APIs (paid, highest quality)

For complex reasoning, long context, or when local quality isn't enough.

**API providers to support:**
- **Anthropic Claude** (Haiku / Sonnet / Opus) — strong reasoning + tool use; Haiku is cheap for high-volume agents
- **OpenAI** (GPT-4o-mini / GPT-4o) — mini is cheap and capable for most agents
- **Google Gemini** (Flash / Pro) — Flash is very cheap, huge context
- **Groq** — serves open-source models (Llama, Qwen) at very high speed, cheap — a great middle ground
- **Together AI / Fireworks / DeepInfra** — host open-source models via API; pay per token, no GPU needed, far cheaper than frontier models
- **OpenRouter** — single API to access many models (open + closed); easiest way to let users pick any model

### Mode C — Hybrid (recommended default)

Route each agent to the cheapest model that can do its job well.

| Agent type | Recommended model | Why |
|-----------|-------------------|-----|
| Classifier / Router | Local Phi-3.5 or Llama 8B | Trivial task, free, fast |
| Data extractor / formatter | Local Qwen 7B | Structured output, free |
| Researcher | Gemini Flash or Groq Llama | Needs quality + speed, cheap |
| Writer | Claude Sonnet or GPT-4o | Quality matters, worth paying |
| Editor / Reviewer | Claude Haiku or GPT-4o-mini | Good enough, cheap |
| Fact-checker | Hosted model w/ web search | Accuracy critical |
| Complex reasoner | Claude Opus or GPT-4o | Hardest steps only |

**The routing principle:** local/cheap models for mechanical steps, premium models only where output quality directly affects the deliverable. A 5-agent workflow might use 3 free local agents and 2 paid agents — cutting cost ~60% vs all-premium.

### How model choice is wired

- Each agent stores a `model_choice` (provider + model name)
- A central **model router** in the backend maps that choice to the right client (Ollama / Anthropic / OpenAI / OpenRouter / Groq)
- Users pick per-agent from a dropdown; sensible defaults pre-filled
- **OpenRouter as the unified gateway** is the cleanest design — one integration, users get every model, you don't maintain five SDK integrations. Keep Ollama separate for the free local path.

---

## 4. Example Workflows

**Content pipeline:** Researcher (gathers sources) → Writer (drafts) → Editor (refines) → SEO agent (optimizes) → ready to publish

**Research report:** Planner (breaks down question) → 3 parallel Researchers (subtopics) → Synthesizer (combines) → Fact-checker (verifies) → cited report

**Lead qualification:** Enrichment (company lookup) → Scorer (rates fit) → Personalizer (drafts outreach) → CRM agent (logs it)

**Competitor analysis:** Collector (gathers data) → Analyst (compares) → Reporter (writes summary)

**Support triage:** Classifier (categorizes) → Retriever (finds relevant docs) → Responder (drafts reply) → Escalation agent (flags hard ones)

---

## 5. Features

**Workflow builder**
- Create, name, describe workflows
- Add agents: role, instructions, tools, model, output format
- Execution order: sequential, parallel, conditional
- Save as reusable templates

**Agent configuration**
- Per-agent system instructions
- Per-agent tool assignment (via MCP)
- Per-agent model selection (local or any API)
- Per-agent output format (text, JSON, file)
- Per-agent retry / fallback model (if local fails, fall back to API)

**Execution & orchestration**
- Manual, scheduled (cron), or webhook triggers
- Sequential, parallel, conditional execution
- Context handoff between agents
- Background processing (long runs don't block UI)
- Pause / resume / cancel a run

**Live monitoring**
- Real-time pipeline view — active agent, progress
- Live output streaming per agent
- Status indicators (queued, running, done, failed)

**Run history & outputs**
- Full trace per run — each agent's input, output, tools called, model used, tokens, cost, latency
- Final deliverable download/export
- Re-run with same or modified config

**Tool integration (MCP)**
- Tool library: web search, database, email, Slack, file ops
- Tools exposed via MCP servers
- Add custom tools per workflow

**Cost & observability**
- Cost per run, per agent, per model
- Local vs API cost breakdown (shows savings from local routing)
- Latency per step
- Success/failure rates over time

**Model management**
- Configure available models (local Ollama models + API keys)
- Set default routing rules
- Per-workflow cost cap

**Templates**
- Pre-built workflows (content, research, lead-gen, support) to clone

---

## 6. Project Structure

```
taskforce/
├── frontend/                      # React + Tailwind
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard          # workflow list + run stats
│   │   │   ├── WorkflowBuilder    # define agents, order, tools, models
│   │   │   ├── RunView            # live pipeline visualization
│   │   │   ├── RunHistory         # past runs + outputs + cost
│   │   │   ├── Models             # configure local + API models
│   │   │   └── Settings           # connections, billing, API keys
│   │   ├── components/
│   │   │   ├── AgentCard          # single agent config block
│   │   │   ├── PipelineGraph      # visual flow (React Flow)
│   │   │   ├── LiveTrace          # streaming run status
│   │   │   ├── OutputPanel        # expandable agent output
│   │   │   ├── ToolPicker         # assign tools to an agent
│   │   │   ├── ModelPicker        # pick local/API model per agent
│   │   │   └── CostBadge          # cost display per run/agent
│   │   ├── hooks/                 # data fetching, websocket for live runs
│   │   └── lib/                   # api client, websocket client
│   └── ...
│
├── backend/                       # FastAPI
│   ├── app/
│   │   ├── main.py                # app entry, routers
│   │   ├── api/
│   │   │   ├── workflows.py       # CRUD workflows
│   │   │   ├── runs.py            # trigger runs, status, history
│   │   │   ├── agents.py          # agent config
│   │   │   ├── tools.py           # available tools / MCP registry
│   │   │   ├── models.py          # available models, routing config
│   │   │   └── webhooks.py        # external triggers
│   │   ├── core/
│   │   │   ├── config.py          # settings, env
│   │   │   ├── auth.py            # Supabase auth
│   │   │   └── security.py        # API key storage (encrypted)
│   │   ├── models/                # MODEL LAYER (the key part)
│   │   │   ├── router.py          # routes agent → correct provider
│   │   │   ├── ollama_client.py   # local open-source models
│   │   │   ├── openrouter_client.py # unified API gateway (many models)
│   │   │   ├── anthropic_client.py  # direct Claude (optional)
│   │   │   ├── openai_client.py     # direct OpenAI (optional)
│   │   │   ├── groq_client.py       # fast open-source via API
│   │   │   └── fallback.py        # local-fail → API fallback logic
│   │   ├── orchestration/
│   │   │   ├── engine.py          # orchestration core (LangGraph)
│   │   │   ├── agent.py           # agent definition + execution
│   │   │   ├── handoff.py         # context passing between agents
│   │   │   ├── graph_builder.py   # turn a workflow config into a graph
│   │   │   └── scheduler.py       # cron / scheduled runs
│   │   ├── tools/
│   │   │   ├── mcp_client.py      # connect to MCP servers
│   │   │   ├── web_search.py
│   │   │   ├── database_tool.py
│   │   │   ├── email_tool.py
│   │   │   └── file_tool.py
│   │   ├── tasks/
│   │   │   └── run_tasks.py       # Celery tasks for background runs
│   │   └── db/
│   │       ├── schema.py          # workflows, agents, runs, traces, models
│   │       └── queries.py
│   └── ...
│
├── mcp_servers/                   # MCP servers exposing tools to agents
│   ├── database_server/
│   ├── email_server/
│   ├── search_server/
│   └── slack_server/
│
├── docker-compose.yml             # backend, redis, workers, frontend, ollama
├── .env.example                   # API keys, Supabase, Ollama host
└── README.md
```

---

## 7. Database Schema (conceptual)

- **users** — Supabase auth
- **workflows** — id, user_id, name, description, trigger_type, schedule, cost_cap, created_at
- **agents** — id, workflow_id, role, instructions, tools[], model_provider, model_name, fallback_model, order, parallel_group, output_format
- **runs** — id, workflow_id, status, started_at, finished_at, total_cost, total_tokens, trigger_source
- **traces** — id, run_id, agent_id, input, output, tools_called[], model_used, tokens, cost, latency, status
- **tools** — id, name, description, mcp_server, parameters
- **model_configs** — id, user_id, provider, model_name, is_local, api_key_ref, enabled

---

## 8. Complete Tech Stack

**Frontend**
- React — UI framework
- Tailwind CSS — styling
- React Flow — visual pipeline builder + live run graph (the portfolio wow-factor)
- WebSockets / SSE — live run streaming

**Backend**
- FastAPI — API server
- Python — language
- Pydantic — validation + structured agent outputs

**Agent / Orchestration**
- LangGraph — primary orchestration (stateful, parallel, conditional, handoffs)
- CrewAI — alternative for role-based agents (simpler, less flexible)
- MCP SDK — exposing tools to agents (your differentiator)

**Models — Open Source (local, free)**
- Ollama — serving layer on your RTX 4060
- Models: Llama 3.1 8B, Qwen 2.5 7B/14B, Mistral 7B/Nemo, Phi-3.5, Gemma 2 9B, Qwen Coder
- vLLM — optional higher-throughput serving if you scale

**Models — Open Source (via API, cheap, no GPU)**
- Groq — open-source models at high speed
- Together AI / Fireworks / DeepInfra — hosted open-source models, pay-per-token

**Models — Closed APIs (premium quality)**
- Anthropic Claude (Haiku/Sonnet/Opus)
- OpenAI (GPT-4o-mini/GPT-4o)
- Google Gemini (Flash/Pro)

**Model gateway**
- OpenRouter — single integration for all hosted models (open + closed); cleanest way to offer model choice
- Custom router — directs each agent to Ollama (local) or OpenRouter/direct API

**Background processing**
- Celery — agents run as background jobs
- Redis — task queue + live run state + caching

**Database & Auth**
- Supabase (Postgres) — all app data
- pgvector — agent memory/retrieval if needed
- Supabase Auth — accounts

**Tools layer**
- MCP servers — web search, database, email, Slack, file ops

**Infrastructure**
- Docker + docker-compose — backend, workers, Redis, Ollama, frontend
- Deploy: Railway/Render (backend + workers), Vercel (frontend), Supabase (DB)
- Local Ollama runs on your machine or a connected GPU host

**Observability**
- Cost/token/latency in traces table
- LangSmith — optional deeper agent tracing in dev

---

## 9. Cost Strategy Summary

| Setup | Cost | When to use |
|-------|------|-------------|
| All local (Ollama) | $0 inference | Privacy clients, simple workflows, dev |
| Open-source via Groq/Together | Very low | Need speed/scale without a GPU |
| Hybrid (local + premium API) | Low | Default — quality where it counts |
| All premium API | Highest | Complex, high-stakes deliverables |

The product's selling point to clients: "runs on your own models, your own infrastructure, no data leaves your servers" (local) OR "best quality, pay only for what you use" (API) — you support both, which most competitors don't.

---

## 10. MVP vs Full

**MVP (build first):**
- One hardcoded workflow (content pipeline: Researcher → Writer → Editor)
- Sequential execution only
- Manual trigger
- Two model options: one local (Ollama) + one API (via OpenRouter)
- Live run view + final output + run history
- 2 tools (web search + one more)

**Full version (add later):**
- Custom workflow builder (any agents, any order, parallel/conditional)
- Scheduled + webhook triggers
- Full model router with per-agent choice + fallback
- Template library
- Full cost/observability dashboard
- Custom tool addition per workflow

Ship the MVP, record one real workflow running end to end with the live pipeline view, and that demo is your portfolio centerpiece. A working 3-agent pipeline that runs on both a local and an API model proves the exact skill clients pay premium for.
