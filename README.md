Stripe + FastAPI subscription demo

Overview
- Minimal FastAPI app demonstrating user auth, Stripe Checkout subscriptions, webhook-based fulfillment, and basic admin-protected plan management.
- Webhook endpoint is the authoritative source of truth for subscription/payment state.

Requirements
- Python 3.10+
- A virtual environment (recommended)
- Stripe CLI (for testing webhooks)

Important environment variables
- `DATABASE_URL` — SQLAlchemy database URL (e.g. sqlite:///./dev.db or a Postgres URL)
- `STRIPE_SECRET_KEY` — your Stripe secret API key
- `STRIPE_WEBHOOK_SECRET` — webhook signing secret (from Stripe CLI or Stripe dashboard)
- `JWT_SECRET` — secret for signing JWTs used for auth

Install & run locally
1. Create and activate virtualenv:

```bash
python -m venv .venv
.\.venv\Scripts\activate    # Windows
# or: source .venv/bin/activate  # macOS / Linux
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set environment variables (example, PowerShell):

```powershell
$env:DATABASE_URL = "sqlite:///./dev.db"
$env:STRIPE_SECRET_KEY = "sk_test_..."
$env:JWT_SECRET = "supersecret"
# You'll set STRIPE_WEBHOOK_SECRET after starting stripe listen (see below)
```

4. Start the app:

```bash
uvicorn main:app --reload
```

DB tables are created automatically on startup via SQLAlchemy `Base.metadata.create_all`.

Testing Stripe webhooks (recommended)
1. Start your app locally (see above).
2. Start Stripe CLI listener to forward webhooks and get a webhook signing secret:

```bash
stripe listen --forward-to http://localhost:8000/webhook
```

When you start `stripe listen` it prints a webhook signing secret (starts with `whsec_`). Set `STRIPE_WEBHOOK_SECRET` to that value in your environment before testing (or export it into your shell session).

3. Create a Checkout Session by calling the `POST /billing/subscribe` endpoint (authenticated). The endpoint returns `checkout_url` and `session_id`. Open `checkout_url` and complete a test card (e.g. 4242 4242 4242 4242).

4. Stripe will send a signed `checkout.session.completed` webhook to `/webhook`. The app verifies the signature and updates DB state (subscription activated, payment recorded). Do NOT call `/webhook` from Swagger — that will fail signature verification.

Quick test with Stripe CLI (simulate events):

```bash
stripe trigger checkout.session.completed
```

Endpoints (summary)
- `POST /auth/register` — register user (body: `{ "email": "x", "password": "x" }`)
- `POST /auth/login` — login (returns `access_token`)
- `POST /admin/register` — create admin (requires existing admin auth)
- `GET /billing/plans` — list plans (requires auth)
- `POST /billing/plans` — create a plan (admin only)
- `POST /billing/subscribe` — create Checkout Session and returns `checkout_url` and `session_id` (requires auth)
- `POST /billing/verify-payment` — read-only check of a Checkout Session (requires auth). Returns payment_status and metadata; webhook is authoritative.
- `POST /webhook` — Stripe webhook endpoint (expects signed raw body + `stripe-signature` header). Do not call from Swagger.
- `GET /billing/payments` — list recorded payments

Security & production notes
- Webhook handlers must verify signatures and be idempotent (this app records processed event IDs).
- Use metadata or client_reference_id to reliably map Stripe objects to your users/plans.
- Do not trust frontend success pages — rely on the webhook for finalizing subscriptions.
- Persist Stripe customer IDs on your User model and reuse them for subscriptions and invoices.

If you want, I can:
- Run a quick syntax/import check, or
- Start a local test sequence using Stripe CLI to demonstrate a subscription flow.

