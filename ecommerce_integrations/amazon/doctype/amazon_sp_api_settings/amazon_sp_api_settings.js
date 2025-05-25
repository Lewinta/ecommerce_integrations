// Copyright (c) 2022, Frappe and contributors
// For license information, please see license.txt

frappe.ui.form.on('Amazon SP API Settings', {
	setup (frm) {
		frappe.realtime.on("amazon_listing_sync_progress", function(data) {
            frappe.dom.unfreeze();
            if (data.idx && data.length) {
                
                frappe.show_progress(
                    "Syncing Amazon listings",
                    data.idx, data.length,
                    `Syncing Amazon listings ${data.idx} of ${data.length}`,
                    true
                );
            }
        });
	},

	refresh(frm) {
		if (frm.doc.__islocal && !frm.doc.amazon_fields_map) {
			frm.trigger("set_default_fields_map");
		}
		frm.trigger("set_queries");
		frm.set_df_property("amazon_fields_map", "cannot_add_rows", true);
		frm.set_df_property("amazon_fields_map", "cannot_delete_rows", true);
	},

	set_default_fields_map(frm) {
		frappe.call({
			method: "set_default_fields_map",
			doc: frm.doc,
			callback: (r) => {
				if (!r.exc) refresh_field("amazon_fields_map");
			},
		});
	},

	set_queries(frm) {
		frm.set_query("warehouse", () => {
			return {
				filters: {
					"is_group": 0,
					"company": frm.doc.company,
				}
			};
		});

		frm.set_query("market_place_account_group", () => {
			return {
				filters: {
					"is_group": 1,
					"company": frm.doc.company,
				}
			};
		});
	},

	sync_listings_button(frm) {
        frappe.dom.freeze("Preparing for Sync...");
        frappe.call({
            method: "erpnext_ebay.sync_orders.enqueue_sync_listings",
            args: {ebay_manager: frm.docname}, 
        });
        frappe.show_alert({
            message: __("Syncing eBay listings;\n This may take some time..."),
            indicator: 'green'
        });
    },
});
