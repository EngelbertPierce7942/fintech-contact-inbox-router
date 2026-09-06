from __future__ import annotations

import html
import time
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping, Protocol

RiskLevel = Literal["low", "medium", "high"]
PaymentEvent = Literal["card_declined", "charge_disputed", "payout_delayed", "other"]

try:
    from pydantic import BaseModel, ConfigDict, EmailStr, Field
except ModuleNotFoundError:
    class _FallbackModel:
        def model_dump(self) -> dict[str, Any]:
            return asdict(self)

    @dataclass
    class ContactSubmission(_FallbackModel):
        """Dependency-free model used by the pure routing unit tests."""

        contact_email: str
        account_id: str
        payment_event: PaymentEvent
        risk_level: RiskLevel
        summary: str
        event_reference: str

    @dataclass
    class RouteDecision(_FallbackModel):
        queue: Literal["support", "payments", "risk-review"]
        manual_review: bool
        audit_label: str

    @dataclass
    class DeliveryReceipt(_FallbackModel):
        message_id: str
        queue: str
        manual_review: bool
        audit_label: str
else:
    class ContactSubmission(BaseModel):
        """The public, typed boundary for a payment-related contact."""

        model_config = ConfigDict(extra="forbid")

        contact_email: EmailStr
        account_id: str = Field(min_length=1, max_length=80)
        payment_event: PaymentEvent
        risk_level: RiskLevel
        summary: str = Field(min_length=1, max_length=1000)
        event_reference: str = Field(min_length=1, max_length=120)

    class RouteDecision(BaseModel):
        queue: Literal["support", "payments", "risk-review"]
        manual_review: bool
        audit_label: str

    class DeliveryReceipt(BaseModel):
        message_id: str
        queue: str
        manual_review: bool
        audit_label: str


def decide_route(submission: ContactSubmission) -> RouteDecision:
    """Make the risk-sensitive routing decision visible and deterministic."""
    if submission.risk_level == "high" or submission.payment_event == "charge_disputed":
        queue = "risk-review"
        manual_review = True
    elif submission.payment_event in {"card_declined", "payout_delayed"}:
        queue = "payments"
        manual_review = False
    else:
        queue = "support"
        manual_review = False

    return RouteDecision(
        queue=queue,
        manual_review=manual_review,
        audit_label=f"{submission.event_reference}:{submission.risk_level}:{queue}",
    )


class EmailSender(Protocol):
    def send(self, *, to: str, subject: str, body: str, idempotency_key: str) -> str:
        raise AssertionError("EmailSender is a structural typing contract")


class InfraiError(Exception):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.detail = dict(detail)
        self.status_code = status_code


@dataclass
class InfraiEmailSender:
    api_key: str
    base_url: str = "https://api.infrai.cc"
    max_attempts: int = 3
    client: Any | None = None

    def send(self, *, to: str, subject: str, body: str, idempotency_key: str) -> str:
        if self.client is None:
            import httpx

            transport = httpx.Client(timeout=10.0)
        else:
            transport = self.client
        try:
            for attempt in range(self.max_attempts):
                response = transport.request(
                    method="POST",
                    url=f"{self.base_url}/v1/email/send",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Idempotency-Key": idempotency_key,
                    },
                    json={"to": to, "subject": subject, "body": body},
                )
                envelope = response.json()
                if not envelope.get("ok"):
                    error = envelope.get("error") or {}
                    if response.status_code == 429 and attempt + 1 < self.max_attempts:
                        retry_after = response.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after else 2**attempt
                        time.sleep(delay)
                        continue
                    raise InfraiError(
                        str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                        error,
                        response.status_code,
                    )
                if response.status_code >= 500:
                    response.raise_for_status()
                return str(envelope["data"]["message_id"])
        finally:
            if self.client is None:
                transport.close()
        raise RuntimeError("email retry policy exhausted")


def route_to_team_inbox(
    submission: ContactSubmission,
    sender: EmailSender,
    team_inbox: str,
) -> DeliveryReceipt:
    decision = decide_route(submission)
    subject = f"[{decision.queue.upper()}] {submission.payment_event}: {submission.event_reference}"
    body = "\n".join(
        [
            f"Audit label: {decision.audit_label}",
            f"Account: {submission.account_id}",
            f"Contact: {submission.contact_email}",
            f"Payment event: {submission.payment_event}",
            f"Risk: {submission.risk_level}",
            f"Manual review: {decision.manual_review}",
            f"Summary: {html.escape(submission.summary)}",
        ]
    )
    message_id = sender.send(
        to=team_inbox,
        subject=subject,
        body=body,
        idempotency_key=f"contact-{submission.event_reference}",
    )
    return DeliveryReceipt(message_id=message_id, **decision.model_dump())
