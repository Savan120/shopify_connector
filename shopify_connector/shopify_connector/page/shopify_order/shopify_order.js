frappe.pages['shopify-order'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Shopify Order',
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

        .clean-table a {
            color: var(--text-color); /* For black link color */
            text-decoration: none;
        }
        .clean-table a:hover {
            text-decoration: underline;
        }

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

    function fetchSyncedOrders() {
        frappe.call({
            method: 'shopify_connector.shopify_connector.page.shopify_order.shopify_order.get_synced_orders',
            callback: function(r) {
                if (r.message) {
                    renderSyncedOrders(r.message[0], r.message[1]);
                } else {
                    renderSyncedOrders([], 0); 
                }
            }
        });
    }

    function renderSyncedOrders(syncedOrders, total_count) {
        var tableHtml = `
            <table class="clean-table">
                <thead>
                    <tr>
                        <th>Order ID</th>
                        <th>Customer</th>
                        </tr>
                </thead>
                <tbody>`;
        
        if (syncedOrders && syncedOrders.length > 0) {
            syncedOrders.forEach(function(order) {

                const orderLink = `/app/sales-order/${encodeURIComponent(order.name || '')}`;
                
                tableHtml += `
                    <tr>
                        <td><a href="${orderLink}">${order.shopify_id || 'N/A'}</a></td>
                        <td>${order.customer || 'N/A'}</td>
                        </tr>`;
            });
        } else {
            tableHtml += `
                <tr>
                    <td colspan="2"><div class="no-data-found">No synced orders found.</div></td>
                </tr>`;
        }
        tableHtml += `
                </tbody>
            </table>`;

        var totalCountHtml = `<div class='total-count-section'>Total Synced Orders: ${total_count}</div>`;
        $(page.body).html(totalCountHtml + tableHtml);
    }

    fetchSyncedOrders();
};