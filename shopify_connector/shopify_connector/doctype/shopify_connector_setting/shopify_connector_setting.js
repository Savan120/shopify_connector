// Copyright (c) 2024, Solufy and contributors
// For license information, please see license.txt

frappe.ui.form.on('Shopify Connector Setting', {
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Products'), function() {
            frappe.set_route('shopify-dashboard');
        });
    }
});


frappe.ui.form.on('Shopify Connector Setting', {
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Orders'), function() {
            frappe.set_route('shopify-order');
        });
    }
});

frappe.ui.form.on('Shopify Connector Setting', {
    refresh: function(frm) {
        frm.add_custom_button(__('Sync Customer'), function() {
            frappe.set_route('shopify-customer');
        });
    }
});








