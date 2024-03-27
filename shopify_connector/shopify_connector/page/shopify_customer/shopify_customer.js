
frappe.pages['shopify-customer'].on_page_load = function(wrapper) {
    var page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Shopify Customer', // Update page title
        single_column: true
    });

    // Function to fetch and render synced customers
    function fetchSyncedCustomers() {
        frappe.call({
            method: 'shopify_connector.shopify_connector.page.shopify_customer.shopify_customer.get_synced_customers', // Update method name
            callback: function(r) {
                if (r.message) {
                    renderSyncedCustomers(r.message, r.total_count);
                }
            }
        });
    }

    // Function to render synced customers in table format
    function renderSyncedCustomers(syncedCustomers, total_count) {
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

        console.log(":::::::::::syncedCustomers 22:::::::::::", syncedCustomers[0])
        console.log(":::::::::::total_count 22:::::::::::", syncedCustomers[1])

        var tableHtml = `
            <table class="table-bordered">
                <thead>
                    <tr class='table-bordered th'>
                        <th>Customer Name</th> <!-- Change table headers -->
                        <th>Shopify Email</th>
                        <!-- Add more table headers as needed -->
                    </tr>
                </thead>
                <tbody>`;

        syncedCustomers[0].forEach(function(customer) {
            tableHtml += `
                <tr>
                    <td>${customer.shopify_id}</td> <!-- Display Shopify ID -->
                    <td>${customer.shopify_email}</td> <!-- Display Customer Name -->
                    <!-- Add more table cells for additional customer details -->
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
