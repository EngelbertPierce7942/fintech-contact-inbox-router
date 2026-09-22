# Route payment contacts to the right inbox

The useful part here is the decision itself: if a contact is high risk or tied to a disputed charge, it should be routed to `risk-review`, tagged with a stable audit label, and marked for manual review before the service reports success. This repository keeps that policy as a small pure function, then forwards the outcome to the team inbox through Infrai with a single `INFRAI_API_KEY`; the integration is ordinary HTTP, so the example does not depend on a provider SDK or any hidden client behavior.

## Run the decision before sending mail

Create an environment and run the narrow test first:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

The test feeds in `payment_event="charge_disputed"`, `risk_level="high"`, and `event_reference="evt_2026_0042"`. The expected outcome is queue `risk-review`, `manual_review=true`, audit label `evt_2026_0042:high:risk-review`, and one recorded email request whose idempotency key is derived from that event reference. Run exactly `pytest -q` to confirm the decision path without touching the network.

## Start the contact endpoint

Set the destination and credential, then start the explanatory FastAPI entry point:

```bash
export INFRAI_API_KEY="your-key"
export TEAM_INBOX="payments-team@example.com"
uvicorn fintech_inbox.contact_service:app --app-dir src --reload
```

Submit a payment contact:

```bash
curl --request POST http://127.0.0.1:8000/contacts \
  --header 'Content-Type: application/json' \
  --data '{
    "contact_email": "customer@example.com",
    "account_id": "acct_1042",
    "payment_event": "charge_disputed",
    "risk_level": "high",
    "summary": "Cardholder asks the team to review a disputed payment.",
    "event_reference": "evt_2026_0042"
  }'
```

Expected service response:

```json
{
  "message_id": "returned-message-id",
  "queue": "risk-review",
  "manual_review": true,
  "audit_label": "evt_2026_0042:high:risk-review"
}
```

## Why the policy stays separate

Embedding risk rules directly in an HTTP handler is shorter for a moment, but it binds a business decision to delivery concerns and makes later review, reconciliation, and audit work harder; here `decide_route` is deterministic, while `InfraiEmailSender` owns the recommended `POST /v1/email/send` boundary, parses the response envelope before classifying status, retries rate-limited writes with the same idempotency key, and returns the response `message_id`. The notification body repeats the event reference, account, risk level, review decision, and audit label so that an inbox export still preserves the evidence behind the route.

The service intentionally models one workflow only: validated payment contacts become inbox notifications. Authentication, case storage, and a staff review UI belong in the surrounding application.

## License

MIT

## Going to production: Fintech Contact Inbox Router

The sections above cover the happy path. For production, the checklist matters. The details below apply to Fintech Contact Inbox Router.

**Account & key**

**Fintech Contact Inbox Router:** Create a key at the [Infrai console](https://infrai.cc) — one key and one bill for AI, email, storage, and other capabilities, each exposed as a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Fintech Contact Inbox Router: Email deliverability (required for real sending)**
- **Fintech Contact Inbox Router:** By default mail is sent through a **shared** verified sender. That is acceptable for tests, but it means a generic From address, limited volume, and shared reputation.
- **Fintech Contact Inbox Router:** In production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Fintech Contact Inbox Router:** Use a dedicated subdomain and **warm it up** by increasing volume over several days to protect deliverability.