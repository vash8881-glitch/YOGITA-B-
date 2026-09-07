import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

INVOICE_DIR = Path(__file__).parent / "invoices"
INVOICE_DIR.mkdir(exist_ok=True)


def generate_invoice_pdf(order: dict, settings: dict, invoice_no: str) -> str:
    path = INVOICE_DIR / f"{invoice_no}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    x = 20 * mm
    y = h - 20 * mm

    c.setFillColor(colors.HexColor("#15803D"))
    c.rect(0, h - 30 * mm, w, 30 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(x, h - 16 * mm, settings.get("store_name", "SabziMandi Fresh"))
    c.setFont("Helvetica", 9)
    c.drawString(x, h - 22 * mm, settings.get("address", ""))
    c.drawString(x, h - 26 * mm, f"GSTIN: {settings.get('gst_number', '-')}   Phone: {settings.get('phone', '-')}")

    c.setFillColor(colors.black)
    y = h - 42 * mm
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x, y, "TAX INVOICE")
    c.setFont("Helvetica", 10)
    y -= 8 * mm
    c.drawString(x, y, f"Invoice No: {invoice_no}")
    c.drawRightString(w - x, y, f"Order ID: {order['id']}")
    y -= 6 * mm
    c.drawString(x, y, f"Date: {order['created_at'][:10]}")
    c.drawRightString(w - x, y, f"Payment: {order['payment_method'].upper()}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Bill To:")
    c.setFont("Helvetica", 10)
    y -= 5 * mm
    addr = order["address"]
    c.drawString(x, y, f"{addr['name']}  ({addr['mobile']})")
    y -= 5 * mm
    c.drawString(x, y, f"{addr['line1']} {addr.get('line2', '')}".strip())
    y -= 5 * mm
    c.drawString(x, y, f"{addr['city']}, {addr['state']} - {addr['pincode']}")
    y -= 10 * mm

    c.setFillColor(colors.HexColor("#DCFCE7"))
    c.rect(x, y - 2 * mm, w - 2 * x, 7 * mm, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 2 * mm, y, "Item")
    c.drawRightString(w - x - 60 * mm, y, "Qty")
    c.drawRightString(w - x - 40 * mm, y, "Rate")
    c.drawRightString(w - x - 20 * mm, y, "Amount")
    y -= 8 * mm
    c.setFont("Helvetica", 9)

    for it in order["items"]:
        if y < 60 * mm:
            c.showPage()
            y = h - 20 * mm
            c.setFont("Helvetica", 9)
        name = it["name"]["en"] if isinstance(it["name"], dict) else str(it["name"])
        c.drawString(x + 2 * mm, y, f"{name} ({it['unit']})"[:60])
        c.drawRightString(w - x - 60 * mm, y, str(it["qty"]))
        c.drawRightString(w - x - 40 * mm, y, f"Rs {it['price']:.2f}")
        c.drawRightString(w - x - 20 * mm, y, f"Rs {it['price'] * it['qty']:.2f}")
        y -= 6 * mm

    y -= 4 * mm
    c.line(x, y, w - x, y)
    y -= 7 * mm

    def row(label, value, bold=False):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(x, y, label)
        c.drawRightString(w - x, y, value)
        y -= 6 * mm

    row("Subtotal", f"Rs {order['subtotal']:.2f}")
    if order.get("product_discount"):
        row("Product Discount (MRP)", f"- Rs {order['product_discount']:.2f}")
    if order.get("coupon_discount"):
        row(f"Coupon ({order.get('coupon_code')})", f"- Rs {order['coupon_discount']:.2f}")
    row("Delivery Charge", f"Rs {order['delivery_fee']:.2f}")
    row("GST", f"Rs {order['gst']:.2f}")
    if order.get("loyalty_discount"):
        row("Loyalty Discount", f"- Rs {order['loyalty_discount']:.2f}")
    if order.get("wallet_used"):
        row("Wallet Credit Used", f"- Rs {order['wallet_used']:.2f}")
    c.line(x, y + 2 * mm, w - x, y + 2 * mm)
    row("Grand Total", f"Rs {order['grand_total']:.2f}", bold=True)

    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.HexColor("#15803D"))
    c.drawString(x, 20 * mm, "Thank you for shopping fresh with us!")
    c.save()
    return str(path)
