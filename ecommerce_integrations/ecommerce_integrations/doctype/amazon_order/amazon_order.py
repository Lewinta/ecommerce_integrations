# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import json
import frappe
import dateutil
from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import AmazonRepository
from frappe.utils import today, add_days, cint, flt, now
from frappe.model.document import Document

class AmazonOrder(Document):
	amz_setting_name = "2n7sn0hlgc"
	
	def db_insert(self, *args, **kwargs):
		pass

	def load_from_db(self):

		repo = AmazonRepository(self.amz_setting_name)
		order = repo.get_order_by_id(self.name)
		items = repo.get_order_items_raw(self.name)

		# Inject OrderItems into the order payload
		order["OrderItems"] = items

		# Re-initialize self with decoded field values
		super(Document, self).__init__(decode(order))

	@frappe.whitelist()
	def sync_order_with_erp(self):
		az = AmazonRepository(self.amz_setting_name)
		payload = json.loads(self.payload)
		return az.sync_order_with_erp(payload)

	def db_update(self, *args, **kwargs):
		pass

	@staticmethod
	def get_list(args):
		start = cint(args.get("start", 0))
		limit = cint(args.get("page_length", 20))
		amz_setting_name = AmazonOrder.amz_setting_name

		# Check cache
		if hasattr(frappe.local, "amazon_sp_orders_cache"):
			cache = frappe.local.amazon_sp_orders_cache
			orders = cache.get("orders", [])[start:start + limit]
			return [decode(order) for order in orders]

		# Fetch fresh data
		repo = AmazonRepository(amz_setting_name)
		all_orders = repo.fetch_orders_list(
			created_after=add_days(today(), -30),
			start=0,
			limit=1000  # Fetch a large batch once
		)

		# Store in cache
		frappe.local.amazon_sp_orders_cache = {
			"orders": all_orders,
			"total_count": len(all_orders)
		}

		return [decode(order) for order in all_orders[start:start + limit]]


	@staticmethod
	def get_count(args):
		if hasattr(frappe.local, "amazon_sp_orders_cache"):
			return frappe.local.amazon_sp_orders_cache.get("total_count", 0)
		else:
			# Fallback if get_list wasn't called before
			return len(AmazonOrder.get_list(args))

		@staticmethod
		def get_stats(args):
			pass

def decode(order: dict) -> dict:
	creation = dateutil.parser.parse(order.get("PurchaseDate")).strftime("%Y-%m-%d %H:%M:%S") if order.get("PurchaseDate") else now()
	order_data = frappe._dict({
		"name": order.get("AmazonOrderId"),
		"order_id": order.get("AmazonOrderId"),
		"order_type": order.get("OrderType"),
		"email": order.get("BuyerInfo", {}).get("BuyerEmail"),
		"sales_channel": order.get("SalesChannel"),
		"status": order.get("OrderStatus"),
		"purchase_date": order.get("PurchaseDate", "").split("T")[0],
		"fulfillment_channel": order.get("FulfillmentChannel"),
		"marketplace_id": order.get("MarketplaceId"),
		"items_shipped": order.get("NumberOfItemsShipped"),
		"premium_order": int(order.get("IsPremiumOrder", False)),
		"prime": int(order.get("IsPrime", False)),
		"earliest_ship_date": order.get("EarliestShipDate", "").split("T")[0] if order.get("EarliestShipDate") else None,
		"latest_ship_date": order.get("LatestShipDate", "").split("T")[0] if order.get("LatestShipDate") else None,
		"ship_service_level": order.get("ShipServiceLevel"),
		"order_total": order.get("OrderTotal", {}).get("Amount", 0),
		"city": order.get("ShippingAddress", {}).get("City"),
		"state": order.get("ShippingAddress", {}).get("StateOrRegion"),
		"pincode": order.get("ShippingAddress", {}).get("PostalCode"),
		"country": order.get("ShippingAddress", {}).get("CountryCode"),
		"payload": frappe.as_json(order),
		"creation": creation,
		"modified": creation,
	})

	items = []
	# Decode OrderItems
	for item in order.get("OrderItems", []):
		items.append(decode_order_item(item))

	order_data["items"] = items

	return order_data

def decode_order_item(item: dict) -> dict:
	"""Decode raw Amazon order item payload into Frappe-compatible dict for Amazon Order Item"""
	return frappe._dict({
		"asin": item.get("ASIN"),
		"sku": item.get("SellerSKU"),
		"title": item.get("Title"),
		"order_item_id": item.get("OrderItemId"),
		"currency": item.get("ItemPrice", {}).get("CurrencyCode"),
		"main_cb": item.get("TaxCollection", {}).get("Model"),
		"rate": flt(item.get("ItemPrice", {}).get("Amount", 0)),
		"qty": flt(item.get("QuantityOrdered", 0)),
		"discount": flt(item.get("PromotionDiscount", {}).get("Amount", 0)),
		"amount": flt(item.get("ItemPrice", {}).get("Amount", 0)),  
		"tax": flt(item.get("ItemTax", {}).get("Amount", 0))
	})
