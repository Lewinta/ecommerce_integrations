frappe.ui.form.on('Item', {
	setup: function(frm) {
        console.log("working")
	    frm.set_query('sku', 'custom_amazon_listings', function(doc, cdt, cdn) {
            let d = locals[cdt][cdn];
            return {
                query: 'ecommerce_integrations.amazon.doctype.amazon_sp_listing.amazon_sp_listing.amazon_sp_listings_ct_query'
            }
	    });
	},
});