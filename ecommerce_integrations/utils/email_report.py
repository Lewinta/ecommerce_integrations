import json
import frappe
from frappe.utils import get_datetime, convert_utc_to_user_timezone, format_datetime, now

def _fulfillment_label(fulfillment_channel: str) -> str:
    # Amazon returns AFN (FBA) or MFN (FBM)
    if fulfillment_channel == "AFN":
        return "FBA"
    if fulfillment_channel == "MFN":
        return "FBM"
    return fulfillment_channel or "Unknown"

def _ship_to_str(addr: dict) -> str:
    if not addr:
        return ""
    parts = [
        addr.get("City"),
        addr.get("StateOrRegion"),
        addr.get("PostalCode"),
        addr.get("CountryCode"),
    ]
    return ", ".join([p for p in parts if p])

def notify_users(order, e, traceback, az):
    """Send email notification to users about error creating Sales Invoice for Amazon order.

    Args:
        order (dict): Amazon order data (as returned by SP-API).
        e (Exception): Exception that occurred.
        traceback (str): Traceback string.
    """
    # For testing:
    # 1. Set your email in Amazon SP API Settings > Notify To
    # 2. Run this script via bench console
    # 3. Check your email

    order_id = order.get("AmazonOrderId") or order.get("SellerOrderId")
    subject = f"Error creating Sales Invoice · Amazon Order {order_id}"

    # dates: Amazon uses UTC ISO8601; render in user's timezone
    purchase_dt = None
    if order.get("PurchaseDate"):
        try:
            purchase_dt = convert_utc_to_user_timezone(get_datetime(order.get("PurchaseDate")))
        except Exception:
            purchase_dt = get_datetime(order.get("PurchaseDate"))

    context = {
        "subject": subject,
        "channel": order.get("SalesChannel") or "Amazon",
        "fulfillment": _fulfillment_label(order.get("FulfillmentChannel")),
        "order": order,
        "order_id": order_id,
        "marketplace": order.get("MarketplaceId"),
        "buyer_email": (order.get("BuyerInfo") or {}).get("BuyerEmail"),
        "purchase_date_local": format_datetime(purchase_dt) if purchase_dt else "—",
        "ship_level": order.get("ShipServiceLevel") or order.get("ShipmentServiceLevelCategory"),
        "ship_to": _ship_to_str(order.get("ShippingAddress")),
        "error_message": str(e),
        "traceback": traceback,
        "payload_pretty": json.dumps(order, indent=2, ensure_ascii=False, default=str),
        "now_str": format_datetime(now()),
    }

    # Render Jinja template
    html = frappe.render_template("templates/email/order_import_error.html", context)

    if getattr(az.amz_setting, "notify_to", None):
        users = [u.strip() for u in az.amz_setting.notify_to.split("\n") if u.strip()]
        if users:
            frappe.sendmail(
                recipients=users,
                subject=subject,
                message=html,  
            )
