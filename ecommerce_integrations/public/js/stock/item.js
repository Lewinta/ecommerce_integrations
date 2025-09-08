frappe.ui.form.on('Item', {
	setup(frm) {
        console.log("working")
	    frm.set_query('sku', 'custom_amazon_listings', function(doc, cdt, cdn) {
            let d = locals[cdt][cdn];
            return {
                query: 'ecommerce_integrations.amazon.doctype.amazon_sp_listing.amazon_sp_listing.amazon_sp_listings_ct_query'
            }
	    });
	},
    refresh(frm) {
        frm.trigger('add_custom_buttons');
    },
    add_custom_buttons(frm) {
        if (!frm.doc.__islocal && frm.doc.custom_amazon_listings && frm.doc.custom_amazon_listings.length > 0) {
            frm.add_custom_button(__('View Amazon Listing'), function() {
                frappe.set_route('Form', 'Amazon SP Listing', frm.doc.custom_amazon_listings[0].sku)
            }, __("View"));
        }
    }
});