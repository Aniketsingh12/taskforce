"""Public-demo access control: admin gating, demo forcing, spend cap, rate limit."""

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import settings
from app.core.ratelimit import RateLimiter
from app.db.schema import Run, RunStatus
from app.db.store import store
from app.main import app
from app.orchestration.templates import CONTENT_PIPELINE

TOKEN = "test-admin-token"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def gated():
    """Turn on gating for one test, then restore the open default."""
    settings.admin_token = TOKEN
    security.run_limiter.reset()
    try:
        yield
    finally:
        settings.admin_token = None
        security.run_limiter.reset()


def _auth():
    return {"X-Admin-Token": TOKEN}


# --- Gating is opt-in ------------------------------------------------------

def test_everything_is_open_when_no_admin_token_configured(client):
    """Local dev and the test suite must behave exactly as before gating existed."""
    assert settings.admin_token is None
    status = client.get("/api/auth/status").json()
    assert status["gating_enabled"] is False
    assert status["admin"] is True and status["demo_mode"] is False

    created = client.post("/api/workflows", json={
        "name": "Open", "agents": [{"role": "A", "instructions": "go"}],
    })
    assert created.status_code == 201
    client.delete(f"/api/workflows/{created.json()['id']}")


# --- Admin token -----------------------------------------------------------

def test_mutations_require_the_admin_token(client, gated):
    """A visitor must not be able to create, edit, clone, or DELETE anything."""
    body = {"name": "Intruder", "agents": [{"role": "A", "instructions": "go"}]}

    assert client.post("/api/workflows", json=body).status_code == 401
    assert client.put(f"/api/workflows/{CONTENT_PIPELINE.id}", json=body).status_code == 401
    assert client.post(f"/api/workflows/{CONTENT_PIPELINE.id}/clone").status_code == 401
    # The one that would destroy real work.
    assert client.delete(f"/api/workflows/{CONTENT_PIPELINE.id}").status_code == 401

    # ...and the template is still there afterwards.
    assert client.get(f"/api/workflows/{CONTENT_PIPELINE.id}").status_code == 200


def test_admin_token_unlocks_mutations(client, gated):
    created = client.post("/api/workflows", headers=_auth(), json={
        "name": "Mine", "agents": [{"role": "A", "instructions": "go"}],
    })
    assert created.status_code == 201
    assert client.delete(
        f"/api/workflows/{created.json()['id']}", headers=_auth()
    ).status_code == 204


def test_a_wrong_token_is_rejected(client, gated):
    resp = client.post("/api/workflows", headers={"X-Admin-Token": "not-the-token"},
                       json={"name": "x", "agents": []})
    assert resp.status_code == 401


def test_reading_and_running_stay_public(client, gated):
    """The demo has to keep working for visitors — that's the whole point."""
    assert client.get("/api/workflows").status_code == 200
    assert client.get("/api/runs").status_code == 200
    assert client.post("/api/runs/trigger", json={
        "workflow_id": CONTENT_PIPELINE.id, "input": "hello",
    }).status_code == 200


def test_status_hides_spend_from_visitors(client, gated):
    """A public visitor has no business seeing your remaining budget."""
    anon = client.get("/api/auth/status").json()
    assert anon["demo_mode"] is True
    assert "spent_today" not in anon and "budget_remaining" not in anon

    admin = client.get("/api/auth/status", headers=_auth()).json()
    assert admin["admin"] is True and admin["demo_mode"] is False
    assert "spent_today" in admin


# --- Demo forcing ----------------------------------------------------------

def test_anonymous_runs_are_forced_onto_the_demo_model(gated):
    """The control that makes a public link safe: a visitor can't pick a billed model."""
    from app.api.runs import _as_demo
    from app.db.schema import AgentConfig, WorkflowConfig

    wf = WorkflowConfig(name="Pricey", agents=[
        AgentConfig(role="A", instructions="go", model_provider="together",
                    model_name="some/expensive-model", fallback_model="openrouter:gpt-4o"),
        AgentConfig(role="B", instructions="go", model_provider="openrouter",
                    model_name="openai/gpt-4o"),
    ])
    demo = _as_demo(wf)

    for agent in demo.agents:
        assert agent.model_provider == settings.demo_provider
        assert agent.model_name == settings.demo_model
        # A billed fallback would reintroduce the cost this exists to prevent.
        assert agent.fallback_model is None

    # The stored workflow is untouched — _as_demo must not mutate the original.
    assert wf.agents[0].model_provider == "together"
    assert wf.agents[0].fallback_model == "openrouter:gpt-4o"


# --- Model catalog privacy -------------------------------------------------

def test_model_catalog_is_hidden_from_visitors(client, gated):
    """The catalog is account detail, not public data.

    Together's list is fetched with YOUR api key (so a fine-tuned or dedicated
    model would be named in it), and the local list reveals what's installed on
    your server. A visitor is forced onto the demo model anyway, so there's
    nothing for them to gain and something for you to lose.
    """
    anon = client.get("/api/models").json()
    assert anon["restricted"] is True
    assert anon["together"] == []
    assert anon["local"] == []
    assert anon["hosted"] == []
    # They still see the one model they're allowed to run.
    assert [m["model"] for m in anon["demo"]] == [settings.demo_model]
    # And no hint of which providers are wired up.
    assert anon["providers"] == [settings.demo_provider]


def test_admin_still_sees_the_full_catalog(client, gated):
    full = client.get("/api/models", headers=_auth()).json()
    assert full["restricted"] is False
    assert "together" in full["providers"] and "openrouter" in full["providers"]
    # Static reference pricing is compiled into the repo, so it's always present.
    assert len(full["hosted"]) > 0


def test_catalog_is_public_when_gating_is_off(client):
    """Local dev keeps the full picker without needing a token."""
    assert settings.admin_token is None
    assert client.get("/api/models").json()["restricted"] is False


# --- Spend circuit breaker -------------------------------------------------

def test_budget_cap_blocks_new_runs_once_reached(client, gated):
    """The only control that bounds the maximum bill."""
    settings.daily_cost_limit_usd = 0.50
    try:
        # Bank a run that has already consumed the whole day's budget.
        spent = Run(workflow_id="x", workflow_name="Expensive",
                    status=RunStatus.done, total_cost=0.75)
        store.save_run(spent)

        # An admin (real models) is refused...
        blocked = client.post("/api/runs/trigger", headers=_auth(), json={
            "workflow_id": CONTENT_PIPELINE.id, "input": "hi",
        })
        assert blocked.status_code == 429
        assert "spend limit" in blocked.json()["detail"].lower()

        # ...but a visitor's demo run still works, because it costs nothing.
        assert client.post("/api/runs/trigger", json={
            "workflow_id": CONTENT_PIPELINE.id, "input": "hi",
        }).status_code == 200
    finally:
        settings.daily_cost_limit_usd = 1.0


def test_spend_since_only_counts_runs_in_the_window():
    old = Run(workflow_id="x", status=RunStatus.done, total_cost=5.0)
    old.started_at = old.started_at.replace(year=old.started_at.year - 1)
    store.save_run(old)
    # A cutoff after that run excludes it.
    assert store.spend_since("2099-01-01T00:00:00+00:00") == 0.0


# --- Rate limiting ---------------------------------------------------------

def test_rate_limiter_allows_then_blocks():
    limiter = RateLimiter(max_events=3, window_seconds=60)
    assert [limiter.allow("1.2.3.4") for _ in range(3)] == [True, True, True]
    assert limiter.allow("1.2.3.4") is False
    # Limits are per-key, so one noisy client can't lock everyone else out.
    assert limiter.allow("5.6.7.8") is True


def test_rate_limiter_is_disabled_when_max_is_zero():
    limiter = RateLimiter(max_events=0, window_seconds=60)
    assert all(limiter.allow("x") for _ in range(50))


def test_trigger_endpoint_enforces_the_rate_limit(client, gated):
    original = settings.rate_limit_runs
    settings.rate_limit_runs = 2
    security.run_limiter = RateLimiter(max_events=2, window_seconds=3600)
    try:
        body = {"workflow_id": CONTENT_PIPELINE.id, "input": "hi"}
        assert client.post("/api/runs/trigger", json=body).status_code == 200
        assert client.post("/api/runs/trigger", json=body).status_code == 200
        third = client.post("/api/runs/trigger", json=body)
        assert third.status_code == 429
        assert "rate limit" in third.json()["detail"].lower()
    finally:
        settings.rate_limit_runs = original
        security.run_limiter = RateLimiter(
            max_events=original, window_seconds=settings.rate_limit_window_seconds
        )


def test_client_ip_prefers_the_proxy_header():
    """Behind Railway the socket peer is the proxy, not the visitor."""
    class FakeReq:
        headers = {"x-forwarded-for": "203.0.113.9, 70.41.3.18"}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert security.client_ip(FakeReq()) == "203.0.113.9"

    class NoHeader:
        headers = {}
        client = type("C", (), {"host": "10.0.0.1"})()

    assert security.client_ip(NoHeader()) == "10.0.0.1"
