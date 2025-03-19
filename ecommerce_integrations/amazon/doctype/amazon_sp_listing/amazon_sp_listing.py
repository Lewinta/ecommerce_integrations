# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
import json
class AmazonSPListing(Document):

	field_mappings = {
        'id': 'sku'
    }
	
	amz_setting_name = "21qv23optp"
	
	def db_insert(self, *args, **kwargs):
		pass

	def load_from_db(self):
		from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import get_listings_item

		sku = self.name
		response = get_listings_item(amz_setting_name=self.amz_setting_name, seller_id="AZ8IEI2WE6JHM", sku=sku)
		
		dict_response = frappe._dict(
			name=response["sku"],
			sku=response["sku"],
			summaries=frappe.as_json(response["summaries"])
		)

		super(Document, self).__init__(dict_response)
		

	def db_update(self, *args, **kwargs):
		pass

	@staticmethod
	def get_list(args):
		"""Get Amazon listings with pagination support for Frappe's list view"""
		from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import search_listings
		
		# Parse Frappe pagination parameters
		page_length = int(args.get("page_length", 20))
		start = int(args.get("start", 0))
		
		# Parse sorting parameters
		sort_field = "modified"
		sort_order = "DESC"
		if args.get("order_by"):
			order_parts = args["order_by"].replace("`", "").split(".")[-1].split()
			if len(order_parts) >= 1:
				sort_field = order_parts[0]
			if len(order_parts) >= 2:
				sort_order = order_parts[1].upper()

		sort_field_mapping = {
			"modified": "LastUpdateDate",
			"creation": "CreatedDate",
			"name": "SKU",
			"idx": "SKU"
		}

		# Cache key for storing pagination tokens
		cache_key = f"amazon_sp_listing_tokens_{frappe.session.user}"
		
		def get_cached_tokens():
			return frappe.cache().get_value(cache_key) or {}

		def set_cached_tokens(tokens):
			frappe.cache().set_value(cache_key, tokens, expires_in_sec=3600)  # 1 hour expiry
			
		#TODO: Pagination is not working properly, it's not fetching the next page rather its replacing the current page.
		def fetch_page(next_token=None):
			"""Fetch a single page from Amazon SP-API"""
			return search_listings(
				seller_id="AZ8IEI2WE6JHM",
				amz_setting_name="21qv23optp",
				sort_by=sort_field_mapping.get(sort_field, "LastUpdateDate"),
				sort_order=sort_order,
				page_size=20,  # Amazon's max page size
				next_token=next_token
			)

		try:
			all_items = []
			tokens = get_cached_tokens()
			current_page = start // 20  # Calculate which Amazon page we need
			
			# If we have cached tokens, use them to get to the right page faster
			if str(current_page) in tokens and current_page > 0:
				next_token = tokens[str(current_page)]
			else:
				# We need to build up to the required page
				next_token = None
				for page in range(current_page):
					result = fetch_page(next_token)
					next_token = result.get("pagination", {}).get("nextToken")
					if not next_token:
						break
					tokens[str(page + 1)] = next_token
				set_cached_tokens(tokens)

			# Now fetch pages until we have enough items
			items_needed = page_length
			items_offset = start % 20  # Offset within the first page we need
			
			while len(all_items) < items_needed:
				result = fetch_page(next_token)
				items = result.get("items", [])
				pagination = result.get("pagination", {})
				
				# Store the token for future use
				if pagination.get("nextToken"):
					current_page += 1
					tokens[str(current_page)] = pagination["nextToken"]
					set_cached_tokens(tokens)

				# Add items considering the offset
				if items_offset > 0:
					items = items[items_offset:]
					items_offset = 0

				all_items.extend(items)
				
				next_token = pagination.get("nextToken")
				if not next_token:
					break

			# Prepare the response
			response = [
				{
					"name": item.get("sku"),
					"sku": item.get("sku"),
					"summaries": item.get("summaries")
				}
				for item in all_items[:page_length]
			]
			return response
		except Exception as e:
			frappe.log_error(
				message=f"Amazon Listings Error: {str(e)}\nArgs: {args}",
				title="Amazon SP Listing Get List Error")
			return {"data": [], "total_count": 0}

	@staticmethod
	def get_count(args):
		pass

	@staticmethod
	def get_stats(args):
		pass
	
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def amazon_sp_listings_ct_query(doctype, txt, searchfield, start, page_len, filters):
    from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import search_listings

    all_items = search_listings(
        seller_id="AZ8IEI2WE6JHM",
        amz_setting_name="21qv23optp",
        sku_list=txt
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