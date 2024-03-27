
frappe.pages['shopify-order'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Shopify Order',
        single_column: true
    });

    // Function to fetch and render synced orders
    function fetchSyncedOrders() {
        frappe.call({
            method: 'shopify_connector.shopify_connector.page.shopify_order.shopify_order.get_synced_orders',
            callback: function(r) {
                if (r.message) {
                    renderSyncedOrders(r.message, r.total_count);
                }
            }
        });
    }

    // Function to render synced orders in table format
    function renderSyncedOrders(syncedOrders, total_count) {
    	var styleElement = document.createElement('style');
        styleElement.innerHTML = `
            /* Style for the table */
            .table-bordered {
                border: 5px solid #ddd;
                border-collapse: collapse;
                width: 100%;
            }

            .table-bordered th, .table-bordered td {
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }

            .table-bordered th {
                background-color: #f2f2f2;
                font-weight: bold;
            }

            /* Style for the total count display */
            .total-count {
            	background-color: yellow;
                font-size: 24px;
                margin-bottom: 20px;
            }
        `;

        // Append the <style> element to the <head>
        document.head.appendChild(styleElement);

        console.log(":::::::::::syncedOrders 22:::::::::::",syncedOrders[0])
        console.log(":::::::::::total_count 22:::::::::::",syncedOrders[1])

        var tableHtml = `
            <table class="table-bordered">
                <thead>
                    <tr class='table-bordered th'>
                        <th>Order ID</th>
                        <th>Customer</th>
                        <!-- Add more table headers as needed -->
                    </tr>
                </thead>
                <tbody>`;
        
        syncedOrders[0].forEach(function(order) {
            tableHtml += `
                <tr>
                    <td>${order.shopify_id}</td>
                    <td>${order.customer}</td>
                    <!-- Add more table cells for additional order details -->
                </tr>`;
        });

        tableHtml += `
                </tbody>
            </table>`;

        // Add the total count above the table
        var totalCountHtml = `<p class='total-count'>Total Synced Orders: ${syncedOrders[1]}</p>`;
        $(page.body).html(totalCountHtml + tableHtml);
    }

    // Fetch and render synced orders when the page loads
    fetchSyncedOrders();
};
