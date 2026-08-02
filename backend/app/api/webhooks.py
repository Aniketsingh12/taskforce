"""Webhook triggers — start a workflow run from an external system.

POST any JSON to /api/webhooks/{workflow_id}; the body becomes the run input.
Returns the run id so the caller can poll /api/runs/{run_id}.

Set WEBHOOK_SECRET to require an `X-Webhook-Secret` header — without it the
endpoint is unauthenticated and anyone who can reach it can start billable runs.
"""

from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request

from ..core.config import settings
from .runs import TriggerResponse, start_run

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/{workflow_id}", response_model=TriggerResponse)
async def webhook_trigger(
    workflow_id: str,
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
) -> TriggerResponse:
    # Only enforced when a secret is configured, so local demos keep working.
    if settings.webhook_secret:
        if not x_webhook_secret or not hmac.compare_digest(
            x_webhook_secret, settings.webhook_secret
        ):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - allow empty / non-JSON bodies
        body = {}
    # Use an explicit `input` field if present, else the whole payload.
    run_input = body.get("input") if isinstance(body, dict) and "input" in body else json.dumps(body)
    run_id = start_run(workflow_id, run_input or "", "webhook")
    return TriggerResponse(run_id=run_id)
