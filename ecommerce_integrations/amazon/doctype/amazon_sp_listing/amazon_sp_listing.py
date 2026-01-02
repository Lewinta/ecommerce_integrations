# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe import _
import json
from six import string_types
from woocommerce_fusion.tasks.stock_update import get_item_projected_qty
from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import AmazonRepository

class AmazonSPListing(Document):

	field_mappings = {
        'id': 'sku'
    }
	
	amz_setting_name = "2n7sn0hlgc"
	seller_id = "AZ8IEI2WE6JHM"
	
	def db_insert(self, *args, **kwargs):
		pass

	def load_from_db(self):
		from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import get_listings_item
		response = get_listings_item(
			amz_setting_name=self.amz_setting_name,
			seller_id=self.seller_id,
			sku=self.name
		)
		super(Document, self).__init__(decode(response))
		

	def db_update(self, *args, **kwargs):
		pass
	
	@frappe.whitelist()
	def sync_with_erp(self, args=None):
		if name:= frappe.db.exists("Item", self.name):
			item = frappe.get_doc("Item", name)
			item.update({
				"item_code": self.name,
				"item_name": self.item_name[:140],
				"custom_sku": self.name,
				"image": self.image
			})
			
		else:
			item = frappe.new_doc("Item")
			item.update({
				"item_code": self.name,
				"item_name": self.item_name[:140],
				"custom_sku": self.item_name[:140],
				"image": self.image,
				"item_group": "All Item Groups",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"has_variants": 0
			})
		
		if self.amazon_sp_api_settings:
			row = {
				"fulfillment_channel": self.fulfillment_channel,
				"marketplace_id": self.marketplace_id,
				"seller_id": self.seller_id,
				"sku": self.sku,
				"asin": self.asin,
				"amazon_sp_api_settings": self.amazon_sp_api_settings,
			}
			# Now let's check if the row already exists
			existing_row = next(
				(row for row in item.custom_amazon_listings
				if row.amazon_sp_api_settings == self.amazon_sp_api_settings
				and row.seller_id == self.seller_id
				and row.sku == self.sku),
				None
			)
			if existing_row:
				# Update the existing row
				for key, value in row.items():
					existing_row.set(key, value)
				existing_row.save()
				return
			# If it doesn't exist, append a new row
			item.append('custom_amazon_listings', row)
		
		return item.save()

	@frappe.whitelist()
	def sync_inventory(self, args=None):
		"""
		Update stock quantity for an FBM (MFN) listing via the Amazon Listings Items API.
		"""
		az = AmazonRepository(self.amz_setting_name)
		return az.update_fbm_stock(self.seller_id, self.sku, self.product_type, self.available_qty)
		
	@staticmethod
	def get_list(args):
		from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import search_listings

		try:
			if hasattr(frappe.local, "amazon_sp_listings_cache"):
				cached = frappe.local.amazon_sp_listings_cache
				items = cached.get("items", [])
				total_count = cached.get("total_count", len(items))
				return [decode(item) for item in items]

			start = int(args.get("start", 0))
			page_length = int(args.get("page_length", 20))
			current_page = start // page_length
			items_offset = start % page_length

			all_items = []
			next_token = None
			seen_tokens = set()
			tokens = {}

			# Walk through pages to get to the correct offset
			for page in range(current_page + 1):
				result = search_listings(
					seller_id=AmazonSPListing.seller_id,
					amz_setting_name=AmazonSPListing.amz_setting_name,
					page_size=page_length,
					next_token=next_token
				)

				items = result.get("items", [])
				all_items.extend(items)

				next_token = result.get("pagination", {}).get("nextToken")
				if not next_token or next_token in seen_tokens:
					break

				seen_tokens.add(next_token)
				tokens[str(page + 1)] = next_token

			# Cache entire batch for reuse in get_count()
			frappe.local.amazon_sp_listings_cache = {
				"items": all_items[items_offset:items_offset + page_length],
				"total_count": result.get("numberOfResults", len(all_items))
			}

			return [decode(item) for item in frappe.local.amazon_sp_listings_cache["items"]]

		except Exception as e:
			frappe.log_error(
				title="Amazon SP Listing Get List Error",
				message=f"Error: {str(e)}\nTraceback: {frappe.get_traceback()}"
			)
			return []

	@staticmethod
	def get_count(args):
		if hasattr(frappe.local, "amazon_sp_listings_cache"):
			return frappe.local.amazon_sp_listings_cache.get("total_count", 0)
		else:
			# fallback — shouldn't happen under normal listview calls
			return len(AmazonSPListing.get_list(args))

	@staticmethod
	def get_stats(args):
		pass
	
def decode(item):
	
	summaries, availability = extract_data(item)

	if not summaries:
		frappe.throw(f"Invalid item data: {item.get('sku')}")
	
	fulfillment_channel = "FBM" if availability and availability.get("fulfillmentChannelCode") == "DEFAULT" else "FBA"
	if not item.get("amazon_sp_api_settings"):
		return frappe._dict({})
	settings = frappe.get_doc("Amazon SP API Settings", item.get("amazon_sp_api_settings"))
	available_qty = get_item_projected_qty(item.get("sku"),settings.company)

	return frappe._dict({
		"name": item.get("sku"),
		"amazon_sp_api_settings": item.get("amazon_sp_api_settings"),
		"seller_id": item.get("seller_id"),
		"asin": summaries.get("asin"),
		"sku": item.get("sku"),
		"fn_sku": summaries.get("fnSku"),
		"fulfillment_channel": fulfillment_channel,
		"item_name": summaries.get("itemName"),
		"image": summaries.get('mainImage').get("link"),
		"product_type": summaries.get("productType"),
		"marketplace_id": summaries.get("marketplaceId"),
		"available_qty": available_qty if available_qty > 0 else 0,
		"listed_qty": get_listed_qty(item),
		"summaries": frappe.as_json(item),
		"creation": summaries.get('createdDate').replace("T", " ").replace("Z", ""),
		"modified": summaries.get('lastUpdatedDate').replace("T", " ").replace("Z", ""),
	})

def get_listed_qty(item):
	listed_qty = 0
	for row in item.get("fulfillmentAvailability", []):
		if row.get("fulfillmentChannelCode") == "DEFAULT":
			listed_qty = row.get("quantity", 0)
			break
	return listed_qty

def extract_data(item):
	summaries = None
	availbility = None
	if isinstance(item, string_types):
		item = json.loads(item)
	
	if item.get("summaries"):
		summaries = item.get("summaries")[0]
	
	if item.get("fulfillmentAvailability"):
		availbility = item.get("fulfillmentAvailability")[0]
	
	return summaries, availbility



def sync_item_stock_to_amazon(item_code):
	"""
	Synchronize stock quantity of an item to Amazon.
	"""
	if not frappe.db.exists('Item Amazon SP Listing', {"parent": item_code}):
		return
	
	listing = frappe.get_doc("Amazon SP Listing", item_code)
	if listing.fulfillment_channel == "FBA":
		frappe.msgprint(
			_("FBA listings are not supported for stock synchronization. ")
		)
		return
	listing.sync_inventory()

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def amazon_sp_listings_ct_query(doctype, txt, searchfield, start, page_len, filters):
    from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import search_listings

    all_items = search_listings(
        amz_setting_name="2n7sn0hlgc",
        seller_id="AZ8IEI2WE6JHM",
        sku_list=[txt] if txt else None
    )

    # Convert to the correct format: list of [value, description] pairs
    results = [
        [
            item.get("sku"),  # Value that will be stored
            f"{item.get('sku', '')}"  # Description shown in UI
        ]
        for item in all_items.get("items", [])
    ]

    return results