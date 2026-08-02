# ⚡ TaskForce

**Build and deploy teams of AI agents that complete entire business workflows autonomously.**

Each agent has a role, tools, and instructions; they hand work off to each other like a real team. Workflows run on **open-source models locally (Ollama, $0)**, **hosted APIs (via OpenRouter)**, or a **hybrid** that routes each agent to the cheapest model that can do its job.

> Define a workflow once — content production, research, lead qualification, support triage — assign each step to a specialized agent, set a trigger (manual, scheduled, or webhook), and watch the pipeline run live. Output and a full trace (tokens, cost, latency per agent) are saved for every run.

---

## ✨ Features

- 🧩 **Visual workflow builder** — create any team of agents, any order, reorder/add/remove *(per-agent field editing has a known bug — see [Status](#-status))*
- 🔀 **Parallel & conditional execution** — agents in the same group run concurrently; agents can be skipped by a condition (e.g. escalate only when flagged)
- 🧠 **Per-agent model routing** — `ollama` (local/free), `openrouter` (hosted gateway), `mock` (offline demo), with **local-fail → API fallback**
- ⚡ **Triggers** — manual, **scheduled (cron)**, or **webhook**
- 📺 **Live run view** — watch each agent light up and stream output token-by-token over WebSocket
- 📜 **Run history & traces** — per-agent input, output, tools called, model, tokens, cost, latency
- 📊 **Observability dashboard** — success rate, total cost/tokens, **local-vs-API cost split**, average latency
- 🔧 **Tool integration** — web search + file output today, MCP servers as the integration point
- 📚 **Template library** — 4 ready-to-clone workflows (content, research, lead-gen, support)
- 💾 **Persistence** — SQLite out of the box (zero setup), Supabase/Postgres as the production target

**Runs out of the box with no API keys and no GPU** — the built-in `mock` model produces realistic streaming output so you can demo the entire platform offline.

---

## 🚀 Quick start

### Option A — One command (full app, no Docker)

```bash
python run.py            # first time: python run.py --install
```

Starts the backend (FastAPI, autoreload) and frontend (Vite) together, prefixes both logs in one terminal, and stops both on Ctrl+C. Hops to a free port automatically if 8000 is taken. Open **http://localhost:5173** — run a template live, **clone** it, or build your own in the **Builder**.

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
cp .env.example .env        # optional: add OPENROUTER_API_KEY for hosted models
docker compose up --build
```
- Frontend → http://localhost:5173 · Backend → http://localhost:8000/docs · Ollama → http://localhost:11434
- Pull a local model: `docker compose exec ollama ollama pull llama3.1:8b`

---

## 🧠 The model layer (the heart of the system)

Each agent stores a `model_provider` + `model_name`. A central **router** (`backend/app/models/router.py`) maps that choice to the right client:

| Provider | Client | Use |
|----------|--------|-----|
| `ollama` | `ollama_client.py` | Local open-source models on your GPU — **$0 inference** |
| `openrouter` | `openrouter_client.py` | One key → Claude, GPT, Gemini, Groq-served Llama, … |
| `mock` | `mock_client.py` | Offline demo / tests — realistic streaming, zero setup |

**Fallback:** if a primary provider fails (Ollama down, missing key, quota), the router retries once on a backup provider (`fallback.py`) — defaulting to `mock` so a run always completes, and the trace records the fallback.

**Hybrid routing principle:** local/cheap models for mechanical steps (classify, extract, format), premium models only where output quality is the deliverable. A 5-agent workflow might use 3 free local agents + 2 paid agents — cutting cost ~60% vs all-premium. The dashboard's local-vs-API split makes the savings visible.

---

## 🔀 Execution modes

The engine (`backend/app/orchestration/engine.py`) runs a workflow as ordered **stages**:

- **Sequential** — agents with no `parallel_group` run one after another, handing context forward.
- **Parallel** — agents sharing a `parallel_group` run concurrently (`asyncio.gather`); they see the same prior context, not each other.
- **Conditional** — an agent with a `condition` runs only if that phrase appears in prior output (prefix `!` to invert). Skipped agents are recorded and excluded from handoff.

The node/edge stage model mirrors a LangGraph `StateGraph`, so LangGraph can be swapped in without changing the API or the live event contract.

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

Interactive docs at `/docs`. **Live event stream:** `run_started` → `agent_started` → `token`×N → `agent_completed` / `agent_skipped` → … → `run_completed` | `run_failed`.

Scheduled workflows (`trigger_type: "schedule"` + a cron `schedule`) fire automatically via the in-process scheduler.

---

## 🗂 Project structure

```
taskforce/
├── run.py                         # ⭐ single-command launcher — backend + frontend together
├── backend/                       # FastAPI
│   ├── app/
│   │   ├── main.py                # routers, template seeding, scheduler start
│   │   ├── api/                   # workflows, runs(+WS), models, tools, stats, webhooks
│   │   ├── core/config.py         # settings (env-driven, sane defaults)
│   │   ├── models/                # ⭐ MODEL LAYER
│   │   │   ├── router.py          # routes agent → provider, applies fallback
│   │   │   ├── ollama_client.py · openrouter_client.py · mock_client.py
│   │   │   └── fallback.py        # local-fail → API fallback
│   │   ├── orchestration/
│   │   │   ├── engine.py          # sequential + parallel + conditional stages
│   │   │   ├── agent.py           # single-agent execution + tools + streaming
│   │   │   ├── handoff.py         # context passing between agents
│   │   │   ├── scheduler.py · cron.py   # scheduled (cron) triggers
│   │   │   └── templates.py       # 4 built-in workflows
│   │   ├── tools/                 # web_search, file output, registry (MCP-ready)
│   │   ├── db/                    # schema (Pydantic) + SQLite store
│   │   └── ws.py                  # live run event broker
│   ├── demo.py                    # run the pipeline from the CLI
│   └── tests/                     # 14 tests: engine, clients, cron, orchestrator
│
├── frontend/                      # React + Tailwind + Vite
│   └── src/
│       ├── pages/                 # Dashboard, WorkflowBuilder, Models, RunView, RunHistory
│       ├── components/            # PipelineGraph, LiveTrace, AgentCard, ModelPicker,
│       │                          #   ToolPicker, CostBadge, StatsBar
│       └── lib/                   # api client, websocket client
│
├── mcp_servers/                   # MCP servers exposing tools to agents
│   └── search_server/             # example: web search over MCP
│
├── docker-compose.yml             # backend, frontend, redis, ollama
├── .env.example
└── README.md
```

---

## 🧪 Tests

```bash
cd backend
pip install -r requirements-dev.txt   # pytest + pytest-asyncio (pulls in requirements.txt)
python -m pytest -q                   # 21 passing
```

Covers sequential/parallel/conditional execution, the cron matcher, context handoff,
the **real Ollama + OpenRouter clients** (verified against a mock HTTP upstream over
a real transport — proving the wiring without a live server), and that concurrent
agents streaming through the shared model router never leak usage/cost into each
other's trace. No network required.

---

## 🛠 Tech stack

**Frontend:** React · Tailwind CSS · Vite · React Router · WebSockets (live streaming)
**Backend:** FastAPI · Python · Pydantic
**Orchestration:** custom stage engine (sequential/parallel/conditional; LangGraph-shaped)
**Models — local:** Ollama (Llama 3.1, Qwen 2.5, Mistral/Nemo, Phi-3.5, Gemma 2…)
**Models — hosted:** OpenRouter gateway (Claude, GPT, Gemini, Groq-served open-source)
**Tools:** MCP servers (web search, database, email, Slack, file ops)
**Data:** SQLite (default) → Supabase/Postgres + pgvector (production)
**Scheduling:** in-process cron scheduler → Celery beat at scale
**Infra:** Docker Compose; deploy to Railway/Render (backend) + Vercel (frontend) + Supabase (DB)

---

## 💰 Cost strategy

| Setup | Cost | When |
|-------|------|------|
| All local (Ollama) | $0 inference | Privacy clients, simple workflows, dev |
| Open-source via Groq/Together (OpenRouter) | Very low | Speed/scale without a GPU |
| **Hybrid (local + premium API)** | **Low** | **Default — quality where it counts** |
| All premium API | Highest | Complex, high-stakes deliverables |

**The pitch to clients:** *"runs on your own models, your own infrastructure, no data leaves your servers"* (local) **OR** *"best quality, pay only for what you use"* (API) — TaskForce supports both, which most competitors don't.

---

## 🗺 Status

**Done:**
- [x] Visual workflow builder — add / reorder / remove agents, clone templates
- [x] Sequential, **parallel**, and **conditional** execution
- [x] Manual, **scheduled (cron)**, and **webhook** triggers
- [x] Per-agent model choice + fallback (local · hosted · demo)
- [x] Live run view with token streaming over WebSocket
- [x] Run history with full per-agent traces
- [x] Cost / observability dashboard (local-vs-API split)
- [x] Template library (content · research · lead-gen · support)
- [x] SQLite persistence
- [x] Tools (web search, file) + an example MCP server
- [x] Single-command local launcher (`run.py`)

**Known issues:**
- [ ] **Builder: per-agent fields don't save.** Role, instructions, model, tools, output format, parallel group, and condition are frozen after an agent is added — an `onChange` arity mismatch between `WorkflowBuilder.jsx`'s parent handler `(index, agent)` and the child's `(patch)` call. Add / reorder / remove work; editing an existing agent's fields does not.
- [ ] **`save_file` writes the run's input, not the deliverable.** The MVP's pre-tool step runs tools *before* the model, so the Editor's `save_file` call captures the workflow's original input rather than its own output.
- [ ] **Stats dashboard miscounts skipped agents.** A skipped agent has no `model_used`, so it lands in the "API" bucket of the local-vs-API cost split instead of being excluded.
- [ ] **`POST /api/workflows` can overwrite an existing workflow (including templates).** The `id` is accepted from the client instead of generated server-side.

**Production hardening (next):**
- [ ] Supabase persistence + auth (swap the SQLite store)
- [ ] Celery + Redis for distributed background runs and scheduling
- [ ] Full MCP tool library (database, email, Slack) + custom tools per workflow
- [ ] Model-driven tool-calling loop (ReAct) in place of the MVP's pre-tool step
- [ ] LangGraph engine for richer branching/looping
- [ ] Webhook auth (currently any caller can trigger a billable run)

---

## 📄 License

MIT — see `taskforce_complete.md` for the full product vision.
