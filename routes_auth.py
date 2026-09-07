import os
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from auth_utils import (create_token, get_current_user, hash_pw, log_activity,
                        new_id, now_utc, public_user, verify_pw)
from db import db

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_PROVIDER = os.environ.get("OTP_PROVIDER", "test")
TEST_OTP = os.environ.get("TEST_OTP", "123456")
OTP_EXPIRY = int(os.environ.get("OTP_EXPIRY_SECONDS", "120"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))


class SendOtpIn(BaseModel):
    identifier: str


class VerifyOtpIn(BaseModel):
    identifier: str
    otp: str
    name: str | None = None


class AdminLoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    name: str | None = None
    email: str | None = None


def _is_email(identifier: str) -> bool:
    return "@" in identifier


@router.post("/send-otp")
async def send_otp(body: SendOtpIn):
    identifier = body.identifier.strip().lower() if _is_email(body.identifier) else body.identifier.strip()
    if not identifier:
        raise HTTPException(400, "Mobile number or email is required")
    if not _is_email(identifier) and not identifier.isdigit():
        raise HTTPException(400, "Enter a valid mobile number")
    since = (now_utc() - timedelta(hours=1)).isoformat()
    sent = await db.otps.count_documents({"identifier": identifier, "created_at": {"$gte": since}})
    if sent >= 10:
        raise HTTPException(429, "Too many OTP requests. Try again later.")
    otp = TEST_OTP if OTP_PROVIDER == "test" else "".join(__import__("random").choices("0123456789", k=6))
    await db.otps.insert_one({
        "id": new_id(),
        "identifier": identifier,
        "otp_hash": hash_pw(otp),
        "expires_at": now_utc() + timedelta(seconds=OTP_EXPIRY),
        "attempts": 0,
        "created_at": now_utc().isoformat(),
    })
    resp = {"message": "OTP sent", "expires_in": OTP_EXPIRY}
    if OTP_PROVIDER == "test":
        resp["test_otp"] = otp
    return resp


@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpIn):
    identifier = body.identifier.strip().lower() if _is_email(body.identifier) else body.identifier.strip()
    otp_doc = await db.otps.find_one({"identifier": identifier}, sort=[("created_at", -1)])
    if not otp_doc:
        raise HTTPException(400, "OTP not requested. Please request a new OTP.")
    if otp_doc["attempts"] >= OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "Too many attempts. Request a new OTP.")
    exp = otp_doc["expires_at"]
    if isinstance(exp, str):
        exp = __import__("datetime").datetime.fromisoformat(exp)
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=__import__("datetime").timezone.utc)
    if now_utc() > exp:
        raise HTTPException(400, "OTP expired. Please request a new OTP.")
    if not verify_pw(body.otp.strip(), otp_doc["otp_hash"]):
        await db.otps.update_one({"id": otp_doc["id"]}, {"$inc": {"attempts": 1}})
        remaining = OTP_MAX_ATTEMPTS - otp_doc["attempts"] - 1
        raise HTTPException(400, f"Invalid OTP. {remaining} attempt(s) left.")
    await db.otps.delete_many({"identifier": identifier})

    query = {"email": identifier} if _is_email(identifier) else {"mobile": identifier}
    user = await db.users.find_one(query)
    if not user:
        user = {
            "id": new_id(),
            "name": body.name or ("Customer " + identifier[-4:]),
            "role": "customer",
            "wallet_balance": 0.0,
            "loyalty_points": 0,
            "created_at": now_utc().isoformat(),
        }
        if _is_email(identifier):
            user["email"] = identifier
        else:
            user["mobile"] = identifier
        try:
            await db.users.insert_one(user)
        except Exception:
            user = await db.users.find_one(query)
            if not user:
                raise HTTPException(409, "Account conflict. Please try again.")
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": public_user(user)}


@router.post("/admin-login")
async def admin_login(body: AdminLoginIn, request: Request):
    email = body.email.strip().lower()
    key = email
    attempt = await db.login_attempts.find_one({"key": key})
    if attempt and attempt.get("count", 0) >= 5:
        locked_at = __import__("datetime").datetime.fromisoformat(attempt["updated_at"])
        if now_utc() - locked_at < timedelta(minutes=15):
            raise HTTPException(429, "Account locked for 15 minutes due to failed attempts")
        await db.login_attempts.delete_one({"key": key})
    user = await db.users.find_one({"email": email})
    if not user or not user.get("password_hash") or not verify_pw(body.password, user["password_hash"]):
        await db.login_attempts.update_one(
            {"key": key},
            {"$inc": {"count": 1}, "$set": {"updated_at": now_utc().isoformat()}},
            upsert=True,
        )
        raise HTTPException(401, "Invalid email or password")
    if user.get("role") == "customer":
        raise HTTPException(403, "Admin access required")
    await db.login_attempts.delete_one({"key": key})
    token = create_token(user["id"], user["role"])
    return {"token": token, "user": public_user(user)}


@router.get("/me")
async def me(request: Request):
    return public_user(await get_current_user(request))


@router.put("/profile")
async def update_profile(body: ProfileIn, request: Request):
    user = await get_current_user(request)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    return public_user(await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0}))


@router.post("/logout")
async def logout():
    return {"message": "Logged out"}
