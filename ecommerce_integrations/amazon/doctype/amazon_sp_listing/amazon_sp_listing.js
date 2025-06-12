// Copyright (c) 2025, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on('Amazon SP Listing', {
	refresh(frm) {
		frm.trigger("add_custom_buttons");
	},
	add_custom_buttons(frm) {
		frm.add_custom_button(__('Sync Listings'), function() {
			frm.call(
				{
					method: "sync_with_erp",
					freeze: true,
					freeze_message: __('Syncing listings with ERPNext...'),
				}
			).then(r => {
				if (r.message) {
					frappe.utils.play_sound("submit");
					frappe.show_alert({
						message: __('Listings synced successfully'),
						indicator: 'green'
					});
				} else {
					frappe.show_alert({
						message: __('No listings to sync'),
						indicator: 'orange'
					});
				}
			});
		});	
	}
});
