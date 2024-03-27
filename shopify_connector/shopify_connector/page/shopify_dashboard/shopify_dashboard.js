
frappe.provide('shopify');

frappe.pages['shopify-dashboard'].on_page_load = function (wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Synced Shopify Products',
        single_column: true
    });

    new shopify.SyncedProductViewer(wrapper);
}

shopify.SyncedProductViewer = class {
    constructor(wrapper) {
        this.wrapper = $(wrapper).find('.layout-main-section');
        this.init();
    }

    async init() {
        const syncedData = await this.fetchSyncedProducts();
        this.renderSyncedProducts(syncedData.synced_products);
        this.renderSyncedProductCount(syncedData.synced_product_count);
    }

    async fetchSyncedProducts() {
        try {
            const response = await frappe.call({
                method: 'shopify_connector.shopify_connector.page.shopify_dashboard.shopify_dashboard.get_synced_products'
            });
            return response.message; // assuming the method returns both products and count
        } catch (error) {
            frappe.msgprint(__("Error fetching synced products"));
        }
    }

    renderSyncedProducts(syncedProducts) {
        const table = $('<table class="table table-bordered"></table>')
            .append('<thead><tr><th>Name</th><th>Shopify ID</th><th>Item Groups</th></tr></thead>')
            .append('<tbody></tbody>');

        const tbody = table.find('tbody');
        syncedProducts.forEach(product => {
            const row = `<tr><td>${product.item_name}</td><td>${product.shopify_id}</td><td>${product.item_group}</td></tr>`;
            tbody.append(row);
        });

        this.wrapper.append(table);
    }

    renderSyncedProductCount(syncedProductCount) {
        const countContainer = $('<div></div>').text(`Synced Product Count: ${syncedProductCount}`);
        this.wrapper.append(countContainer);
    }
}
