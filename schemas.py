from pydantic import BaseModel, EmailStr
from typing import Optional, Dict


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str


class PlanCreate(BaseModel):
    name: str
    price: int


class PlanOut(BaseModel):
    id: int
    name: str
    price: int
    stripe_price_id: Optional[str]

    class Config:
        orm_mode = True


class SubscribeRequest(BaseModel):
    plan_id: int


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class SessionStatus(BaseModel):
    session_id: str
    payment_status: Optional[str]
    subscription_id: Optional[str]
    metadata: Optional[Dict[str, str]]


class PaymentOut(BaseModel):
    id: int
    user_id: int
    amount: int
    status: str
    stripe_payment_intent: Optional[str]

    class Config:
        orm_mode = True


class Message(BaseModel):
    message: str
