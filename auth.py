from passlib.context import CryptContext
from jose import jwt, JWTError
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from config import settings

from database import get_db
from models import User

pwd_context = CryptContext(schemes=["bcrypt"])

oauth2 = HTTPBearer()


def hash_password(password):
    return pwd_context.hash(password)


def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)


def create_token(data: dict):
    return jwt.encode(data, settings.JWT_SECRET, algorithm="HS256")

def decode_token(token: str):
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM]
    )


def get_current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)):
    try:
        payload = decode_token(token.credentials)
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return user


def require_admin(user: User = Depends(get_current_user)):
    if getattr(user, "role", "user") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user