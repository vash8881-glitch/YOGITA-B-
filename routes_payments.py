import hashlib
import hmac
import os

import razorpay
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from auth_utils import get_current_user, new_id, now_utc
from db import db

router = APIRouter(prefix="/api/payments", tags=["payments"])

RZP_KEY = os.environ.get("RAZORPAY_KEY_ID", "")
RZP_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")


def _client():
    if not RZP_KEY or not RZP_SECRET:
        raise HTTPException(503, "Razorpay is not configured on the server")
    return razorpay.Client(auth=(RZP_KEY, RZP_SECRET))


class CreateRzpOrderIn(BaseModel):
    order_id: str


class VerifyIn(BaseModel):
    order_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/razorpay/create-order")
async def create_razorpay_order(body: CreateRzpOrderIn, request: Request):
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": body.order_id, "user_id": user["id"]})
    if not order:
        raise HTTPException(404, "Order not found")
    if order.get("payment_method") != "razorpay":
        raise HTTPException(400, "Order is not a Razorpay order")
    if order.get("payment_status") == "paid":
        raise HTTPException(400, "Order already paid")

    existing = await db.payments.find_one({"order_id": order["id"], "status": "created"})
    if existing:
        return {"razorpay_order_id": existing["razorpay_order_id"], "amount": int(round(order["grand_total"] * 100)), "currency": "INR", "key_id": RZP_KEY}

    amount_paise = int(round(order["grand_total"] * 100))
    try:
        rz = _client().order.create({"amount": amount_paise, "currency": "INR", "receipt": order["id"][:40], "payment_capture": 1})
    except Exception as e:
        await db.payments.insert_one({
            "id": new_id(), "order_id": order["id"], "user_id": user["id"],
            "razorpay_order_id": None, "amount": order["grand_total"], "currency": "INR",
            "status": "failed", "error": str(e), "created_at": now_utc().isoformat(),
        })
        raise HTTPException(502, f"Razorpay order creation failed: {e}")

    payment = {
        "id": new_id(), "order_id": order["id"], "user_id": user["id"],
        "razorpay_order_id": rz["id"], "razorpay_payment_id": None, "razorpay_signature": None,
        "amount": order["grand_total"], "currency": "INR", "status": "created",
        "created_at": now_utc().isoformat(),
    }
    await db.payments.insert_one(payment)
    return {"razorpay_order_id": rz["id"], "amount": amount_paise, "currency": "INR", "key_id": RZP_KEY}


@router.post("/razorpay/verify")
async def verify_razorpay(body: VerifyIn, request: Request):
    user = await get_current_user(request)
    payment = await db.payments.find_one({"razorpay_order_id": body.razorpay_order_id, "order_id": body.order_id})
    if not payment or payment["user_id"] != user["id"]:
        raise HTTPException(404, "Payment record not found")

    expected = hmac.new(RZP_SECRET.encode(), f"{body.razorpay_order_id}|{body.razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, body.razorpay_signature):
        await db.payments.update_one({"id": payment["id"]}, {"$set": {"status": "failed", "razorpay_payment_id": body.razorpay_payment_id, "error": "signature mismatch"}})
        raise HTTPException(400, "Payment verification failed: invalid signature")

    await db.payments.update_one(
        {"id": payment["id"]},
        {"$set": {"status": "paid", "razorpay_payment_id": body.razorpay_payment_id,
                  "razorpay_signature": body.razorpay_signature, "paid_at": now_utc().isoformat()}},
    )
    await db.orders.update_one(
        {"id": body.order_id},
        {"$set": {"payment_status": "paid", "status": "confirmed", "razorpay_payment_id": body.razorpay_payment_id},
         "$push": {"status_history": {"status": "confirmed", "at": now_utc().isoformat(), "by": "razorpay"}}},
    )
    return {"status": "paid", "order_id": body.order_id}


@router.get("")
async def my_payments(request: Request):
    user = await get_current_user(request)
    return await db.payments.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
