// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on('Amazon Order', {
	refresh(frm) {
		frm.trigger("add_custom_buttons");
	},
	add_custom_buttons(frm) {
		frm.add_custom_button(__('Sync Order with ERP'), function() {
			frappe.dom.freeze(__('Syncing order with ERP...'));
			frm.call('sync_order_with_erp').then(r => {
				frappe.dom.unfreeze();
				if (r.message) {
					frappe.utils.play_sound("submit");
					frappe.show_alert({
						message: __('Order synced successfully'),
						indicator: 'green'
					});
				} else {
					frappe.show_alert({
						message: __('Order sync failed, please check logs'),
						indicator: 'red'
					});
				}
			});
		});
	}
});
