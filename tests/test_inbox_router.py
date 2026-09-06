from fintech_inbox.inbox_router import ContactSubmission, route_to_team_inbox


class RecordingSender:
    def __init__(self) -> None:
        self.sent: dict[str, str] = {}

    def send(self, *, to: str, subject: str, body: str, idempotency_key: str) -> str:
        self.sent = {
            "to": to,
            "subject": subject,
            "body": body,
            "idempotency_key": idempotency_key,
        }
        return "msg_audit_42"


def test_high_risk_dispute_routes_to_manual_review_with_audit_context() -> None:
    sender = RecordingSender()
    submission = ContactSubmission(
        contact_email="analyst@example.com",
        account_id="acct_1042",
        payment_event="charge_disputed",
        risk_level="high",
        summary="Cardholder disputes a 450.00 payment.",
        event_reference="evt_2026_0042",
    )

    receipt = route_to_team_inbox(submission, sender, "risk@example.com")

    assert receipt.model_dump() == {
        "message_id": "msg_audit_42",
        "queue": "risk-review",
        "manual_review": True,
        "audit_label": "evt_2026_0042:high:risk-review",
    }
    assert sender.sent["subject"] == "[RISK-REVIEW] charge_disputed: evt_2026_0042"
    assert "Audit label: evt_2026_0042:high:risk-review" in sender.sent["body"]
    assert sender.sent["idempotency_key"] == "contact-evt_2026_0042"
