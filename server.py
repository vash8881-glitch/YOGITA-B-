import asyncio
import logging
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from auth_utils import new_id, now_utc  # noqa: E402
from db import client, db  # noqa: E402
from routes_admin import router as admin_router  # noqa: E402
from routes_auth import router as auth_router  # noqa: E402
from routes_orders import router as orders_router  # noqa: E402
from routes_payments import router as payments_router  # noqa: E402
from routes_store import router as store_router  # noqa: E402
from seed import create_indexes, seed  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="SabziMandi Fresh API")

app.include_router(auth_router)
app.include_router(store_router)
app.include_router(orders_router)
app.include_router(payments_router)
app.include_router(admin_router)

UPLOADS = ROOT_DIR / "static" / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api")
async def root():
    return {"message": "SabziMandi Fresh API"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def background_jobs():
    while True:
        try:
            now = now_utc().isoformat()
            await db.offers.update_many({"end_at": {"$lt": now}, "is_active": True}, {"$set": {"is_active": False}})
            due = await db.subscriptions.find({"status": "active", "next_delivery_at": {"$lte": now}}).to_list(20)
            for sub in due:
                plan_days = {"daily": 1, "weekly": 7, "monthly": 30}.get(sub["plan"], 1)
                try:
                    settings = ((await db.settings.find_one({"key": "store"})) or {}).get("value", {})
                    gst_percent = settings.get("gst_percent", 5)
                    for i in sub["items"]:
                        p = await db.products.find_one({"id": i["product_id"], "is_active": True})
                        if not p or p.get("stock", 0) < i["qty"]:
                            raise ValueError(f"{i['product_id']} out of stock")
                    order_id = "ORD-" + new_id()[:8].upper()
                    subtotal = round(sum(i["price"] * i["qty"] for i in sub["items"]), 2)
                    gst = round(subtotal * gst_percent / 100, 2)
                    order = {
                        "id": order_id, "user_id": sub["user_id"], "customer": sub["customer"],
                        "items": sub["items"], "address": sub["address"], "delivery_slot": sub.get("delivery_slot", ""),
                        "payment_method": sub.get("payment_method", "cod"), "payment_status": "cod",
                        "subtotal": subtotal, "mrp_total": subtotal, "product_discount": 0, "coupon_code": None,
                        "coupon_discount": 0, "delivery_fee": 0, "gst": gst,
                        "loyalty_discount": 0, "wallet_used": 0, "grand_total": round(subtotal + gst, 2),
                        "loyalty_earned": 0, "status": "confirmed", "subscription_id": sub["id"],
                        "status_history": [{"status": "confirmed", "at": now}],
                        "created_at": now,
                    }
                    from invoice import generate_invoice_pdf
                    invoice_no = "INV-" + new_id()[:8].upper()
                    order["invoice"] = {"invoice_no": invoice_no, "path": generate_invoice_pdf(order, settings, invoice_no), "generated_at": now}
                    await db.orders.insert_one(order)
                    for i in sub["items"]:
                        await db.products.update_one({"id": i["product_id"]}, {"$inc": {"stock": -i["qty"], "popularity": i["qty"]}})
                    await db.subscriptions.update_one(
                        {"id": sub["id"]},
                        {"$set": {"next_delivery_at": (now_utc() + timedelta(days=plan_days)).isoformat()}},
                    )
                    logger.info(f"Subscription order {order_id} created for {sub['id']}")
                except Exception as e:
                    logger.error(f"Subscription {sub['id']} failed: {e}")
        except Exception as e:
            logger.error(f"Background job error: {e}")
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup():
    await create_indexes()
    await seed()
    asyncio.create_task(background_jobs())
    logger.info("SabziMandi Fresh API started")


@app.on_event("shutdown")
async def shutdown():
    client.close()
