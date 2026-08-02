"""API-level guarantees: create can't overwrite, webhooks honour the secret."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.orchestration.templates import CONTENT_PIPELINE


@pytest.fixture
def client():
    with TestClient(app) as c:  # lifespan seeds the templates
        yield c


def test_create_ignores_client_supplied_id(client):
    """POST must always insert under a fresh id.

    Honouring the posted id let the builder's "new workflow" screen silently
    overwrite the workflow it had just been editing (the store upserts).
    """
    body = {
        "id": CONTENT_PIPELINE.id,          # try to clobber a seeded template
        "name": "Impostor",
        "agents": [{"role": "A", "instructions": "do it"}],
    }
    created = client.post("/api/workflows", json=body).json()

    assert created["id"] != CONTENT_PIPELINE.id
    # The template is untouched.
    template = client.get(f"/api/workflows/{CONTENT_PIPELINE.id}").json()
    assert template["name"] == CONTENT_PIPELINE.name
    assert template["is_template"] is True
    # ...and a client can't mint templates either.
    assert created["is_template"] is False


def test_webhook_open_when_no_secret_configured(client):
    settings.webhook_secret = None
    resp = client.post(f"/api/webhooks/{CONTENT_PIPELINE.id}", json={"input": "hi"})
    assert resp.status_code == 200
    assert resp.json()["run_id"]


def test_webhook_requires_secret_when_configured(client):
    settings.webhook_secret = "s3cret"
    try:
        missing = client.post(f"/api/webhooks/{CONTENT_PIPELINE.id}", json={"input": "hi"})
        assert missing.status_code == 401

        wrong = client.post(
            f"/api/webhooks/{CONTENT_PIPELINE.id}",
            json={"input": "hi"},
            headers={"X-Webhook-Secret": "nope"},
        )
        assert wrong.status_code == 401

        ok = client.post(
            f"/api/webhooks/{CONTENT_PIPELINE.id}",
            json={"input": "hi"},
            headers={"X-Webhook-Secret": "s3cret"},
        )
        assert ok.status_code == 200
    finally:
        settings.webhook_secret = None  # don't leak into other tests
