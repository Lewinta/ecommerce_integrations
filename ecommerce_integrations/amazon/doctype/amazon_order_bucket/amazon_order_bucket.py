# Copyright (c) 2025, Frappe and contributors
# For license information, please see license.txt

import frappe
import time
from frappe.model.document import Document

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