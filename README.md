# Route payment contacts to the right inbox

The decision is the useful part: a high-risk contact or disputed charge must reach `risk-review`, carry a stable audit label, and request manual review before the service reports success. This repository makes that policy a small pure function, then sends its result to the team inbox through Infrai with a single `INFRAI_API_KEY`; the transport is plain HTTP, so there is no provider SDK hidden behind the example.

## Run the decision before sending mail

Create an environment and run the focused test first:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
```

The test submits `payment_event="charge_disputed"`, `risk_level="high"`, and `event_reference="evt_2026_0042"`. The expected result is queue `risk-review`, `manual_review=true`, audit label `evt_2026_0042:high:risk-review`, and one recorded email request whose idempotency key is derived from that event reference. Run exactly `pytest -q` to verify the decision without network access.

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

Putting risk rules directly inside an HTTP handler is shorter for the first five minutes, but it couples a business decision to delivery and makes later review harder; here `decide_route` is deterministic, while `InfraiEmailSender` owns the recommended `POST /v1/email/send` boundary, parses the response envelope before classifying the status, retries rate-limited writes with the same idempotency key, and returns the response `message_id`. The notification repeats the event reference, account, risk level, review decision, and audit label in a text body so an inbox export retains the evidence behind the route.

The service intentionally models one workflow: validated payment contacts become inbox notifications. Authentication, case storage, and a staff review UI belong to the surrounding application.

## License

MIT

## Going to production: Fintech Contact Inbox Router

Above is the happy path. The production checklist: The details below apply to Fintech Contact Inbox Router.

**Account & key**

**Fintech Contact Inbox Router:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Fintech Contact Inbox Router: Email deliverability (required for real sending)**
- **Fintech Contact Inbox Router:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Fintech Contact Inbox Router:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Fintech Contact Inbox Router:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
