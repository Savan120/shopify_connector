// Copyright (c) 2024, Solufy and contributors
// For license information, please see license.txt

frappe.ui.form.on('Shopify Connector Setting', {
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Products'), function() {
            frappe.set_route('shopify-dashboard');
        });
    },
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Orders'), function() {
            frappe.set_route('shopify-order');
        });
    },
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Customer'), function() {
            frappe.set_route('shopify-customer');
        });
    },
    validate: function (frm) {
        if (frm.doc.enable_shopify) {
            frappe.call({
                method: "shopify_connector.shopify_connector.doctype.shopify_connector_setting.shopify_connector_setting.sync_shopify_locations",
                callback: function (r) {
                    frm.reload_doc();
                }
            });
        }
    }
});


