frappe.pages['shopify-customer'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Shopify Customer',
        single_column: true
    });

    function fetchSyncedCustomers() {
        frappe.call({
            method: 'shopify_connector.shopify_connector.page.shopify_customer.shopify_customer.get_synced_customers',
            callback: function(r) {
                if (r.message) {
                    renderSyncedCustomers(r.message, r.total_count);
                }
            }
        });
    }

    function renderSyncedCustomers(syncedCustomers, total_count) {
        var styleElement = document.createElement('style');
        styleElement.innerHTML = `
            .table-bordered {
                width: 100%;
                border-collapse: collapse;
                margin-top: 20px;
                background-color: var(--fg-color);
                border: 1px solid var(--border-color);
                border-radius: var(--border-radius-md);
                overflow: hidden;
                box-shadow: var(--shadow-sm);
            }

            .table-bordered th, .table-bordered td {
                border: 1px solid var(--border-color); 
                padding: 14px 18px;
                text-align: left;
                font-size: var(--text-md); 
                color: var(--text-color);
                word-break: break-word; 
            }

            .table-bordered th {
                background-color: var(--bg-gray-100);
                font-weight: var(--font-weight-bold);
                color: var(--text-extra-muted);
                text-transform: uppercase;
                letter-spacing: 0.5px;
                padding: 14px 18px;
            }

            .table-bordered tbody tr:nth-child(even) {
                background-color: var(--lighter-background-color);
            }

            .table-bordered tbody tr:hover {
                background-color: var(--hover-color);
                cursor: pointer;
            }

            .total-count {
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

            .table-bordered thead tr.table-bordered.th {
                background-color: var(--bg-gray-100);
            }
        `;

        document.head.appendChild(styleElement);

        console.log(":::::::::::syncedCustomers 22:::::::::::", syncedCustomers[0])
        console.log(":::::::::::total_count 22:::::::::::", syncedCustomers[1])

        var tableHtml = `
            <table class="table-bordered">
                <thead>
                    <tr class='table-bordered th'>
                        <th>Customer Name</th> <th>Shopify Email</th>
                        </tr>
                </thead>
                <tbody>`;

        syncedCustomers[0].forEach(function(customer) {
            tableHtml += `
                <tr>
                    <td><a href="/app/customer/${customer.shopify_id || 'N/A'}">${customer.shopify_id || 'N/A'}</td> <td>${customer.shopify_email || 'N/A'}</td> 
                </tr>`;
        });

        tableHtml += `
                </tbody>
            </table>`;

        // Add the total count above the table
        var totalCountHtml = `<p class='total-count'>Total Synced Customers: ${syncedCustomers[1]}</p>`;
        $(page.body).html(totalCountHtml + tableHtml);
    }

    // Fetch and render synced customers when the page loads
    fetchSyncedCustomers();
};