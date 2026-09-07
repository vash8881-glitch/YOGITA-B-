from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from auth_utils import get_current_user, get_optional_user, new_id, now_utc
from db import db

router = APIRouter(prefix="/api", tags=["store"])


class CartSyncIn(BaseModel):
    cart_token: str
    items: list


class WishlistIn(BaseModel):
    product_id: str


class AddressIn(BaseModel):
    label: str = "Home"
    name: str
    mobile: str
    line1: str
    line2: str = ""
    city: str
    state: str
    pincode: str
    is_default: bool = False


class CouponValidateIn(BaseModel):
    code: str
    subtotal: float


class ReviewIn(BaseModel):
    rating: int
    comment: str = ""


@router.get("/settings/public")
async def public_settings():
    s = await db.settings.find_one({"key": "store"}, {"_id": 0})
    if not s:
        return {}
    val = s["value"]
    pay = val.get("payments", {})
    val["payments"] = {
        "cod": pay.get("cod", True),
        "upi": pay.get("upi", True),
        "upi_id": pay.get("upi_id", ""),
        "razorpay_enabled": bool(pay.get("razorpay_key_id")),
        "razorpay_key_id": pay.get("razorpay_key_id", ""),
    }
    return val


@router.get("/categories")
async def list_categories():
    return await db.categories.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(100)


@router.get("/products")
async def list_products(
    q: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    in_stock: Optional[bool] = None,
    fresh: Optional[bool] = None,
    discount: Optional[bool] = None,
    sort: str = "popularity",
    page: int = 1,
    limit: int = 24,
):
    query = {"is_active": True}
    if q:
        query["$or"] = [
            {"name.en": {"$regex": q, "$options": "i"}},
            {"name.hi": {"$regex": q, "$options": "i"}},
            {"name.kn": {"$regex": q, "$options": "i"}},
            {"name.mr": {"$regex": q, "$options": "i"}},
            {"sku": {"$regex": q, "$options": "i"}},
        ]
    if category:
        query["category_id"] = category
    if min_price is not None or max_price is not None:
        query["price"] = {}
        if min_price is not None:
            query["price"]["$gte"] = min_price
        if max_price is not None:
            query["price"]["$lte"] = max_price
    if min_rating:
        query["rating"] = {"$gte": min_rating}
    if in_stock:
        query["stock"] = {"$gt": 0}
    if fresh:
        query["is_fresh"] = True
    if discount:
        query["$expr"] = {"$lt": ["$price", "$mrp"]}
    sort_map = {
        "price_low": ("price", 1), "price_high": ("price", -1),
        "popularity": ("popularity", -1), "rating": ("rating", -1),
        "newest": ("created_at", -1), "discount": ("discount_percent", -1),
    }
    field, direction = sort_map.get(sort, ("popularity", -1))
    total = await db.products.count_documents(query)
    items = await db.products.find(query, {"_id": 0}).sort(field, direction).skip((page - 1) * limit).limit(limit).to_list(limit)
    return {"items": items, "total": total, "page": page, "pages": max(1, (total + limit - 1) // limit)}


@router.get("/products/suggestions")
async def suggestions(q: str = Query(..., min_length=1)):
    items = await db.products.find(
        {"is_active": True, "$or": [
            {"name.en": {"$regex": q, "$options": "i"}},
            {"name.hi": {"$regex": q, "$options": "i"}},
            {"name.kn": {"$regex": q, "$options": "i"}},
            {"name.mr": {"$regex": q, "$options": "i"}},
        ]},
        {"_id": 0, "id": 1, "name": 1, "price": 1, "unit": 1, "images": 1},
    ).limit(8).to_list(8)
    return items


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    p = await db.products.find_one({"id": product_id, "is_active": True}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Product not found")
    related = await db.products.find(
        {"category_id": p["category_id"], "id": {"$ne": p["id"]}, "is_active": True}, {"_id": 0}
    ).limit(6).to_list(6)
    reviews = await db.reviews.find({"product_id": p["id"]}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return {"product": p, "related": related, "reviews": reviews}


@router.get("/banners")
async def banners():
    return await db.banners.find({"is_active": True}, {"_id": 0}).sort("sort_order", 1).to_list(20)


@router.get("/offers/active")
async def active_offers():
    now = now_utc().isoformat()
    return await db.offers.find(
        {"is_active": True, "start_at": {"$lte": now}, "end_at": {"$gte": now}}, {"_id": 0}
    ).to_list(10)


@router.post("/cart/sync")
async def sync_cart(body: CartSyncIn, request: Request):
    user = await get_optional_user(request)
    doc = {
        "cart_token": body.cart_token,
        "user_id": user["id"] if user else None,
        "customer_mobile": user.get("mobile") if user else None,
        "customer_name": user.get("name") if user else None,
        "items": body.items,
        "updated_at": now_utc().isoformat(),
        "reminder_sent": False,
        "converted": False,
    }
    existing = await db.carts.find_one({"cart_token": body.cart_token})
    if existing:
        await db.carts.update_one({"cart_token": body.cart_token}, {"$set": doc})
    else:
        doc["id"] = new_id()
        doc["created_at"] = now_utc().isoformat()
        await db.carts.insert_one(doc)
    return {"message": "ok"}


@router.get("/wishlist")
async def get_wishlist(request: Request):
    user = await get_current_user(request)
    doc = await db.wishlists.find_one({"user_id": user["id"]}, {"_id": 0})
    ids = doc["product_ids"] if doc else []
    products = await db.products.find({"id": {"$in": ids}, "is_active": True}, {"_id": 0}).to_list(100) if ids else []
    return {"product_ids": ids, "products": products}


@router.post("/wishlist")
async def add_wishlist(body: WishlistIn, request: Request):
    user = await get_current_user(request)
    await db.wishlists.update_one(
        {"user_id": user["id"]},
        {"$addToSet": {"product_ids": body.product_id}, "$setOnInsert": {"id": new_id()}},
        upsert=True,
    )
    return {"message": "Added to wishlist"}


@router.delete("/wishlist/{product_id}")
async def remove_wishlist(product_id: str, request: Request):
    user = await get_current_user(request)
    await db.wishlists.update_one({"user_id": user["id"]}, {"$pull": {"product_ids": product_id}})
    return {"message": "Removed from wishlist"}


@router.get("/addresses")
async def list_addresses(request: Request):
    user = await get_current_user(request)
    return await db.addresses.find({"user_id": user["id"]}, {"_id": 0}).to_list(20)


@router.post("/addresses")
async def create_address(body: AddressIn, request: Request):
    user = await get_current_user(request)
    doc = body.model_dump()
    doc.update({"id": new_id(), "user_id": user["id"]})
    if doc["is_default"]:
        await db.addresses.update_many({"user_id": user["id"]}, {"$set": {"is_default": False}})
    await db.addresses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/addresses/{address_id}")
async def update_address(address_id: str, body: AddressIn, request: Request):
    user = await get_current_user(request)
    doc = body.model_dump()
    if doc["is_default"]:
        await db.addresses.update_many({"user_id": user["id"]}, {"$set": {"is_default": False}})
    await db.addresses.update_one({"id": address_id, "user_id": user["id"]}, {"$set": doc})
    return await db.addresses.find_one({"id": address_id}, {"_id": 0})


@router.delete("/addresses/{address_id}")
async def delete_address(address_id: str, request: Request):
    user = await get_current_user(request)
    await db.addresses.delete_one({"id": address_id, "user_id": user["id"]})
    return {"message": "Deleted"}


@router.post("/coupons/validate")
async def validate_coupon(body: CouponValidateIn):
    c = await db.coupons.find_one({"code": body.code.strip().upper(), "is_active": True}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Invalid coupon code")
    if c.get("expiry") and now_utc().isoformat() > c["expiry"]:
        raise HTTPException(400, "Coupon expired")
    if c.get("usage_limit") and c.get("used_count", 0) >= c["usage_limit"]:
        raise HTTPException(400, "Coupon usage limit reached")
    if body.subtotal < c.get("min_order", 0):
        raise HTTPException(400, f"Minimum order ₹{c.get('min_order', 0)} required")
    if c["type"] == "percent":
        disc = round(body.subtotal * c["value"] / 100, 2)
        if c.get("max_discount"):
            disc = min(disc, c["max_discount"])
    else:
        disc = min(c["value"], body.subtotal)
    return {"code": c["code"], "discount": round(disc, 2), "type": c["type"], "value": c["value"]}


@router.get("/coupons/available")
async def available_coupons():
    now = now_utc().isoformat()
    return await db.coupons.find(
        {"is_active": True, "$or": [{"expiry": None}, {"expiry": {"$gte": now}}]},
        {"_id": 0},
    ).to_list(20)


@router.get("/delivery/check")
async def check_delivery(pincode: str):
    s = await db.settings.find_one({"key": "store"}, {"_id": 0})
    delivery = (s or {}).get("value", {}).get("delivery", {})
    pincodes = delivery.get("pincodes", [])
    serviceable = not pincodes or pincode in pincodes
    return {
        "serviceable": serviceable,
        "pincode": pincode,
        "slots": delivery.get("slots", []) if serviceable else [],
        "estimated": delivery.get("estimated", "Within 2 hours") if serviceable else None,
    }


@router.post("/products/{product_id}/reviews")
async def add_review(product_id: str, body: ReviewIn, request: Request):
    user = await get_current_user(request)
    if not 1 <= body.rating <= 5:
        raise HTTPException(400, "Rating must be 1-5")
    doc = {
        "id": new_id(), "product_id": product_id, "user_id": user["id"],
        "user_name": user.get("name", "Customer"), "rating": body.rating,
        "comment": body.comment, "created_at": now_utc().isoformat(),
    }
    await db.reviews.insert_one(doc)
    agg = await db.reviews.aggregate([
        {"$match": {"product_id": product_id}},
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}},
    ]).to_list(1)
    if agg:
        await db.products.update_one(
            {"id": product_id},
            {"$set": {"rating": round(agg[0]["avg"], 1), "rating_count": agg[0]["n"]}},
        )
    doc.pop("_id", None)
    return doc
