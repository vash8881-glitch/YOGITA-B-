import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from auth_utils import get_current_user, new_id, now_utc
from db import db
from invoice import generate_invoice_pdf

router = APIRouter(prefix="/api", tags=["orders"])

ORDER_STATUSES = ["pending", "confirmed", "packed", "out_for_delivery", "delivered", "cancelled", "returned", "refund_requested", "refunded"]


class OrderItemIn(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    qty: int


class AddressSnapIn(BaseModel):
    name: str
    mobile: str
    line1: str
    line2: str = ""
    city: str
    state: str
    pincode: str


class CreateOrderIn(BaseModel):
    items: list[OrderItemIn]
    address: AddressSnapIn
    delivery_slot: str = ""
    payment_method: str = "cod"
    coupon_code: Optional[str] = None
    redeem_points: int = 0
    use_wallet: float = 0.0
    cart_token: Optional[str] = None


class SubscriptionIn(BaseModel):
    plan: str
    items: list[OrderItemIn]
    address: AddressSnapIn
    delivery_slot: str = ""
    payment_method: str = "cod"


PLAN_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}


async def _settings():
    s = await db.settings.find_one({"key": "store"}, {"_id": 0})
    return (s or {}).get("value", {})


def _delivery_fee(delivery: dict, amount: float) -> float:
    for tier in delivery.get("fee_tiers", []):
        if tier.get("max") is None or amount <= tier["max"]:
            return float(tier["fee"])
    return 0.0


@router.post("/orders")
async def create_order(body: CreateOrderIn, request: Request):
    user = await get_current_user(request)
    if not body.items:
        raise HTTPException(400, "Cart is empty")
    settings = await _settings()
    delivery = settings.get("delivery", {})
    gst_percent = settings.get("gst_percent", 5)
    loyalty_cfg = settings.get("loyalty", {"per_amount": 100, "points": 1, "point_value": 1})

    items = []
    subtotal = 0.0
    mrp_total = 0.0
    for it in body.items:
        p = await db.products.find_one({"id": it.product_id, "is_active": True}, {"_id": 0})
        if not p:
            raise HTTPException(400, f"Product unavailable")
        price, mrp, label, stock = p["price"], p["mrp"], p["unit"], p["stock"]
        if it.variant_id:
            v = next((x for x in p.get("variants", []) if x["id"] == it.variant_id), None)
            if not v:
                raise HTTPException(400, f"Variant unavailable for {p['name']['en']}")
            price, mrp, label, stock = v["price"], v["mrp"], v["label"], v.get("stock", p["stock"])
        if it.qty < 1:
            raise HTTPException(400, "Invalid quantity")
        if stock < it.qty:
            raise HTTPException(400, f"Only {stock} left in stock for {p['name']['en']} ({label})")
        subtotal += price * it.qty
        mrp_total += mrp * it.qty
        items.append({
            "product_id": p["id"], "variant_id": it.variant_id, "name": p["name"],
            "sku": p["sku"], "unit": label, "qty": it.qty, "price": price, "mrp": mrp,
            "image": p["images"][0] if p.get("images") else "",
        })

    subtotal = round(subtotal, 2)
    coupon_discount = 0.0
    coupon_code = None
    if body.coupon_code:
        c = await db.coupons.find_one({"code": body.coupon_code.strip().upper(), "is_active": True}, {"_id": 0})
        if c and subtotal >= c.get("min_order", 0) and (not c.get("expiry") or now_utc().isoformat() <= c["expiry"]) and (not c.get("usage_limit") or c.get("used_count", 0) < c["usage_limit"]):
            coupon_discount = round(subtotal * c["value"] / 100, 2) if c["type"] == "percent" else min(c["value"], subtotal)
            if c["type"] == "percent" and c.get("max_discount"):
                coupon_discount = min(coupon_discount, c["max_discount"])
            coupon_code = c["code"]

    taxable = max(0.0, subtotal - coupon_discount)
    delivery_fee = _delivery_fee(delivery, taxable)
    gst = round(taxable * gst_percent / 100, 2)

    loyalty_discount = 0.0
    redeem = min(max(0, body.redeem_points), int(user.get("loyalty_points", 0)))
    if redeem:
        loyalty_discount = round(redeem * loyalty_cfg.get("point_value", 1), 2)

    pre_wallet_total = taxable + delivery_fee + gst - loyalty_discount
    wallet_used = round(min(max(0.0, body.use_wallet), user.get("wallet_balance", 0.0), max(0.0, pre_wallet_total)), 2)
    grand_total = round(pre_wallet_total - wallet_used, 2)
    if grand_total < 0:
        grand_total = 0.0

    min_order = delivery.get("min_order", 0)
    if subtotal < min_order:
        raise HTTPException(400, f"Minimum order value is ₹{min_order}")

    pincodes = delivery.get("pincodes", [])
    if pincodes and body.address.pincode not in pincodes:
        raise HTTPException(400, "Delivery not available for this pincode")

    order_id = "ORD-" + new_id()[:8].upper()
    earned = int(grand_total // loyalty_cfg.get("per_amount", 100)) * loyalty_cfg.get("points", 1)

    order = {
        "id": order_id,
        "user_id": user["id"],
        "customer": {"name": user.get("name"), "mobile": user.get("mobile"), "email": user.get("email")},
        "items": items,
        "address": body.address.model_dump(),
        "delivery_slot": body.delivery_slot,
        "payment_method": body.payment_method,
        "payment_status": "pending" if body.payment_method != "cod" else "cod",
        "subtotal": subtotal,
        "mrp_total": round(mrp_total, 2),
        "product_discount": round(mrp_total - subtotal, 2),
        "coupon_code": coupon_code,
        "coupon_discount": round(coupon_discount, 2),
        "delivery_fee": delivery_fee,
        "gst": gst,
        "loyalty_discount": loyalty_discount,
        "wallet_used": wallet_used,
        "grand_total": grand_total,
        "loyalty_earned": earned,
        "status": "confirmed" if body.payment_method == "cod" else "pending",
        "status_history": [{"status": "confirmed" if body.payment_method == "cod" else "pending", "at": now_utc().isoformat()}],
        "created_at": now_utc().isoformat(),
    }

    for it in body.items:
        if it.variant_id:
            await db.products.update_one({"id": it.product_id, "variants.id": it.variant_id}, {"$inc": {"variants.$.stock": -it.qty, "popularity": it.qty}})
        else:
            await db.products.update_one({"id": it.product_id}, {"$inc": {"stock": -it.qty, "popularity": it.qty}})

    if coupon_code:
        await db.coupons.update_one({"code": coupon_code}, {"$inc": {"used_count": 1}})
    wallet_ops = []
    if wallet_used:
        wallet_ops.append({"id": new_id(), "user_id": user["id"], "type": "debit", "amount": wallet_used,
                           "reason": f"Order {order_id}", "created_at": now_utc().isoformat()})
    loyalty_ops = []
    if redeem:
        loyalty_ops.append({"id": new_id(), "user_id": user["id"], "type": "redeemed", "points": -redeem,
                            "reason": f"Order {order_id}", "created_at": now_utc().isoformat()})
    if earned:
        loyalty_ops.append({"id": new_id(), "user_id": user["id"], "type": "earned", "points": earned,
                            "reason": f"Order {order_id}", "created_at": now_utc().isoformat()})
    if wallet_ops:
        await db.wallet_transactions.insert_many(wallet_ops)
    if loyalty_ops:
        await db.loyalty_transactions.insert_many(loyalty_ops)
    await db.users.update_one({"id": user["id"]}, {"$inc": {"wallet_balance": -wallet_used, "loyalty_points": earned - redeem}})

    invoice_no = "INV-" + new_id()[:8].upper()
    invoice_path = generate_invoice_pdf(order, settings, invoice_no)
    order["invoice"] = {"invoice_no": invoice_no, "path": invoice_path, "generated_at": now_utc().isoformat()}
    await db.orders.insert_one(order)
    order.pop("_id", None)

    if body.cart_token:
        await db.carts.update_one({"cart_token": body.cart_token}, {"$set": {"converted": True, "items": [], "updated_at": now_utc().isoformat()}})

    return order


@router.get("/orders")
async def my_orders(request: Request):
    user = await get_current_user(request)
    return await db.orders.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)


@router.get("/orders/{order_id}")
async def order_detail(order_id: str, request: Request):
    user = await get_current_user(request)
    q = {"id": order_id} if user.get("role") != "customer" else {"id": order_id, "user_id": user["id"]}
    order = await db.orders.find_one(q, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, request: Request):
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id, "user_id": user["id"]})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["status"] in ("delivered", "cancelled", "refunded", "returned"):
        raise HTTPException(400, f"Cannot cancel order in {order['status']} status")
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": "cancelled"}, "$push": {"status_history": {"status": "cancelled", "at": now_utc().isoformat()}}},
    )
    for it in order["items"]:
        if it.get("variant_id"):
            await db.products.update_one({"id": it["product_id"], "variants.id": it["variant_id"]}, {"$inc": {"variants.$.stock": it["qty"]}})
        else:
            await db.products.update_one({"id": it["product_id"]}, {"$inc": {"stock": it["qty"]}})
    if order.get("coupon_code"):
        await db.coupons.update_one({"code": order["coupon_code"], "used_count": {"$gt": 0}}, {"$inc": {"used_count": -1}})
    settings = await _settings()
    pv = settings.get("loyalty", {}).get("point_value", 1) or 1
    redeemed = int(order.get("loyalty_discount", 0) / pv)
    if order.get("loyalty_earned") or redeemed:
        await db.users.update_one({"id": user["id"]}, {"$inc": {"loyalty_points": redeemed - order.get("loyalty_earned", 0)}})
        await db.loyalty_transactions.insert_one({"id": new_id(), "user_id": user["id"], "type": "reversal",
                                                  "points": redeemed - order.get("loyalty_earned", 0),
                                                  "reason": f"Cancel {order_id}", "created_at": now_utc().isoformat()})
    if order.get("wallet_used"):
        await db.users.update_one({"id": user["id"]}, {"$inc": {"wallet_balance": order["wallet_used"]}})
        await db.wallet_transactions.insert_one({"id": new_id(), "user_id": user["id"], "type": "credit",
                                                 "amount": order["wallet_used"], "reason": f"Refund {order_id}",
                                                 "created_at": now_utc().isoformat()})
    return {"message": "Order cancelled"}


@router.post("/orders/{order_id}/return")
async def return_order(order_id: str, request: Request):
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id, "user_id": user["id"]})
    if not order:
        raise HTTPException(404, "Order not found")
    if order["status"] != "delivered":
        raise HTTPException(400, "Only delivered orders can be returned")
    await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": "refund_requested"}, "$push": {"status_history": {"status": "refund_requested", "at": now_utc().isoformat()}}},
    )
    return {"message": "Return/refund requested"}


@router.get("/orders/{order_id}/whatsapp")
async def whatsapp_link(order_id: str, request: Request):
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or (user.get("role") == "customer" and order["user_id"] != user["id"]):
        raise HTTPException(404, "Order not found")
    settings = await _settings()
    number = settings.get("whatsapp", os.environ.get("STORE_WHATSAPP", ""))
    lines = [
        f"New Order - {settings.get('store_name', 'Store')}",
        f"Customer: {order['customer'].get('name')}",
        f"Order ID: {order['id']}",
        "Items:",
    ]
    for it in order["items"]:
        lines.append(f"- {it['name']['en']} ({it['unit']}) x {it['qty']} = ₹{round(it['price'] * it['qty'], 2)}")
    lines += [
        f"Subtotal: ₹{order['subtotal']}",
        f"Delivery: ₹{order['delivery_fee']}",
        f"Total: ₹{order['grand_total']}",
        f"Address: {order['address']['line1']}, {order['address']['city']} - {order['address']['pincode']}",
        f"Payment: {order['payment_method'].upper()}",
    ]
    import urllib.parse
    url = f"https://wa.me/{number}?text=" + urllib.parse.quote("\n".join(lines))
    return {"url": url}


@router.get("/invoices/{order_id}/download")
async def download_invoice(order_id: str, request: Request):
    user = await get_current_user(request)
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order or (user.get("role") == "customer" and order["user_id"] != user["id"]):
        raise HTTPException(404, "Order not found")
    path = order.get("invoice", {}).get("path")
    if not path or not os.path.exists(path):
        settings = await _settings()
        path = generate_invoice_pdf(order, settings, order.get("invoice", {}).get("invoice_no", "INV-" + new_id()[:8].upper()))
    return FileResponse(path, media_type="application/pdf", filename=f"{order.get('invoice', {}).get('invoice_no', order_id)}.pdf")


@router.get("/loyalty")
async def loyalty(request: Request):
    user = await get_current_user(request)
    txns = await db.loyalty_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    settings = await _settings()
    return {"points": user.get("loyalty_points", 0), "transactions": txns, "rule": settings.get("loyalty", {})}


@router.get("/wallet")
async def wallet(request: Request):
    user = await get_current_user(request)
    txns = await db.wallet_transactions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"balance": user.get("wallet_balance", 0.0), "transactions": txns}


@router.get("/subscriptions")
async def my_subscriptions(request: Request):
    user = await get_current_user(request)
    return await db.subscriptions.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)


@router.post("/subscriptions")
async def create_subscription(body: SubscriptionIn, request: Request):
    user = await get_current_user(request)
    if body.plan not in PLAN_DAYS:
        raise HTTPException(400, "Invalid plan")
    if not body.items:
        raise HTTPException(400, "Add at least one product")
    resolved = []
    for it in body.items:
        p = await db.products.find_one({"id": it.product_id, "is_active": True}, {"_id": 0})
        if not p:
            raise HTTPException(400, "A product in your plan is unavailable")
        resolved.append({"product_id": p["id"], "name": p["name"], "qty": it.qty,
                         "price": p["price"], "unit": p["unit"],
                         "image": p["images"][0] if p.get("images") else ""})
    next_date = (now_utc() + timedelta(days=PLAN_DAYS[body.plan])).isoformat()
    doc = {
        "id": new_id(), "user_id": user["id"],
        "customer": {"name": user.get("name"), "mobile": user.get("mobile")},
        "plan": body.plan, "items": resolved, "address": body.address.model_dump(),
        "delivery_slot": body.delivery_slot, "payment_method": body.payment_method,
        "status": "active", "next_delivery_at": next_date, "created_at": now_utc().isoformat(),
    }
    await db.subscriptions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/subscriptions/{sub_id}")
async def update_subscription(sub_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    action = body.get("action")
    sub = await db.subscriptions.find_one({"id": sub_id, "user_id": user["id"]})
    if not sub:
        raise HTTPException(404, "Subscription not found")
    updates = {}
    if action == "pause":
        updates["status"] = "paused"
    elif action == "resume":
        updates["status"] = "active"
        updates["next_delivery_at"] = (now_utc() + timedelta(days=PLAN_DAYS.get(sub["plan"], 1))).isoformat()
    elif action == "cancel":
        updates["status"] = "cancelled"
    elif action == "update":
        if body.get("items"):
            updates["items"] = body["items"]
        if body.get("address"):
            updates["address"] = body["address"]
        if body.get("delivery_slot"):
            updates["delivery_slot"] = body["delivery_slot"]
    else:
        raise HTTPException(400, "Invalid action")
    await db.subscriptions.update_one({"id": sub_id}, {"$set": updates})
    return await db.subscriptions.find_one({"id": sub_id}, {"_id": 0})
