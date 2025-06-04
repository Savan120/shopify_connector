import frappe

@frappe.whitelist()
def get_synced_products():
    try:
        # Assuming you have a custom DocType named SyncedProduct to store synced product data
        synced_products = frappe.get_all("Item", fields=["item_name","shopify_id","item_group"])
        shopify_product_count = frappe.db.count("Item", filters={"shopify_id": ("!=", "")})

        # Fetch count of synced products
        synced_product_count = shopify_product_count
        
        # Returning both synced products and count
        return {
            "synced_products": synced_products,
            "synced_product_count": synced_product_count
        }
    except Exception as e:
        frappe.throw(f"Error fetching synced products: {str(e)}")
