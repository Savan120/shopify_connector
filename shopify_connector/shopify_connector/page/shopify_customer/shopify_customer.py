import frappe

@frappe.whitelist()
def get_synced_customers():
    try:
        # Query the database for synced orders
        synced_customers = frappe.get_all("Customer", filters={"shopify_email": ("!=", "")}, fields=["shopify_email","customer_name"])
        print("::::::::::synced_customers:::::::::::::", synced_customers)

        # Get the total count of synced customers
        total_count = len(synced_customers)

        # Format the data as a list of dictionaries
        customers_data = []
        for customer in synced_customers:
            customers_data.append({
                "shopify_id": customer.customer_name,
                "shopify_email": customer.shopify_email,
            })

        # Return the customers data along with the total count
        print("::::::::customers_data:::::::::::", customers_data)
        print("::::::::total_count:::::::::::", total_count)
        return customers_data, total_count

    except Exception as e:
        frappe.throw(f"Error fetching synced customers: {str(e)}")



