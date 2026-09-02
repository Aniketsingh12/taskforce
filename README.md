# ⚡ TaskForce

**Build and deploy teams of AI agents that complete entire business workflows autonomously.**

Each agent has a role, tools, and instructions; they hand work off to each other like a real team. Workflows run on **open-source models locally (Ollama, $0)**, **hosted APIs (Together AI, OpenRouter)**, or a **hybrid** that routes each agent to the cheapest model that can do its job.

> Wire a workflow visually on a drag-and-drop canvas — or build it as a list — assign each step to a specialized agent, set a trigger (manual, scheduled, or webhook), and watch the pipeline run live. Output and a full trace (tokens, cost, latency per agent) are saved for every run.

---

## ✨ Features

- 🧩 **Visual canvas builder** — drag out agent nodes, wire them together (ComfyUI-style), and the graph compiles into the engine's execution stages automatically; a list view covers the same ground without the canvas
- 🔀 **Parallel & conditional execution** — agents at the same graph depth run concurrently; agents can be skipped by a condition (e.g. escalate only when flagged)
- 🛠 **Model-driven tool calling (ReAct)** — the model decides whether to call a tool, with what arguments, and whether to call another after seeing the result, bounded by `max_tool_steps`; providers without tool support fall back to simpler staged tool use
- 🧠 **Per-agent model routing** — `ollama` (local/free), `together` (hosted open-source), `openrouter` (hosted gateway), `mock` (offline demo) — with **key-aware fallback** that only ever falls back to a provider that's actually configured
- 🧾 **Structured JSON output** — `output_format="json"` is enforced, not just requested: prose-wrapped or fenced JSON is extracted from the model's reply, and an unparseable reply triggers one auto-retry with a correction nudge
- ⚡ **Triggers** — manual, **scheduled (cron)**, or **webhook**
- 📺 **Live run view** — watch each agent light up and stream output token-by-token over WebSocket, including live tool-call events
- 📜 **Run history & traces** — per-agent input, output, tools called, model, tokens, cost, latency
- 📊 **Observability dashboard** — success rate, total cost/tokens, **local-vs-API cost split**, average latency
- 🔧 **Tool integration** — web search + file output today, MCP servers as the integration point
- 📚 **Template library** — 4 ready-to-clone workflows (content, research, lead-gen, support)
- 💪 **Crash-resilient runs** — per-agent retries with bounded timeouts, and any run still "running" after a crash/restart is reconciled to `failed` on the next boot instead of hanging forever
- 🔐 **Public-demo access control** — an admin token gates mutations and billed models; a spend cap and a rate limiter protect a publicly-shared deployment from runaway cost (see [below](#-public-demo-access-control))
- 💾 **Persistence** — SQLite out of the box (zero setup, WAL mode), Supabase/Postgres as the production target

**Runs out of the box with no API keys and no GPU** — the built-in `mock` model produces realistic streaming output (and simulated tool calls) so you can demo the entire platform offline.

---

## 🚀 Quick start

### Option A — One command (full app, no Docker)

```bash
python run.py            # first time: python run.py --install
```

Starts the backend (FastAPI, autoreload) and frontend (Vite) together, prefixes both logs in one terminal, and stops both on Ctrl+C. Hops to a free port automatically if 8000 is taken. Open **http://localhost:5173** — run a template live, **clone** it, or build your own on the **Canvas**.

### Option B — Backend-only demo (no UI, no Docker)

```bash
cd backend
pip install -r requirements.txt
python demo.py "How AI agents are changing freelance work"
```

The Researcher → Writer → Editor pipeline runs end to end, streaming each agent's output with a cost/latency summary.

### Option C — Two terminals (manual)

**Terminal 1 — backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm install
npm run dev
```

Same result as Option A, run by hand — useful if you want the two logs in separate terminals.

### Option D — Docker Compose (backend + frontend + Ollama)

```bash
cp .env.example .env        # optional: add TOGETHER_API_KEY / OPENROUTER_API_KEY for hosted models
docker compose up --build
```
- Frontend → http://localhost:5173 · Backend → http://localhost:8000/docs · Ollama → http://localhost:11434
- Pull a local model: `docker compose exec ollama ollama pull llama3.1:8b`

### Option E — Single-service production image

The root [`Dockerfile`](Dockerfile) builds the frontend and copies it into the same FastAPI process that serves the API — one image, one URL, same-origin (no CORS split needed). This is the image deployed to Railway; see [Deployment](#-deployment) below.

---

## 🧠 The model layer (the heart of the system)

Each agent stores a `model_provider` + `model_name`. A central **router** (`backend/app/models/router.py`) maps that choice to the right client:

| Provider | Client | Use |
|----------|--------|-----|
| `ollama` | `ollama_client.py` | Local open-source models on your GPU — **$0 inference** |
| `together` | `together_client.py` | Open-source models (Llama, DeepSeek, Qwen…) via Together AI's API — cheap, no GPU needed |
| `openrouter` | `openrouter_client.py` | One key → Claude, GPT, Gemini, Groq-served Llama, … |
| `mock` | `mock_client.py` | Offline demo / tests — realistic streaming, zero setup |

**Fallback is key-aware:** if a primary provider fails (Ollama down, missing key, quota), the router retries once on a backup provider (`fallback.py`) — but only a provider that's actually configured (`provider_is_usable()` checks the relevant API key is set). An explicit per-agent `fallback_model` naming an unconfigured provider is skipped rather than trusted blindly, so a run degrades to `mock` instead of crashing outright. The global chain defaults to `mock` so a run always completes, and the trace records the fallback.

**Hybrid routing principle:** local/cheap models for mechanical steps (classify, extract, format), premium models only where output quality is the deliverable. A 5-agent workflow might use 3 free local agents + 2 paid agents — cutting cost ~60% vs all-premium. The dashboard's local-vs-API split makes the savings visible.

---

## 🔀 Execution modes

The engine (`backend/app/orchestration/engine.py`) runs a workflow as ordered **stages**:

- **Sequential** — agents with no `parallel_group` run one after another, handing context forward.
- **Parallel** — agents sharing a `parallel_group` run concurrently (`asyncio.gather`); they see the same prior context, not each other.
- **Conditional** — an agent with a `condition` runs only if that phrase appears in prior output (prefix `!` to invert). Skipped agents are recorded and excluded from handoff and from the cost dashboard.

The node/edge stage model mirrors a LangGraph `StateGraph`, so LangGraph can be swapped in without changing the API or the live event contract.

**Canvas → stages:** when a workflow is built visually, `orchestration/graph.py` compiles the node/edge graph into that stage model by computing each agent's longest-path depth (Kahn's algorithm) — agents at the same depth become a parallel group, and a graph with a cycle is rejected outright rather than silently misordered.

**Reliability:** each agent's call is wrapped in a bounded `asyncio.timeout` and retried up to `max_retries` times, discarding any partial output from a failed attempt rather than splicing it with the retry. A run still marked `running` after a crash or restart is reconciled to `failed` on the next boot (`store.reconcile_interrupted_runs()`), so a killed process never leaves a run stuck open forever.

---

## 🔌 API

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/health` | Health check |
| `GET`/`POST` | `/api/workflows` | List / create workflows |
| `GET`/`PUT`/`DELETE` | `/api/workflows/{id}` | Get / update / delete |
| `POST` | `/api/workflows/{id}/clone` | Duplicate (e.g. a template) into an editable copy |
| `POST` | `/api/runs/trigger` | Start a run (background) → `{run_id}` |
| `GET`  | `/api/runs` · `/api/runs/{id}` | History · full run + traces |
| `WS`   | `/api/runs/ws` | Start a run **and** stream it live |
| `WS`   | `/api/runs/ws/{run_id}` | Subscribe to a run started via `/trigger` |
| `POST` | `/api/webhooks/{workflow_id}` | External trigger — body becomes the run input |
| `GET`  | `/api/models` · `/api/tools` | Available models (with pricing) · tools |
| `GET`  | `/api/stats` | Aggregate observability for the dashboard |
| `GET`  | `/api/auth/status` | Current access mode (admin vs. demo), and — admin only — today's spend |

Interactive docs at `/docs`. **Live event stream:** `run_started` → `agent_started` → `token`×N / `tool_call` → `agent_completed` / `agent_skipped` / `agent_retry` → … → `run_completed` | `run_failed` | `error`.

Mutating routes (`POST`/`PUT`/`DELETE` on `/api/workflows`) require the admin token once one is configured — see below. Reading and running stay public so a shared demo keeps working.

Scheduled workflows (`trigger_type: "schedule"` + a cron `schedule`) fire automatically via the in-process scheduler.

---

## 🔐 Public-demo access control

A deployed instance is publicly reachable, so it ships with three layers that let you **share the link safely**. All of them are **off when `ADMIN_TOKEN` is unset**, so local dev is unchanged.

| Layer | Env var | Controls |
|---|---|---|
| Admin token | `ADMIN_TOKEN` | who can mutate data and use billed models (`backend/app/core/security.py`, constant-time compare) |
| Spend cap | `DAILY_COST_LIMIT_USD` | **your maximum bill** — the real backstop, checked against actual run cost summed since UTC midnight |
| Rate limit | `RATE_LIMIT_RUNS` | how fast one IP can trigger runs (`backend/app/core/ratelimit.py`, in-process sliding window) |

With a token set, an anonymous visitor can still **browse and run every workflow live** — but their runs are forced onto the free `mock` provider (`_as_demo()` deep-copies the workflow, overrides every agent's provider/model, and clears any billed `fallback_model`, without touching the stored original), and create/edit/clone/delete all return `401`. The `/api/models` catalog is restricted too — Together's live list is fetched with *your* key and Ollama's list reflects *your* server, so neither is account-safe to hand to a stranger; a visitor sees only the one demo model they're allowed to run. Visitors still see token streaming, tool calling, parallel stages, and the full cost trace, so the demo stays compelling at exactly $0. Unlock real models and editing with the token via the header (`X-Admin-Token`) or the lock button in the app header — a WebSocket run sends it in the first JSON message instead, since browsers can't set custom headers on the socket handshake.

Only the spend cap genuinely bounds cost: a rate limit caps one client's velocity, not total spend across many honest visitors, and per-IP counting (via `X-Forwarded-For`) is defeated by a proxy. The rate limiter is also in-process — it resets on redeploy and doesn't span replicas. Set a provider-side limit in your model vendor's dashboard too — that's the only cap that survives a bug in this code.

```bash
ADMIN_TOKEN=$(openssl rand -hex 24)   # then set it in your host's env vars
```

---

## 🗂 Project structure

```
taskforce/
├── run.py                         # ⭐ single-command launcher — backend + frontend together
├── Dockerfile                     # single-service production image (frontend baked into the API)
├── docker-compose.yml             # backend + frontend + ollama, for local Docker dev
├── backend/                       # FastAPI
│   ├── app/
│   │   ├── main.py                # routers, template seeding, scheduler start, SPA static serving
│   │   ├── api/
│   │   │   ├── auth.py            # /api/auth/status — admin vs. demo, spend (admin only)
│   │   │   ├── workflows.py       # CRUD + clone, admin-gated mutations
│   │   │   ├── runs.py            # trigger + WS streaming, demo forcing, budget/rate checks
│   │   │   ├── models.py          # /api/models (admin-scoped catalog) + /api/tools
│   │   │   ├── stats.py           # dashboard aggregates
│   │   │   └── webhooks.py        # external triggers
│   │   ├── core/
│   │   │   ├── config.py          # settings (env-driven, absolute .env path resolution)
│   │   │   ├── security.py        # admin check, budget/rate enforcement, client IP
│   │   │   └── ratelimit.py       # in-process sliding-window rate limiter
│   │   ├── models/                # ⭐ MODEL LAYER
│   │   │   ├── router.py          # routes agent → provider, applies key-aware fallback
│   │   │   ├── ollama_client.py · together_client.py · openrouter_client.py · mock_client.py
│   │   │   └── fallback.py        # local-fail → API fallback, provider_is_usable() guard
│   │   ├── orchestration/
│   │   │   ├── engine.py          # sequential + parallel + conditional stages
│   │   │   ├── agent.py           # single-agent execution: retries, timeouts, tools, streaming
│   │   │   ├── react.py           # model-driven tool calling (ReAct) loop
│   │   │   ├── graph.py           # canvas node/edge graph → execution stages
│   │   │   ├── output.py          # JSON extraction from prose/fenced model output
│   │   │   ├── handoff.py         # context passing between agents
│   │   │   ├── scheduler.py · cron.py   # scheduled (cron) triggers
│   │   │   └── templates.py       # 4 built-in workflows
│   │   ├── tools/                 # web_search, file output, registry (MCP-ready)
│   │   ├── db/                    # schema (Pydantic) + SQLite store (WAL, traces table)
│   │   └── ws.py                  # live run event broker
│   ├── demo.py                    # run the pipeline from the CLI
│   └── tests/                     # 66 tests across 11 files — see Tests below
│
├── frontend/                      # React + Tailwind + Vite
│   └── src/
│       ├── pages/                 # Dashboard, WorkflowBuilder, Models, RunView, RunHistory
│       ├── components/
│       │   ├── GraphEditor.jsx    # ⭐ drag-and-drop canvas (@xyflow/react)
│       │   ├── PipelineGraph.jsx  # read-only run visualization
│       │   ├── LiveTrace.jsx · AgentCard.jsx · ModelPicker.jsx · ToolPicker.jsx
│       │   ├── CostBadge.jsx · StatsBar.jsx
│       │   └── AccessBadge.jsx    # admin unlock/lock control in the header
│       └── lib/                   # api.js (client), ws.js (websocket), auth.jsx (admin token context)
│
├── mcp_servers/                   # MCP servers exposing tools to agents
│   └── search_server/             # example: web search over MCP
│
└── .env.example
```

---

## 🧪 Tests

```bash
cd backend
pip install -r requirements-dev.txt   # pytest + pytest-asyncio (pulls in requirements.txt)
python -m pytest -q                   # 66 passing
```

| File | Covers |
|---|---|
| `test_access.py` (16) | admin gating, demo forcing, model-catalog privacy, spend cap, rate limiting |
| `test_engine.py` (5) | sequential/parallel/conditional stage execution, fallback chain |
| `test_graph.py` (8) | canvas graph → stage compilation, depth computation, cycle detection |
| `test_output.py` (8) | JSON extraction from prose/fences, repair-nudge retry |
| `test_react.py` (4) | ReAct tool-call loop, usage accumulation, streamed tool-call reassembly |
| `test_reliability.py` (5) | retries, timeouts, partial-output discard, crash recovery on boot |
| `test_tools_and_stats.py` (4) | pre/post-stage tools, skipped-agent stats exclusion |
| `test_clients.py` (6) | Ollama + OpenRouter clients against a mock HTTP transport |
| `test_cron.py` (5) | cron schedule matching |
| `test_orchestrator.py` (2) | context handoff between agents |
| `test_api.py` (3) | HTTP surface smoke tests |

No network required — every provider client is tested against a mocked transport, not a live API.

---

## 🛠 Tech stack

**Frontend:** React · Tailwind CSS · Vite · React Router · `@xyflow/react` (drag-and-drop canvas) · WebSockets (live streaming)
**Backend:** FastAPI · Python · Pydantic v2 · pydantic-settings
**Orchestration:** custom stage engine (sequential/parallel/conditional; LangGraph-shaped) · model-driven ReAct tool calling
**Models — local:** Ollama (Llama 3.1, Qwen 2.5, Mistral/Nemo, Phi-3.5, Gemma 2…)
**Models — hosted:** Together AI (open-source models, live catalog) · OpenRouter gateway (Claude, GPT, Gemini, Groq-served open-source)
**Tools:** MCP servers (web search, database, email, Slack, file ops)
**Data:** SQLite (default, WAL mode) → Supabase/Postgres + pgvector (production)
**Scheduling:** in-process cron scheduler → Celery beat at scale
**Infra:** single-service Docker image (Railway) or Docker Compose for local dev

---

## 💰 Cost strategy

| Setup | Cost | When |
|-------|------|------|
| All local (Ollama) | $0 inference | Privacy clients, simple workflows, dev |
| Open-source via Together AI | Very low | Speed/scale without a GPU |
| **Hybrid (local + premium API)** | **Low** | **Default — quality where it counts** |
| All premium API (OpenRouter) | Highest | Complex, high-stakes deliverables |

**The pitch to clients:** *"runs on your own models, your own infrastructure, no data leaves your servers"* (local) **OR** *"best quality, pay only for what you use"* (API) — TaskForce supports both, which most competitors don't.

---

## 🚢 Deployment

The root [`Dockerfile`](Dockerfile) builds the frontend and bakes it into the same FastAPI process that serves the API (`backend/app/main.py` mounts `static/` when present) — one service, one URL, no CORS split. Deployed to **Railway** (Hobby plan):

1. New service → deploy from this repo, **Root Directory = `.`** (repo root, not `backend/`) so the build sees both `frontend/` and `backend/`.
2. Add a **persistent volume** mounted where `DB_PATH` points (e.g. `/data/taskforce.db`) — without one, every redeploy wipes the database.
3. Set env vars: at minimum `ADMIN_TOKEN` (see [access control](#-public-demo-access-control) above) and whichever model provider keys you're using (`TOGETHER_API_KEY`, `OPENROUTER_API_KEY`, or point `OLLAMA_HOST` at a reachable server). `CORS_ORIGINS` isn't needed for the single-service setup — same-origin has no CORS to configure.
4. Generate a domain (Railway gives you one free `*.up.railway.app` domain per service, or attach your own).

`backend/Procfile` (`web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`) is there for platforms that run a Procfile instead of the Dockerfile directly.

---

## 🗺 Status

**Done:**
- [x] Visual canvas builder (drag/drop/wire agents) + a list-mode alternative
- [x] Sequential, **parallel**, and **conditional** execution
- [x] Manual, **scheduled (cron)**, and **webhook** triggers
- [x] Per-agent model choice + key-aware fallback (local · Together · OpenRouter · demo)
- [x] Model-driven tool calling (ReAct), with a staged fallback for providers that can't
- [x] Enforced JSON structured output with auto-retry on unparseable replies
- [x] Live run view with token streaming + live tool-call events over WebSocket
- [x] Run history with full per-agent traces
- [x] Cost / observability dashboard (local-vs-API split, skipped agents excluded correctly)
- [x] Template library (content · research · lead-gen · support)
- [x] SQLite persistence (WAL mode)
- [x] Tools (web search, file) + an example MCP server
- [x] Per-agent retries, bounded timeouts, and crash recovery for interrupted runs
- [x] Public-demo access control (admin token, spend cap, rate limit, restricted model catalog)
- [x] Single-service Docker image + Railway deployment
- [x] Single-command local launcher (`run.py`)

**Known limitations:**
- [ ] **Rate limiting is in-process.** Resets on every redeploy and doesn't share state across replicas — a speed bump, not a hard guarantee. The spend cap is the control that actually bounds cost.
- [ ] **Client IP detection trusts `X-Forwarded-For`.** Correct behind Railway's proxy, but spoofable if the app is ever exposed directly.
- [ ] **Together AI doesn't return per-model pricing** from its catalog endpoint, so its listed cost is `0`/`n/a`; real token counts are still recorded per run.
- [ ] **Webhook auth is optional** (`WEBHOOK_SECRET` unset = open) — set it before relying on webhooks in production.

**Production hardening (next):**
- [ ] Supabase persistence + real user auth (swap the SQLite store and the shared admin token)
- [ ] Celery + Redis for distributed background runs and scheduling (today's scheduler assumes a single instance)
- [ ] Full MCP tool library (database, email, Slack) + custom tools per workflow
- [ ] LangGraph engine for richer branching/looping
- [ ] Distributed rate limiting (Redis-backed) once running more than one replica

---

## 📄 License

MIT — see `taskforce_complete.md` for the full product vision.
