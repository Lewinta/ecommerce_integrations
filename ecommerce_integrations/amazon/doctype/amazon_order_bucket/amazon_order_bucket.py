# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import frappe
import time
from frappe.model.document import Document
from ecommerce_integrations.amazon.doctype.amazon_sp_api_settings.amazon_repository import AmazonRepository

class AmazonOrderBucket(Document):
	@frappe.whitelist()
	def sync_orders_with_erp(self):
		amazon_order = frappe.get_doc("Amazon Order", self.name)
		return amazon_order.sync_order_with_erp()
	

def import_bucket_order():
	AOB = frappe.qb.DocType("Amazon Order Bucket")
	orders = frappe.qb.from_(AOB).select(
		AOB.name
	).where(
		(AOB.status == "Pending")&
		(~AOB.order_status.isin(['Pending', 'Canceled']))
	).run(as_dict=True)

	for order in orders:
		doc = frappe.get_doc("Amazon Order Bucket", order.name)
		try:
			doc.sync_orders_with_erp()
			# Let's wait for 1 second before processing the next order
			time.sleep(2)
			frappe.db.commit()
		except Exception as e:
			title = f"Error in Syncing Amazon Order Bucket: {doc.name}"
			message = f"Error: {str(e)}\nTraceback:\n{frappe.get_traceback()}"
			frappe.log_error(title, message)
			frappe.db.rollback()

def update_bucket_status():
	""" We store Orders in Pending Status, but every hour
		we check if the status changed so we can update the bucket
	"""
	AOB = frappe.qb.DocType("Amazon Order Bucket")
	orders = frappe.qb.from_(AOB).select(
		AOB.name
	).where(
		(AOB.status == "Pending")&
		(AOB.order_status == "Pending")
	).run(as_dict=True)

	for order in orders:
		doc = frappe.get_doc("Amazon Order Bucket", order.name)
		try:
			az = AmazonRepository('2n7sn0hlgc')
			amazon_order = az.get_order_by_id(order['AmazonOrderId'])
			if amazon_order['OrderStatus'] != 'Pending':
				doc.order_status = amazon_order['OrderStatus']
				doc.save()
			frappe.db.commit()
		except Exception as e:
			title = f"Error in Syncing Amazon Order Bucket: {doc.name}"
			message = f"Error: {str(e)}\nTraceback:\n{frappe.get_traceback()}"
			frappe.log_error(title, message)
			frappe.db.rollback()