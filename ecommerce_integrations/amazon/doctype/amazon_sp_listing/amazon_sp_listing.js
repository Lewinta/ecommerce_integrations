// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on('Amazon SP Listing', {
	refresh(frm) {
		frm.trigger("add_custom_buttons");
	},
	add_custom_buttons(frm) {
		frm.add_custom_button(__('Sync Listings'), function() {
			frm.call(
				"sync_with_erp",
				).then(r => {
				if (r.message && r.message.status === "ACCEPTED") {
					frappe.utils.play_sound("submit");
					frappe.show_alert({
						message: __('Listings synced successfully'),
						indicator: 'green'
					});
				} else {
					frappe.show_alert({
						message: __('Listing sync failed or was not accepted'),
						indicator: 'red'
					});
					console.warn("Sync Listings response:", r.message);
				}
			});
		}, __('Actions'));
			
		frm.add_custom_button(__('Sync Inventory'), function() {
			if (frm.doc.fulfillment_channel != 'FBM') 
				return frappe.msgprint(__('Inventory sync is only available for MFN listings.'));
				frappe.dom.freeze(__('Syncing inventory...'));
				frm.call("sync_inventory").then(r => {
					if (r.message && r.message.status === "ACCEPTED") {
						frappe.utils.play_sound("submit");
						frappe.show_alert({
							message: __('Listings synced successfully'),
							indicator: 'green'
						});
					} else {
						frappe.show_alert({
							message: __('Listing sync failed or was not accepted'),
							indicator: 'red'
						});
						console.warn("Sync Listings response:", r.message);
					}
					frm.reload_doc();
					frappe.dom.unfreeze();
				})
		},
		__('Actions')
	);
	}
});
