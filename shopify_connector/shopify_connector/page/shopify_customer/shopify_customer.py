import frappe

@frappe.whitelist()
def get_synced_customers():
    try:
        synced_customers = frappe.get_all("Customer", filters={"shopify_email": ("!=", ""), "shopify_id": ("!=", "")}, fields=["shopify_email","shopify_id","customer_name"])

        total_count = len(synced_customers)

        customers_data = []
        for customer in synced_customers:
            customers_data.append({
                "shopify_customer": customer.customer_name,
                "shopify_email": customer.shopify_email,
                "shopify_id": customer.shopify_id
            })
        return customers_data, total_count

    except Exception as e:
        frappe.throw(f"Error fetching synced customers: {str(e)}")



