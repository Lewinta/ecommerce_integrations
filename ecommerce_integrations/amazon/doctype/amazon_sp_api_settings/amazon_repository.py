# Copyright (c) 2022, Frappe and contributors
# For license information, please see license.txt


import time
import urllib
from frappe.utils import add_days, today
import dateutil
import frappe
from frappe import _
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_sp_api import (
	SPAPI,
	CatalogItems,
	Finances,
	Orders,
	Listings,
	SPAPIError,
)
from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_sp_api_settings import (
	AmazonSPAPISettings,
)


class AmazonRepository:
	def __init__(self, amz_setting: str | AmazonSPAPISettings) -> None:
		if isinstance(amz_setting, str):
			amz_setting = frappe.get_doc("Amazon SP API Settings", amz_setting)

		self.amz_setting = amz_setting
		self.instance_params = dict(
			iam_arn=self.amz_setting.iam_arn,
			client_id=self.amz_setting.client_id,
			client_secret=self.amz_setting.get_password("client_secret"),
			refresh_token=self.amz_setting.refresh_token,
			aws_access_key=self.amz_setting.aws_access_key,
			aws_secret_key=self.amz_setting.get_password("aws_secret_key"),
			country_code=self.amz_setting.country,
		)

	def return_as_list(self, input) -> list:
		if isinstance(input, list):
			return input
		else:
			return [input]

	def call_sp_api_method(self, sp_api_method, **kwargs) -> dict:
		errors = {}
		max_retries = self.amz_setting.max_retry_limit

		for x in range(max_retries):
			try:
				result = sp_api_method(**kwargs)
				return result.get("payload")
			except SPAPIError as e:
				if e.error not in errors:
					errors[e.error] = e.error_description

				time.sleep(1)
				continue

		for error in errors:
			msg = f"<b>Error:</b> {error}<br/><b>Error Description:</b> {errors.get(error)}"
			frappe.log_error(
				message=f"{error}: {errors.get(error)}", title=f'Method "{sp_api_method.__name__}" failed',
			)

		self.amz_setting.enable_sync = 0
		self.amz_setting.save()

		frappe.throw(
			_("Scheduled sync has been temporarily disabled because maximum retries have been exceeded!")
		)

	def get_finances_instance(self) -> Finances:
		return Finances(**self.instance_params)

	def get_account(self, name) -> str:
		account_name = frappe.db.get_value("Account", {"account_name": "Amazon {0}".format(name)})

		if not account_name:
			new_account = frappe.new_doc("Account")
			new_account.account_name = "Amazon {0}".format(name)
			new_account.company = self.amz_setting.company
			new_account.parent_account = self.amz_setting.market_place_account_group
			new_account.insert(ignore_permissions=True)
			account_name = new_account.name

		return account_name

	def get_charges_and_fees(self, order_id) -> dict:
		finances = self.get_finances_instance()
		financial_events_payload = self.call_sp_api_method(
			sp_api_method=finances.list_financial_events_by_order_id, order_id=order_id
		)

		charges_and_fees = {"charges": [], "fees": []}

		while True:
			shipment_event_list = financial_events_payload.get("FinancialEvents", {}).get(
				"ShipmentEventList", []
			)
			next_token = financial_events_payload.get("NextToken")

			for shipment_event in shipment_event_list:
				if shipment_event:
					for shipment_item in shipment_event.get("ShipmentItemList", []):
						charges = shipment_item.get("ItemChargeList", [])
						fees = shipment_item.get("ItemFeeList", [])
						seller_sku = shipment_item.get("SellerSKU")

						for charge in charges:
							charge_type = charge.get("ChargeType")
							amount = charge.get("ChargeAmount", {}).get("CurrencyAmount", 0)

							if charge_type != "Principal" and float(amount) != 0:
								charge_account = self.get_account(charge_type)
								charges_and_fees.get("charges").append(
									{
										"charge_type": "Actual",
										"account_head": charge_account,
										"tax_amount": amount,
										"description": charge_type + " for " + seller_sku,
									}
								)

						for fee in fees:
							fee_type = fee.get("FeeType")
							amount = fee.get("FeeAmount", {}).get("CurrencyAmount", 0)

							if float(amount) != 0:
								fee_account = self.get_account(fee_type)
								charges_and_fees.get("fees").append(
									{
										"charge_type": "Actual",
										"account_head": fee_account,
										"tax_amount": amount,
										"description": fee_type + " for " + seller_sku,
									}
								)

			if not next_token:
				break

			financial_events_payload = self.call_sp_api_method(
				sp_api_method=finances.list_financial_events_by_order_id,
				order_id=order_id,
				next_token=next_token,
			)

		return charges_and_fees

	def get_orders_instance(self) -> Orders:
		return Orders(**self.instance_params)

	def create_item(self, order_item) -> str:
		# {
			# "ASIN": "B0CRPF819T",
			# "BuyerInfo": {},
			# "IsGift": "false",
			# "IsTransparency": false,
			# "ItemPrice": {
				# "Amount": "38.99",
				# "CurrencyCode": "USD"
			# },
			# "ItemTax": {
				# "Amount": "2.73",
				# "CurrencyCode": "USD"
			# },
			# "OrderItemId": "129478518919921",
			# "ProductInfo": {
				# "NumberOfItems": "1"
			# },
			# "PromotionDiscount": {
				# "Amount": "0.00",
				# "CurrencyCode": "USD"
			# },
			# "PromotionDiscountTax": {
				# "Amount": "0.00",
				# "CurrencyCode": "USD"
			# },
			# "QuantityOrdered": 1,
			# "QuantityShipped": 1,
			# "SellerSKU": "6109M",
			# "TaxCollection": {
				# "Model": "MarketplaceFacilitator",
				# "ResponsibleParty": "Amazon Services, Inc."
			# },
			# "Title": "WARNE RED-DOT Low PRO Reflex Mount"
		# }
		listing = frappe.get_doc("Amazon SP Listing", order_item.get("SellerSKU"))
		listing.sync_with_erp(self.amz_setting)
		

	def get_item_code(self, order_item) -> str:
		for field_map in self.amz_setting.amazon_fields_map:
			if field_map.use_to_find_item_code:
				item_code = frappe.db.get_value(
					"Item",
					filters={field_map.item_field: order_item[field_map.amazon_field]},
					fieldname="item_code",
				)

				if item_code:
					return item_code
				elif not self.amz_setting.create_item_if_not_exists:
					field_label = frappe.get_meta("Item").get_label(field_map.item_field)
					frappe.throw(
						_("Item not found with {0} ({1}) = {2}.").format(
							frappe.bold(field_label),
							field_map.item_field,
							frappe.bold(order_item[field_map.amazon_field]),
						)
					)

				break
		else:
			frappe.throw(_("At least one field must be selected to find the item code."))

		# print(f"Creating item for {order_item['SellerSKU']}")
		# print(f"Order Item: {order_item}")
		# print(f"Now let's create item for {order_item}")
		item_code = self.create_item(order_item)
		return item_code

	def get_order_items(self, order_id) -> list:
		orders = self.get_orders_instance()
		order_items_payload = self.call_sp_api_method(
			sp_api_method=orders.get_order_items, order_id=order_id
		)

		final_order_items = []
		warehouse = self.amz_setting.warehouse

		while True:
			order_items_list = order_items_payload.get("OrderItems")
			next_token = order_items_payload.get("NextToken")

			for order_item in order_items_list:

				if order_item.get("QuantityOrdered") > 0:
					# print(f"Order Item before append: {order_item}")
					item_code = self.get_item_code(order_item)
					
					if not item_code:
						listing = frappe.get_doc("Amazon SP Listing", order_item.get("SellerSKU"))
						listing.sync_with_erp(self.amz_setting)
						item_code = order_item.get("SellerSKU")
					
					final_order_items.append(
						{
							"item_code": item_code,
							"item_name": order_item.get("SellerSKU"),
							"description": order_item.get("Title"),
							"rate": order_item.get("ItemPrice", {}).get("Amount", 0),
							"qty": order_item.get("QuantityOrdered"),
							"stock_uom": "Nos",
							"warehouse": warehouse,
							"conversion_factor": 1.0,
						}
					)

			if not next_token:
				break

			order_items_payload = self.call_sp_api_method(
				sp_api_method=orders.get_order_items, order_id=order_id, next_token=next_token,
			)

		return final_order_items

	def create_sales_order(self, order) -> str | None:
		def create_customer(order) -> str:
			order_customer_name = ""
			buyer_info = order.get("BuyerInfo")

			if buyer_info and buyer_info.get("BuyerEmail"):
				order_customer_name = buyer_info.get("BuyerEmail")
			else:
				order_customer_name = f"Buyer - {order.get('AmazonOrderId')}"

			existing_customer_name = frappe.db.get_value(
				"Customer", filters={"name": order_customer_name}, fieldname="name"
			)

			if existing_customer_name:
				filters = [
					["Dynamic Link", "link_doctype", "=", "Customer"],
					["Dynamic Link", "link_name", "=", existing_customer_name],
					["Dynamic Link", "parenttype", "=", "Contact"],
				]

				existing_contacts = frappe.get_list("Contact", filters)

				if not existing_contacts:
					new_contact = frappe.new_doc("Contact")
					new_contact.first_name = order_customer_name
					new_contact.append(
						"links", {"link_doctype": "Customer", "link_name": existing_customer_name},
					)
					new_contact.insert()

				return existing_customer_name
			else:
				new_customer = frappe.new_doc("Customer")
				new_customer.customer_name = order_customer_name
				new_customer.customer_group = self.amz_setting.customer_group
				new_customer.territory = self.amz_setting.territory
				new_customer.customer_type = self.amz_setting.customer_type
				new_customer.save()

				new_contact = frappe.new_doc("Contact")
				new_contact.first_name = order_customer_name
				new_contact.append("links", {"link_doctype": "Customer", "link_name": new_customer.name})

				new_contact.insert()

				return new_customer.name

		def create_address(order, customer_name) -> str | None:
			shipping_address = order.get("ShippingAddress")

			if not shipping_address:
				return
			else:
				make_address = frappe.new_doc("Address")
				make_address.address_line1 = shipping_address.get("AddressLine1", "Not Provided")
				make_address.city = shipping_address.get("City", "Not Provided")
				make_address.state = shipping_address.get("StateOrRegion").title()
				make_address.pincode = shipping_address.get("PostalCode")

				filters = [
					["Dynamic Link", "link_doctype", "=", "Customer"],
					["Dynamic Link", "link_name", "=", customer_name],
					["Dynamic Link", "parenttype", "=", "Address"],
				]
				existing_address = frappe.get_list("Address", filters)

				for address in existing_address:
					address_doc = frappe.get_doc("Address", address["name"])
					if (
						address_doc.address_line1 == make_address.address_line1
						and address_doc.pincode == make_address.pincode
					):
						return address

				make_address.append("links", {"link_doctype": "Customer", "link_name": customer_name})
				make_address.address_type = "Shipping"
				make_address.insert()

		order_id = order.get("AmazonOrderId")
		so = frappe.db.get_value("Sales Order", filters={"amazon_order_id": order_id}, fieldname="name")

		if so:
			return so
		else:
			# print(f"Getting order items for {order_id}")
			items = self.get_order_items(order_id)

			if not items:
				return

			customer_name = create_customer(order)
			create_address(order, customer_name)

			delivery_date = dateutil.parser.parse(order.get("LatestShipDate")).strftime("%Y-%m-%d")
			transaction_date = dateutil.parser.parse(order.get("PurchaseDate")).strftime("%Y-%m-%d")

			so = frappe.new_doc("Sales Order")
			so.amazon_order_id = order_id
			so.po_no = order_id
			so.marketplace_id = order.get("MarketplaceId")
			so.customer = customer_name
			so.delivery_date = delivery_date
			so.transaction_date = transaction_date
			so.company = self.amz_setting.company
			so.fulfillment_method = order.get("FulfillmentChannel") 

			for item in items:
				so.append("items", item)

			taxes_and_charges = self.amz_setting.taxes_charges

			if taxes_and_charges:
				charges_and_fees = self.get_charges_and_fees(order_id)

				for charge in charges_and_fees.get("charges"):
					so.append("taxes", charge)

				for fee in charges_and_fees.get("fees"):
					so.append("taxes", fee)
			try:
				so.insert(ignore_permissions=True)
				so.submit()
			except Exception as e:
				frappe.log_error(
					title=f"Sales Order Creation Error for Order ID: {order_id}",
					message=f"Error creating sales order: {e}",
				)
				

			return so.name

	def create_sales_invoice(self, order) -> str | None:
		def create_customer(order) -> str:
			order_customer_name = ""
			buyer_info = order.get("BuyerInfo")

			if buyer_info and buyer_info.get("BuyerEmail"):
				order_customer_name = buyer_info.get("BuyerEmail")
			else:
				order_customer_name = f"Buyer - {order.get('AmazonOrderId')}"

			existing_customer_name = frappe.db.get_value(
				"Customer", filters={"name": order_customer_name}, fieldname="name"
			)

			if existing_customer_name:
				filters = [
					["Dynamic Link", "link_doctype", "=", "Customer"],
					["Dynamic Link", "link_name", "=", existing_customer_name],
					["Dynamic Link", "parenttype", "=", "Contact"],
				]

				existing_contacts = frappe.get_list("Contact", filters)

				if not existing_contacts:
					new_contact = frappe.new_doc("Contact")
					new_contact.first_name = order_customer_name
					new_contact.append(
						"links", {"link_doctype": "Customer", "link_name": existing_customer_name},
					)
					new_contact.insert()

				return existing_customer_name
			else:
				new_customer = frappe.new_doc("Customer")
				new_customer.customer_name = order_customer_name
				new_customer.customer_group = self.amz_setting.customer_group
				new_customer.territory = self.amz_setting.territory
				new_customer.customer_type = self.amz_setting.customer_type
				new_customer.save()

				new_contact = frappe.new_doc("Contact")
				new_contact.first_name = order_customer_name
				new_contact.append("links", {"link_doctype": "Customer", "link_name": new_customer.name})

				new_contact.insert()

				return new_customer.name

		def create_address(order, customer_name) -> str | None:
			shipping_address = order.get("ShippingAddress")

			if not shipping_address:
				return
			else:
				make_address = frappe.new_doc("Address")
				make_address.address_line1 = shipping_address.get("AddressLine1", "Not Provided")
				make_address.city = shipping_address.get("City", "Not Provided")
				make_address.state = shipping_address.get("StateOrRegion").title()
				make_address.pincode = shipping_address.get("PostalCode")

				filters = [
					["Dynamic Link", "link_doctype", "=", "Customer"],
					["Dynamic Link", "link_name", "=", customer_name],
					["Dynamic Link", "parenttype", "=", "Address"],
				]
				existing_address = frappe.get_list("Address", filters)

				for address in existing_address:
					address_doc = frappe.get_doc("Address", address["name"])
					if (
						address_doc.address_line1 == make_address.address_line1
						and address_doc.pincode == make_address.pincode
					):
						return address

				make_address.append("links", {"link_doctype": "Customer", "link_name": customer_name})
				make_address.address_type = "Shipping"
				make_address.insert()

		order_id = order.get("AmazonOrderId")
		sinv = frappe.db.get_value("Sales Invoice", filters={"amazon_order_id": order_id}, fieldname="name")

		if sinv:
			return sinv
		else:
			# print(f"Getting order items for {order_id}")
			items = self.get_order_items(order_id)

			if not items:
				return

			customer_name = create_customer(order)
			create_address(order, customer_name)

			delivery_date = dateutil.parser.parse(order.get("LatestShipDate")).strftime("%Y-%m-%d") if order.get("LatestShipDate") else add_days(today(), 3)
			posting_date = dateutil.parser.parse(order.get("PurchaseDate")).strftime("%Y-%m-%d") if order.get("PurchaseDate") else today()

			sinv = frappe.new_doc("Sales Invoice")
			sinv.amazon_order_id = order_id
			# sinv.marketplace_id = order.get("MarketplaceId")
			sinv.customer = customer_name
			sinv.delivery_date = delivery_date
			sinv.posting_date = posting_date
			sinv.set_posting_time = 1
			sinv.company = self.amz_setting.company
			sinv.fulfillment_method = order.get("FulfillmentChannel") 

			for item in items:
				sinv.append("items", item)

			taxes_and_charges = self.amz_setting.taxes_charges

			if taxes_and_charges:
				charges_and_fees = self.get_charges_and_fees(order_id)

				for charge in charges_and_fees.get("charges"):
					sinv.append("taxes", charge)

				for fee in charges_and_fees.get("fees"):
					sinv.append("taxes", fee)
			try:
				sinv.set_missing_values()
				sinv.calculate_taxes_and_totals()
				sinv.save(ignore_permissions=True)
				sinv.submit()
			except Exception as e:
				title = f"Sales Order Creation Error for Order ID: {order_id}"
				message = f"Error creating sales order: {e}\n"
				message += f"Order Details: {order}\n"
				message += f"Traceback: {frappe.get_traceback()}"
				frappe.log_error( title=title, message=message)

			return sinv.name

	def get_orders(self, created_after) -> list:
		orders = self.get_orders_instance()
		order_statuses = [
			"PendingAvailability",
			"Pending",
			"Unshipped",
			"PartiallyShipped",
			"Shipped",
			"InvoiceUnconfirmed",
			"Canceled",
			"Unfulfillable",
		]
		fulfillment_channels = ["FBA", "SellerFulfilled"]

		orders_payload = self.call_sp_api_method(
			sp_api_method=orders.get_orders,
			created_after=created_after,
			order_statuses=order_statuses,
			fulfillment_channels=fulfillment_channels,
			max_results=10,
		)
		# print(f"Found {len(orders_payload.get('Orders'))} orders")
		sales_orders = []
		page = 1
		while True:
			if not orders_payload:
				break
			orders_list = orders_payload.get("Orders")
			next_token = orders_payload.get("NextToken")

			if not orders_list or len(orders_list) == 0:
				break

			print(f"Found {len(orders_list)} orders in this batch (Page {page})")
			page += 1
			for order in orders_list:
				# 'OrderStatus': 'Canceled',
				if order.get("OrderStatus") == "Canceled":
					print(f"Skipping canceled order {order.get('AmazonOrderId')}")
					continue
				# print(f"Let's create sales order {order}")
				print(f"Processing Order ID: {order.get('AmazonOrderId')} | Date: {order.get('PurchaseDate')} | Channel: {order.get('FulfillmentChannel')}")
				if order.get("AmazonOrderId") in ["111-2098714-7849831", "114-3263524-6333843", "113-8236680-9731404", "113-1268571-7165845"]:
					print(f"Order Item: {order}")
				try:
					# For AFN orders we only create a sales invoice
					# For MFN orders we create a sales order and sales invoice
					if order.get("FulfillmentChannel") == "MFN":
						print("""Creating sales order for MFN order""")
						sales_order = self.create_sales_order(order)
						sinv = make_sales_invoice(sales_order, ignore_permissions=True)
						sinv.set_missing_values()
						sinv.calculate_taxes_and_totals()
						if sinv.items:
							if name := frappe.db.exists("Sales Invoice", {"amazon_order_id": order.get("AmazonOrderId")}):
								sinv = frappe.get_doc("Sales Invoice", name)
							else:
								sinv.save(ignore_permissions=True)

							if sinv.docstatus == 0:
								sinv.submit()
						
						if sales_order:
							sales_orders.append(sales_order)
					
					if order.get("FulfillmentChannel") == "AFN":	
						self.create_sales_invoice(order)	
					
					frappe.db.commit()
				except Exception as e:
					frappe.db.rollback()
					title = f"Error creating sales order for Amazon Order ID: {order.get('AmazonOrderId')}"
					message = f"\nPayload: {order}\n"
					message += f"Error: {str(e)}\nTraceback: {frappe.get_traceback()}"
					frappe.log_error(title=title, message=message)

			if not next_token:
				break

			orders_payload = self.call_sp_api_method(
				sp_api_method=orders.get_orders, created_after=created_after, next_token=next_token,
			)

		return sales_orders

	def get_order_by_id(self, order_id: str) -> dict | None:
		orders_instance = self.get_orders_instance()
		result = self.call_sp_api_method(
			sp_api_method=orders_instance.get_order,
			order_id=order_id
		)
		return result
	
	def search_listings_item(self, seller_id, sku_list = None, sort_by = None, sort_order = None, page_size = None, next_token = None) -> list:
		listings = self.get_listings_instance()
		listings_payload = self.call_sp_api_method(
			sp_api_method=listings.search_listings_items, seller_id=seller_id, sku_list=sku_list, sort_by=sort_by, sort_order=sort_order, page_size=page_size, next_token=next_token
		)
		return listings_payload
	
	def get_listings_item(self, seller_id, sku) -> dict:
		listings = self.get_listings_instance()
		listings_payload = self.call_sp_api_method(
			sp_api_method=listings.get_listings_item, seller_id=seller_id, sku=sku
		)
		return listings_payload
	
	def get_catalog_items_instance(self) -> CatalogItems:
		return CatalogItems(**self.instance_params)
	
	def get_listings_instance(self) -> Listings:
		return Listings(**self.instance_params)


def validate_amazon_sp_api_credentials(**args) -> None:
	api = SPAPI(
		iam_arn=args.get("iam_arn"),
		client_id=args.get("client_id"),
		client_secret=args.get("client_secret"),
		refresh_token=args.get("refresh_token"),
		aws_access_key=args.get("aws_access_key"),
		aws_secret_key=args.get("aws_secret_key"),
		country_code=args.get("country"),
	)

	try:
		# validate client_id, client_secret and refresh_token.
		api.get_access_token()

		# validate aws_access_key, aws_secret_key, region and iam_arn.
		api.get_auth()

	except SPAPIError as e:
		msg = f"<b>Error:</b> {e.error}<br/><b>Error Description:</b> {e.error_description}"
		frappe.throw(msg)


def get_orders(amz_setting_name=None, created_after=None) -> list:
	if not amz_setting_name:
		setting = frappe.get_last_doc('Amazon SP API Settings')
		if setting:
			amz_setting_name = setting.name
	
	if not created_after:
		created_after = add_days(today(), -7)

	ar = AmazonRepository(amz_setting_name)
	return ar.get_orders(created_after)

def search_listings(amz_setting_name, seller_id, sku_list = None, sort_by = None, sort_order = None, page_size = None, next_token = None) -> list:
	ar = AmazonRepository(amz_setting_name)
	return ar.search_listings_item(seller_id, sku_list, sort_by, sort_order, page_size, next_token)

def get_listings_item(amz_setting_name, seller_id, sku) -> dict:
	ar = AmazonRepository(amz_setting_name)
	item = ar.get_listings_item(seller_id, sku)
	item.update({
		"amazon_sp_api_settings": amz_setting_name,
		"seller_id": seller_id,
	})

	return item