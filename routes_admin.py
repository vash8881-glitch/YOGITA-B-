from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel

from auth_utils import hash_pw, log_activity, new_id, now_utc, require_admin
from db import db
from routes_orders import ORDER_STATUSES

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOAD_DIR = __import__("pathlib").Path(__file__).parent / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD = 5 * 1024 * 1024


class ProductIn(BaseModel):
    sku: str
    name: dict
    description: dict = {}
    category_id: str
    price: float
    mrp: float
    cost: float = 0.0
    unit: str = "1 kg"
    stock: int = 0
    low_stock_threshold: int = 10
    images: list = []
    badges: list = []
    is_active: bool = True
    is_fresh: bool = False
    variants: list = []


class CategoryIn(BaseModel):
    name: dict
    image: str = ""
    sort_order: int = 0
    is_active: bool = True


class CouponIn(BaseModel):
    code: str
    type: str = "percent"
    value: float
    min_order: float = 0.0
    max_discount: Optional[float] = None
    expiry: Optional[str] = None
    usage_limit: Optional[int] = None
    is_active: bool = True


class OfferIn(BaseModel):
    product_id: str
    offer_price: float
    message: str = ""
    start_at: str
    end_at: str
    is_active: bool = True


class StatusIn(BaseModel):
    status: str
    reason: str = ""


class StaffIn(BaseModel):
    name: str
    email: str
    password: str
    role: str = "admin"


@router.get("/dashboard")
async def dashboard(request: Request):
    await require_admin(request, "dashboard")
    now = now_utc()
    today = now.date().isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()

    async def sales_since(since):
        agg = await db.orders.aggregate([
            {"$match": {"created_at": {"$gte": since}, "status": {"$nin": ["cancelled", "refunded"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$grand_total"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        return round(agg[0]["total"], 2) if agg else 0.0

    status_counts = {}
    for s in await db.orders.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]).to_list(20):
        status_counts[s["_id"]] = s["n"]

    revenue_chart = []
    for i in range(13, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        revenue_chart.append({"date": day[5:], "revenue": 0.0})
    chart_map = {r["date"]: r for r in revenue_chart}
    async for row in db.orders.aggregate([
        {"$match": {"created_at": {"$gte": (now - timedelta(days=14)).isoformat()}, "status": {"$nin": ["cancelled", "refunded"]}}},
        {"$group": {"_id": {"$substr": ["$created_at", 5, 5]}, "revenue": {"$sum": "$grand_total"}}},
    ]):
        if row["_id"] in chart_map:
            chart_map[row["_id"]]["revenue"] = round(row["revenue"], 2)

    top_products = await db.products.find({"is_active": True}, {"_id": 0, "id": 1, "name": 1, "popularity": 1, "price": 1, "images": 1, "stock": 1}).sort("popularity", -1).limit(5).to_list(5)
    low_stock = await db.products.find({"$expr": {"$lte": ["$stock", "$low_stock_threshold"]}, "is_active": True}, {"_id": 0, "id": 1, "name": 1, "stock": 1, "low_stock_threshold": 1}).to_list(20)
    recent_orders = await db.orders.find({}, {"_id": 0}).sort("created_at", -1).limit(6).to_list(6)
    recent_activity = await db.activity_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(8).to_list(8)

    return {
        "today_sales": await sales_since(today),
        "week_sales": await sales_since(week_ago),
        "month_sales": await sales_since(month_ago),
        "total_orders": await db.orders.count_documents({}),
        "pending_orders": status_counts.get("pending", 0) + status_counts.get("confirmed", 0),
        "delivered_orders": status_counts.get("delivered", 0),
        "cancelled_orders": status_counts.get("cancelled", 0),
        "total_customers": await db.users.count_documents({"role": "customer"}),
        "low_stock_count": len(low_stock),
        "active_subscriptions": await db.subscriptions.count_documents({"status": "active"}),
        "status_counts": status_counts,
        "revenue_chart": revenue_chart,
        "top_products": top_products,
        "low_stock": low_stock,
        "recent_orders": recent_orders,
        "recent_activity": recent_activity,
    }


@router.get("/reports/revenue")
async def revenue_report(request: Request, period: str = "daily"):
    await require_admin(request, "reports")
    now = now_utc()
    days = {"daily": 30, "weekly": 90, "monthly": 365, "yearly": 730}.get(period, 30)
    fmt = {"daily": (0, 10), "weekly": (0, 10), "monthly": (0, 7), "yearly": (0, 4)}[period]
    agg = await db.orders.aggregate([
        {"$match": {"created_at": {"$gte": (now - timedelta(days=days)).isoformat()}, "status": {"$nin": ["cancelled", "refunded"]}}},
        {"$group": {"_id": {"$substr": ["$created_at", fmt[0], fmt[1]]}, "revenue": {"$sum": "$grand_total"}, "orders": {"$sum": 1}, "gst": {"$sum": "$gst"}}},
        {"$sort": {"_id": 1}},
    ]).to_list(400)
    profit = 0.0
    cost_map = {p["id"]: p.get("cost", 0.0) for p in await db.products.find({}, {"_id": 0, "id": 1, "cost": 1}).to_list(1000)}
    async for o in db.orders.find({"created_at": {"$gte": (now - timedelta(days=days)).isoformat()}, "status": {"$nin": ["cancelled", "refunded"]}}, {"_id": 0, "items": 1}):
        for it in o.get("items", []):
            profit += (it["price"] - cost_map.get(it["product_id"], it["price"])) * it["qty"]
    return {"rows": [{"period": r["_id"], "revenue": round(r["revenue"], 2), "orders": r["orders"], "gst": round(r.get("gst", 0), 2)} for r in agg],
            "profit": round(profit, 2)}


@router.get("/reports/gst")
async def gst_report(request: Request):
    await require_admin(request, "reports")
    agg = await db.orders.aggregate([
        {"$match": {"status": {"$nin": ["cancelled", "refunded"]}}},
        {"$group": {"_id": {"$substr": ["$created_at", 0, 7]}, "taxable": {"$sum": "$subtotal"}, "gst": {"$sum": "$gst"}, "orders": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
    ]).to_list(24)
    return [{"month": r["_id"], "taxable": round(r["taxable"], 2), "gst": round(r["gst"], 2), "orders": r["orders"]} for r in agg]


# ---------- Products ----------
@router.get("/products")
async def admin_products(request: Request, q: Optional[str] = None, category: Optional[str] = None):
    await require_admin(request, "products")
    query = {}
    if q:
        query["$or"] = [{"name.en": {"$regex": q, "$options": "i"}}, {"sku": {"$regex": q, "$options": "i"}}]
    if category:
        query["category_id"] = category
    return await db.products.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/products")
async def create_product(body: ProductIn, request: Request):
    admin = await require_admin(request, "products")
    if await db.products.find_one({"sku": body.sku}):
        raise HTTPException(400, "SKU already exists")
    doc = body.model_dump()
    doc["id"] = new_id()
    doc["discount_percent"] = round((1 - doc["price"] / doc["mrp"]) * 100) if doc["mrp"] > doc["price"] else 0
    doc.update({"rating": 0.0, "rating_count": 0, "popularity": 0, "created_at": now_utc().isoformat()})
    await db.products.insert_one(doc)
    await log_activity(admin, "create_product", doc["sku"], doc["name"].get("en", ""))
    doc.pop("_id", None)
    return doc


@router.put("/products/{pid}")
async def update_product(pid: str, body: ProductIn, request: Request):
    admin = await require_admin(request, "products")
    doc = body.model_dump()
    doc["discount_percent"] = round((1 - doc["price"] / doc["mrp"]) * 100) if doc["mrp"] > doc["price"] else 0
    res = await db.products.update_one({"id": pid}, {"$set": doc})
    if not res.matched_count:
        raise HTTPException(404, "Product not found")
    await log_activity(admin, "update_product", body.sku)
    return await db.products.find_one({"id": pid}, {"_id": 0})


@router.delete("/products/{pid}")
async def delete_product(pid: str, request: Request):
    admin = await require_admin(request, "products")
    await db.products.delete_one({"id": pid})
    await log_activity(admin, "delete_product", pid)
    return {"message": "Deleted"}


@router.post("/products/{pid}/duplicate")
async def duplicate_product(pid: str, request: Request):
    admin = await require_admin(request, "products")
    p = await db.products.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Product not found")
    p["id"] = new_id()
    p["sku"] = p["sku"] + "-COPY"
    p["name"] = {k: v + " (Copy)" for k, v in p["name"].items()}
    p["created_at"] = now_utc().isoformat()
    await db.products.insert_one(p)
    await log_activity(admin, "duplicate_product", p["sku"])
    p.pop("_id", None)
    return p


@router.patch("/products/{pid}/stock")
async def update_stock(pid: str, request: Request):
    admin = await require_admin(request, "inventory")
    body = await request.json()
    await db.products.update_one({"id": pid}, {"$set": {"stock": int(body.get("stock", 0))}})
    await log_activity(admin, "update_stock", pid, str(body.get("stock")))
    return await db.products.find_one({"id": pid}, {"_id": 0})


# ---------- Categories ----------
@router.post("/categories")
async def create_category(body: CategoryIn, request: Request):
    admin = await require_admin(request, "categories")
    doc = body.model_dump()
    doc["id"] = new_id()
    await db.categories.insert_one(doc)
    await log_activity(admin, "create_category", doc["name"].get("en", ""))
    doc.pop("_id", None)
    return doc


@router.put("/categories/{cid}")
async def update_category(cid: str, body: CategoryIn, request: Request):
    admin = await require_admin(request, "categories")
    await db.categories.update_one({"id": cid}, {"$set": body.model_dump()})
    await log_activity(admin, "update_category", cid)
    return await db.categories.find_one({"id": cid}, {"_id": 0})


@router.delete("/categories/{cid}")
async def delete_category(cid: str, request: Request):
    admin = await require_admin(request, "categories")
    await db.categories.delete_one({"id": cid})
    await log_activity(admin, "delete_category", cid)
    return {"message": "Deleted"}


# ---------- Orders ----------
@router.get("/orders")
async def admin_orders(request: Request, status: Optional[str] = None, q: Optional[str] = None):
    await require_admin(request, "orders")
    query = {}
    if status:
        query["status"] = status
    if q:
        query["$or"] = [{"id": {"$regex": q, "$options": "i"}}, {"customer.name": {"$regex": q, "$options": "i"}}, {"customer.mobile": {"$regex": q, "$options": "i"}}]
    return await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(300)


@router.patch("/orders/{oid}/status")
async def admin_order_status(oid: str, body: StatusIn, request: Request):
    admin = await require_admin(request, "orders")
    if body.status not in ORDER_STATUSES:
        raise HTTPException(400, f"Invalid status. Allowed: {', '.join(ORDER_STATUSES)}")
    order = await db.orders.find_one({"id": oid})
    if not order:
        raise HTTPException(404, "Order not found")
    updates = {"status": body.status}
    if body.reason:
        updates["status_reason"] = body.reason
    await db.orders.update_one({"id": oid}, {"$set": updates, "$push": {"status_history": {"status": body.status, "at": now_utc().isoformat(), "by": admin.get("name")}}})
    if body.status in ("refunded", "cancelled") and order["status"] not in ("refunded", "cancelled"):
        refund = order["grand_total"]
        await db.users.update_one({"id": order["user_id"]}, {"$inc": {"wallet_balance": refund}})
        await db.wallet_transactions.insert_one({"id": new_id(), "user_id": order["user_id"], "type": "credit",
                                                 "amount": refund, "reason": f"Refund for {oid}", "created_at": now_utc().isoformat()})
        await db.orders.update_one({"id": oid}, {"$set": {"payment_status": "refunded"}})
    if body.status == "delivered":
        await db.orders.update_one({"id": oid}, {"$set": {"payment_status": "paid"}})
    await log_activity(admin, "order_status", oid, body.status)
    return await db.orders.find_one({"id": oid}, {"_id": 0})


# ---------- Customers ----------
@router.get("/customers")
async def admin_customers(request: Request):
    await require_admin(request, "customers")
    customers = await db.users.find({"role": "customer"}, {"_id": 0, "password_hash": 0}).to_list(500)
    out = []
    for c in customers:
        agg = await db.orders.aggregate([
            {"$match": {"user_id": c["id"], "status": {"$nin": ["cancelled", "refunded"]}}},
            {"$group": {"_id": None, "total": {"$sum": "$grand_total"}, "n": {"$sum": 1}, "last": {"$max": "$created_at"}}},
        ]).to_list(1)
        total = agg[0]["total"] if agg else 0
        orders = agg[0]["n"] if agg else 0
        last = agg[0]["last"] if agg else None
        if orders == 0:
            group = "New Customer"
        elif total >= 5000:
            group = "VIP Customer"
        elif last and last < (now_utc() - timedelta(days=30)).isoformat():
            group = "Inactive Customer"
        else:
            group = "Regular Customer"
        c.update({"total_spent": round(total, 2), "order_count": orders, "group": group})
        out.append(c)
    return out


@router.get("/customers/{cid}")
async def admin_customer_detail(cid: str, request: Request):
    await require_admin(request, "customers")
    c = await db.users.find_one({"id": cid}, {"_id": 0, "password_hash": 0})
    if not c:
        raise HTTPException(404, "Customer not found")
    orders = await db.orders.find({"user_id": cid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    subs = await db.subscriptions.find({"user_id": cid}, {"_id": 0}).to_list(20)
    addresses = await db.addresses.find({"user_id": cid}, {"_id": 0}).to_list(10)
    cart = await db.carts.find_one({"user_id": cid}, {"_id": 0})
    return {"customer": c, "orders": orders, "subscriptions": subs, "addresses": addresses, "cart": cart}


@router.post("/customers/{cid}/wallet")
async def admin_wallet_adjust(cid: str, request: Request):
    admin = await require_admin(request, "customers")
    body = await request.json()
    amount = float(body.get("amount", 0))
    if amount == 0:
        raise HTTPException(400, "Amount required")
    await db.users.update_one({"id": cid}, {"$inc": {"wallet_balance": amount}})
    await db.wallet_transactions.insert_one({"id": new_id(), "user_id": cid, "type": "credit" if amount > 0 else "debit",
                                             "amount": abs(amount), "reason": body.get("reason", "Admin adjustment"),
                                             "created_at": now_utc().isoformat()})
    await log_activity(admin, "wallet_adjust", cid, str(amount))
    return {"message": "Wallet updated"}


# ---------- Coupons ----------
@router.get("/coupons")
async def admin_coupons(request: Request):
    await require_admin(request, "coupons")
    return await db.coupons.find({}, {"_id": 0}).sort("code", 1).to_list(200)


@router.post("/coupons")
async def create_coupon(body: CouponIn, request: Request):
    admin = await require_admin(request, "coupons")
    code = body.code.strip().upper()
    if await db.coupons.find_one({"code": code}):
        raise HTTPException(400, "Coupon code exists")
    doc = body.model_dump()
    doc.update({"id": new_id(), "code": code, "used_count": 0})
    await db.coupons.insert_one(doc)
    await log_activity(admin, "create_coupon", code)
    doc.pop("_id", None)
    return doc


@router.put("/coupons/{cid}")
async def update_coupon(cid: str, body: CouponIn, request: Request):
    admin = await require_admin(request, "coupons")
    doc = body.model_dump()
    doc["code"] = doc["code"].strip().upper()
    await db.coupons.update_one({"id": cid}, {"$set": doc})
    await log_activity(admin, "update_coupon", doc["code"])
    return await db.coupons.find_one({"id": cid}, {"_id": 0})


@router.delete("/coupons/{cid}")
async def delete_coupon(cid: str, request: Request):
    admin = await require_admin(request, "coupons")
    await db.coupons.delete_one({"id": cid})
    await log_activity(admin, "delete_coupon", cid)
    return {"message": "Deleted"}


# ---------- Offers ----------
@router.get("/offers")
async def admin_offers(request: Request):
    await require_admin(request, "offers")
    return await db.offers.find({}, {"_id": 0}).sort("start_at", -1).to_list(100)


@router.post("/offers")
async def create_offer(body: OfferIn, request: Request):
    admin = await require_admin(request, "offers")
    p = await db.products.find_one({"id": body.product_id}, {"_id": 0, "name": 1, "images": 1, "price": 1, "mrp": 1, "unit": 1})
    if not p:
        raise HTTPException(404, "Product not found")
    doc = body.model_dump()
    doc.update({"id": new_id(), "product": p, "created_at": now_utc().isoformat(),
                "discount_percent": round((1 - body.offer_price / p["mrp"]) * 100) if p["mrp"] > body.offer_price else 0})
    await db.offers.insert_one(doc)
    await log_activity(admin, "create_offer", p["name"].get("en", ""))
    doc.pop("_id", None)
    return doc


@router.put("/offers/{oid}")
async def update_offer(oid: str, body: OfferIn, request: Request):
    admin = await require_admin(request, "offers")
    await db.offers.update_one({"id": oid}, {"$set": body.model_dump()})
    await log_activity(admin, "update_offer", oid)
    return await db.offers.find_one({"id": oid}, {"_id": 0})


@router.delete("/offers/{oid}")
async def delete_offer(oid: str, request: Request):
    admin = await require_admin(request, "offers")
    await db.offers.delete_one({"id": oid})
    await log_activity(admin, "delete_offer", oid)
    return {"message": "Deleted"}


# ---------- Subscriptions ----------
@router.get("/subscriptions")
async def admin_subscriptions(request: Request):
    await require_admin(request, "subscriptions")
    return await db.subscriptions.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@router.patch("/subscriptions/{sid}")
async def admin_subscription_status(sid: str, request: Request):
    admin = await require_admin(request, "subscriptions")
    body = await request.json()
    await db.subscriptions.update_one({"id": sid}, {"$set": {"status": body.get("status", "active")}})
    await log_activity(admin, "subscription_status", sid, body.get("status", ""))
    return await db.subscriptions.find_one({"id": sid}, {"_id": 0})


# ---------- Abandoned carts ----------
@router.get("/abandoned-carts")
async def abandoned_carts(request: Request):
    await require_admin(request, "dashboard")
    cutoff = (now_utc() - timedelta(minutes=60)).isoformat()
    carts = await db.carts.find({"converted": False, "items.0": {"$exists": True}, "updated_at": {"$lt": cutoff}}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    for c in carts:
        c["cart_value"] = round(sum(i.get("price", 0) * i.get("qty", 1) for i in c.get("items", [])), 2)
    return carts


@router.post("/abandoned-carts/{cid}/remind")
async def remind_cart(cid: str, request: Request):
    admin = await require_admin(request, "dashboard")
    await db.carts.update_one({"id": cid}, {"$set": {"reminder_sent": True, "reminder_at": now_utc().isoformat()}})
    await log_activity(admin, "cart_reminder", cid)
    return {"message": "Reminder marked as sent. Configure WhatsApp API credentials in .env for automated messaging."}


# ---------- Settings ----------
@router.get("/settings")
async def get_settings(request: Request):
    await require_admin(request, "settings")
    s = await db.settings.find_one({"key": "store"}, {"_id": 0})
    return s["value"] if s else {}


@router.put("/settings")
async def put_settings(request: Request):
    admin = await require_admin(request, "settings")
    body = await request.json()
    await db.settings.update_one({"key": "store"}, {"$set": {"value": body}}, upsert=True)
    await log_activity(admin, "update_settings", "store")
    return body


# ---------- Activity logs ----------
@router.get("/logs")
async def activity_logs(request: Request):
    await require_admin(request, "logs")
    return await db.activity_logs.find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)


# ---------- Staff / RBAC ----------
@router.get("/staff")
async def list_staff(request: Request):
    await require_admin(request, "settings")
    return await db.users.find({"role": {"$ne": "customer"}}, {"_id": 0, "password_hash": 0}).to_list(100)


@router.post("/staff")
async def create_staff(body: StaffIn, request: Request):
    admin = await require_admin(request, "settings")
    email = body.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(400, "Email already registered")
    if body.role not in ("admin", "editor", "sales_manager", "inventory_manager", "support"):
        raise HTTPException(400, "Invalid role")
    doc = {"id": new_id(), "name": body.name, "email": email, "password_hash": hash_pw(body.password),
           "role": body.role, "created_at": now_utc().isoformat()}
    await db.users.insert_one(doc)
    await log_activity(admin, "create_staff", email, body.role)
    return {"id": doc["id"], "name": doc["name"], "email": email, "role": doc["role"]}


# ---------- Payments ----------
@router.get("/payments")
async def admin_payments(request: Request):
    await require_admin(request, "orders")
    return await db.payments.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


# ---------- Upload ----------
@router.post("/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    await require_admin(request)
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only JPG, PNG, WEBP, GIF images allowed")
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, "Image too large (max 5MB)")
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "png"
    fname = f"{new_id()}.{ext}"
    (UPLOAD_DIR / fname).write_bytes(data)
    return {"url": f"/api/uploads/{fname}"}
