frappe.provide('shopify');

frappe.pages['shopify-dashboard'].on_page_load = function (wrapper) {
    let page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Synced Shopify Products',
        single_column: true
    });

    var styleElement = document.createElement('style');
    styleElement.innerHTML = `
        .clean-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 25px;
            background-color: var(--fg-color);
            border-radius: var(--border-radius-md);
            overflow: hidden;
            box-shadow: var(--shadow-sm);
        }

        .clean-table th, .clean-table td {
            padding: 16px 20px;
            text-align: left;
            font-size: var(--text-md);
            color: var(--text-color);
            border-bottom: 1px solid var(--border-color);
        }

        .clean-table thead th {
            background-color: var(--bg-gray-100);
            font-weight: var(--font-weight-semibold);
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-size: var(--text-sm);
            border-bottom: 2px solid var(--border-color-light);
        }

        /* No border on the last row */
        .clean-table tbody tr:last-child td {
            border-bottom: none;
        }

        .clean-table tbody tr:nth-child(even) {
            background-color: var(--lighter-background-color);
        }

        /* Subtle hover effect */
        .clean-table tbody tr:hover {
            background-color: var(--hover-color);
            cursor: pointer;
        }

        /* Make links black */
        .clean-table a {
            color: var(--text-color); 
            text-decoration: none;
        }
        .clean-table a:hover {
            text-decoration: underline;
        }

        /* --- Professional Total Count Display --- */
        .total-count-section {
            background-color: var(--blue-50);
            color: var(--blue-700);
            padding: 18px 25px;
            border-radius: var(--border-radius-md);
            font-size: var(--text-xl);
            font-weight: var(--font-weight-bold);
            margin-bottom: 25px;
            border: 1px solid var(--blue-200);
            text-align: center;
            box-shadow: var(--shadow-md);
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .no-data-found {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
            font-size: var(--text-lg);
            background-color: var(--bg-color);
            border: 1px dashed var(--border-color);
            border-radius: var(--border-radius-md);
            margin-top: 20px;
        }
    `;

    document.head.appendChild(styleElement);

    new shopify.SyncedProductViewer(wrapper);
}

shopify.SyncedProductViewer = class {
    constructor(wrapper) {
        this.wrapper = $(wrapper).find('.layout-main-section');
        this.init();
    }

    async init() {
        const syncedData = await this.fetchSyncedProducts();
        this.renderSyncedProductCount(syncedData.synced_product_count);
        this.renderSyncedProducts(syncedData.synced_products);
    }

    async fetchSyncedProducts() {
        try {
            const response = await frappe.call({
                method: 'shopify_connector.shopify_connector.page.shopify_dashboard.shopify_dashboard.get_synced_products'
            });
            return response.message;
        } catch (error) {
            frappe.msgprint(__("Error fetching synced products: {0}", [error.message || error]));
            return { synced_products: [], synced_product_count: 0 };
        }
    }

    renderSyncedProducts(syncedProducts) {
        const table = $('<table class="clean-table"></table>')
            .append('<thead><tr><th>Name</th><th>Shopify ID</th><th>Item Groups</th></tr></thead>')
            .append('<tbody></tbody>');

        const tbody = table.find('tbody');

        if (syncedProducts && syncedProducts.length > 0) {
            syncedProducts.forEach(product => {
                const row = `<tr><td><a href="/app/item/${(product.item_name || '')}">${product.item_name || 'N/A'}</a></td><td>${product.shopify_id || 'N/A'}</td><td>${product.item_group || 'N/A'}</td></tr>`;
                tbody.append(row);
            });
        } else {
            tbody.append('<tr><td colspan="3"><div class="no-data-found">No synced products found.</div></td></tr>');
        }

        this.wrapper.append(table);
    }

    renderSyncedProductCount(syncedProductCount) {
        const countContainer = $(`<div class="total-count-section"></div>`).text(`Total Synced Product Count: ${syncedProductCount}`);
        this.wrapper.prepend(countContainer);
    }
}