import os
import uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Request

from db import db

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
JWT_ALGO = "HS256"
TOKEN_DAYS = 7


def now_utc():
    return datetime.now(timezone.utc)


def new_id():
    return uuid.uuid4().hex


def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": now_utc() + timedelta(days=TOKEN_DAYS),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def _extract_token(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return request.cookies.get("access_token")


async def get_current_user(request: Request) -> dict:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_optional_user(request: Request):
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


ROLE_PERMISSIONS = {
    "super_admin": {"*"},
    "admin": {"dashboard", "products", "categories", "orders", "customers", "coupons", "offers", "subscriptions", "settings", "reports", "logs", "inventory"},
    "editor": {"dashboard", "products", "categories", "offers"},
    "sales_manager": {"dashboard", "orders", "customers", "coupons", "reports"},
    "inventory_manager": {"dashboard", "products", "inventory"},
    "support": {"dashboard", "orders", "customers"},
}


async def require_admin(request: Request, permission: str = None) -> dict:
    user = await get_current_user(request)
    if user.get("role") == "customer":
        raise HTTPException(status_code=403, detail="Admin access required")
    if permission:
        perms = ROLE_PERMISSIONS.get(user.get("role"), set())
        if "*" not in perms and permission not in perms:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
    return user


async def log_activity(admin: dict, action: str, record: str, detail: str = ""):
    await db.activity_logs.insert_one({
        "id": new_id(),
        "admin_id": admin.get("id"),
        "admin_name": admin.get("name") or admin.get("email") or admin.get("mobile"),
        "action": action,
        "record": record,
        "detail": detail,
        "created_at": now_utc().isoformat(),
    })


def public_user(user: dict) -> dict:
    user = dict(user)
    user.pop("password_hash", None)
    user.pop("_id", None)
    return user
