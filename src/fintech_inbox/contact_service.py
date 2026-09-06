from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from .inbox_router import (
    ContactSubmission,
    DeliveryReceipt,
    InfraiEmailSender,
    InfraiError,
    route_to_team_inbox,
)

app = FastAPI(title="Fintech contact inbox router")


@app.post("/contacts", response_model=DeliveryReceipt, status_code=201)
def submit_contact(submission: ContactSubmission) -> DeliveryReceipt:
    api_key = os.environ.get("INFRAI_API_KEY")
    team_inbox = os.environ.get("TEAM_INBOX")
    if not api_key or not team_inbox:
        raise HTTPException(status_code=503, detail="Service configuration is incomplete")

    try:
        return route_to_team_inbox(
            submission,
            InfraiEmailSender(api_key=api_key),
            team_inbox,
        )
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "message": exc.detail.get("message", "Email was not accepted")},
        ) from exc

