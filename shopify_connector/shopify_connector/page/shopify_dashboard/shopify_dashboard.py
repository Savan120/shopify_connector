import frappe

@frappe.whitelist()
def get_synced_products():
    try:
        synced_products = frappe.get_all("Item", filters={"shopify_id": ("!=", "")},fields=["item_name","shopify_id","item_group"])
        shopify_product_count = frappe.db.count("Item", filters={"shopify_id": ("!=", "")})

        synced_product_count = shopify_product_count
        return {
            "synced_products": synced_products,
            "synced_product_count": synced_product_count
        }
    except Exception as e:
        frappe.throw(f"Error fetching synced products: {str(e)}")
