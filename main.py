from fastapi import FastAPI
import stripe

from database import Base, engine
from routes import auth, billing, stripe_webhook, admin
from config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY
endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

Base.metadata.create_all(bind=engine)
app = FastAPI()

app.include_router(auth)
app.include_router(billing)
app.include_router(stripe_webhook)
app.include_router(admin)