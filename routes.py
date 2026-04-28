from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import stripe, os

from typing import List

from database import get_db
from models import User, Plan, Subscription, Payment, WebhookEvent
from auth import hash_password, verify_password, create_token, get_current_user, require_admin
from config import settings
from schemas import (
    UserCreate,
    Token,
    PlanCreate,
    PlanOut,
    SubscribeRequest,
    CheckoutResponse,
    PaymentOut,
    Message,
    SessionStatus,
)

stripe.api_key = settings.STRIPE_SECRET_KEY
endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

# Routers
auth = APIRouter(prefix="/auth")
billing = APIRouter(prefix="/billing")
stripe_webhook = APIRouter()
admin = APIRouter(prefix="/admin")


@auth.post("/register", response_model=Message)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    user = User(email=payload.email, password=hash_password(payload.password), role="member")
    
    db.add(user)
    db.commit()
    return {"message": "User created"}


@admin.post("/register", response_model=Message)
def register_admin(
    payload: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create a new admin user. Requires an existing admin to call."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    user = User(email=payload.email, password=hash_password(payload.password), role="admin")
    db.add(user)
    db.commit()
    return {"message": "Admin user created"}


@auth.post("/login", response_model=Token)
def login(payload: UserCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password):
        raise HTTPException(400, "Invalid credentials")
    token = create_token({"user_id": user.id})
    return {"access_token": token}


@billing.post("/plans", response_model=PlanOut)
def create_plan(
    payload: PlanCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    # create stripe product + price
    product = stripe.Product.create(name=payload.name)
    price_in_cents = int(payload.price * 100)

    stripe_price = stripe.Price.create(
        unit_amount=price_in_cents,
        currency="usd",
        recurring={"interval": "month"},
        product=product.id,
    )

    plan = Plan(name=payload.name, price=payload.price, stripe_price_id=stripe_price.id)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@billing.post("/subscribe", response_model=CheckoutResponse)
def subscribe(
    payload: SubscribeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    plan = db.query(Plan).get(payload.plan_id)
    # ensure stripe customer exists for user
    customer_id = current_user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        current_user.stripe_customer_id = customer.id
        db.add(current_user)
        db.commit()
        customer_id = customer.id

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        success_url="http://localhost:3000/success",
        cancel_url="http://localhost:3000/cancel",
        client_reference_id=str(current_user.id),
        customer=customer_id,
        metadata={"user_id": str(current_user.id), "plan_id": str(plan.id)},
    )

    sub = Subscription(
        user_id=current_user.id,
        plan_id=payload.plan_id,
        status="pending",
        stripe_session_id=session.id,
    )
    db.add(sub)
    db.commit()

    return {"checkout_url": session.url, "session_id": session.id}


@stripe_webhook.post("/webhook")
async def stripe_webhook_handler(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except Exception:
        raise HTTPException(400, "Webhook error")
    # Idempotency: ensure we process each Stripe event once
    event_id = event.get("id")
    if event_id:
        existing = db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
        if existing:
            return {"status": "already processed"}
        # mark event as seen
        seen = WebhookEvent(event_id=event_id)
        db.add(seen)
        db.commit()

    # Handle relevant event types
    etype = event.get("type")
    if etype == "checkout.session.completed":
        session = event["data"]["object"]
        session_id = session.get("id")
        metadata = session.get("metadata", {}) or {}
        user_id = metadata.get("user_id") or session.get("client_reference_id")
        plan_id = metadata.get("plan_id")
        stripe_sub_id = session.get("subscription")

        sub = None
        if session_id:
            sub = db.query(Subscription).filter(Subscription.stripe_session_id == session_id).first()

        if not sub and user_id:
            sub = (
                db.query(Subscription)
                .filter(Subscription.user_id == int(user_id))
                .order_by(Subscription.id.desc())
                .first()
            )

        if not sub:
            # create subscription record if none exists
            sub = Subscription(
                user_id=int(user_id) if user_id else None,
                plan_id=int(plan_id) if plan_id else None,
                status="active",
                stripe_subscription_id=stripe_sub_id,
                stripe_session_id=session_id,
            )
            db.add(sub)
        else:
            sub.status = "active"
            sub.stripe_subscription_id = stripe_sub_id
            sub.stripe_session_id = session_id or sub.stripe_session_id

        payment = Payment(
            user_id=sub.user_id,
            amount=0,
            status="paid",
            stripe_payment_intent=session.get("payment_intent"),
        )
        db.add(payment)
        db.commit()

    elif etype == "invoice.paid":
        invoice = event["data"]["object"]
        stripe_sub_id = invoice.get("subscription")
        # mark subscription active/renewed
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_sub_id).first()
        if sub:
            sub.status = "active"
            # record payment
            payment = Payment(
                user_id=sub.user_id,
                amount=invoice.get("amount_paid", 0),
                status="paid",
                stripe_payment_intent=invoice.get("payment_intent"),
            )
            db.add(payment)
            db.commit()

    elif etype == "invoice.payment_failed":
        invoice = event["data"]["object"]
        stripe_sub_id = invoice.get("subscription")
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_sub_id).first()
        if sub:
            sub.status = "past_due"
            db.commit()

    elif etype == "customer.subscription.deleted":
        subscription_obj = event["data"]["object"]
        stripe_sub_id = subscription_obj.get("id")
        sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == stripe_sub_id).first()
        if sub:
            sub.status = "canceled"
            db.commit()

    return {"status": "success"}


@billing.post("/verify-payment", response_model=SessionStatus)
def verify(session_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Read-only check of Stripe Checkout Session. Requires authentication. Does NOT change DB state.

    Returns the Stripe session payment status and metadata. Frontend can poll this endpoint to update UI,
    but the webhook remains the authoritative source for activating subscriptions.
    """
    session = stripe.checkout.Session.retrieve(session_id)

    # verify that the session belongs to the requesting user (metadata or client_reference_id)
    metadata = session.get("metadata") or {}
    owner = metadata.get("user_id") or session.get("client_reference_id")
    if owner and str(owner) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not allowed")

    return {
        "session_id": session.id,
        "payment_status": session.get("payment_status"),
        "subscription_id": session.get("subscription"),
        "metadata": metadata,
    }


@billing.get("/payments", response_model=List[PaymentOut])
def get_payments(db: Session = Depends(get_db)):
    return db.query(Payment).all()


@billing.get("/plans", response_model=List[PlanOut])
def list_plans(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List available plans — requires authentication."""
    return db.query(Plan).all()
