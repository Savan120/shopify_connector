import frappe
import requests

def send_customer_to_shopify_hook(doc, method):
    if getattr(doc.flags, "from_shopify", False):
        return
    
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = "2024-01"
    if shopify_keys.sync_customer:
        
        customer_payload = {
            "customer": {
                "first_name": doc.first_name or "",
                "last_name": doc.last_name or "",
                "email": doc.email or "",
                "phone": doc.phone or "",
                "addresses": []
            }
        }

        address_links = frappe.get_all("Dynamic Link", filters={
            "link_doctype": "Customer",
            "link_name": doc.name,
            "parenttype": "Address"
        }, fields=["parent"])

        for link in address_links:
            address = frappe.get_doc("Address", link["parent"])
            customer_payload["customer"]["addresses"].append({
                "address1": address.address_line1,
                "address2": address.address_line2 or "",
                "city": address.city,
                "province": address.state,
                "country": address.country,
                "zip": address.pincode,
                "phone": address.phone
            })
            # customer_doc.flags.from_shopify = True

        try:
            if doc.shopify_customer_id:
                customer_payload["customer"]["id"] = doc.shopify_customer_id
                url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{doc.shopify_customer_id}.json"
                response = requests.put(url, json=customer_payload, verify=False)
            else:
                url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"
                response = requests.post(url, json=customer_payload, verify=False)

            if response.status_code not in (200, 201):
                frappe.log_error(f"Shopify customer sync failed: {response.text}", "Shopify Sync Error")
            else:
                shopify_id = response.json()["customer"]["id"]
                frappe.db.set_value("Customer", doc.name, "shopify_customer_id", shopify_id)

        except Exception as e:
            frappe.log_error(f"Exception during Shopify customer sync: {str(e)}", "Shopify Sync Error")