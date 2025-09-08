// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on('Amazon Order Bucket', {
	refresh(frm) {
		frm.trigger("add_custom_buttons");
	},
	add_custom_buttons(frm) {
		if(frm.is_new() || frm.doc.status === "Completed")
			return 
		frm.add_custom_button(__('Sync Orders with ERP'), function() {
			frappe.dom.freeze(__('Syncing order with ERP...'));
			frm.call('sync_orders_with_erp').then(r => {
				frappe.dom.unfreeze();
				if (r.message) {
					frappe.utils.play_sound("submit");
					frappe.show_alert({
						message: __('Orders synced successfully'),
						indicator: 'green'
					});
				} else {
					frappe.show_alert({
						message: __('Order sync failed, please check logs'),
						indicator: 'red'
					});
				}
				frm.reload_doc();
			});
		}).addClass('btn-primary');
	}
});
