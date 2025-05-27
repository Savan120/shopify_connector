# In your_custom_app/module/doctype/shopify_order/shopify_order.py

import frappe


@frappe.whitelist()
def get_synced_orders():
    try:
        synced_orders = frappe.get_all("Sales Order", filters={"status": "To Deliver and Bill", "shopify_id": ("!=", "")}, fields=["shopify_id", "customer", "name"])
        print("::::::::::synced_orders:::::::::::::", synced_orders)

        total_count = len(synced_orders)

        orders_data = []
        for order in synced_orders:
            orders_data.append({
                "shopify_id": order.shopify_id,
                "customer": order.customer,
                "name": order.name,
            })

        # Return the orders data along with the total count
        print("::::::::orders_data:::::::::::", orders_data)
        print("::::::::total_count:::::::::::", total_count)
        return orders_data, total_count

    except Exception as e:
        frappe.throw(f"Error fetching synced orders: {str(e)}")
