import frappe
import requests

def send_customer_to_shopify_hook(doc, method):
    if not doc.flags.from_shopify:
        return

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = "2024-01"

    if shopify_keys.sync_customer:

        email = ""
        phone = ""


        address_links = frappe.get_all("Dynamic Link", filters={
            "link_doctype": "Customer",
            "link_name": doc.name,
            "parenttype": "Address"
        }, fields=["parent"])


        if not address_links and doc.customer_name != doc.name:
            address_links = frappe.get_all("Dynamic Link", filters={
                "link_doctype": "Customer",
                "link_name": doc.customer_name,
                "parenttype": "Address"
            }, fields=["parent"])

        address_list = []

        if address_links:
            primary_address = frappe.get_doc("Address", address_links[0]["parent"])
            email = primary_address.email_id or ""
            phone = primary_address.phone or ""

            for link in address_links:
                address = frappe.get_doc("Address", link["parent"])
                address_list.append({
                    "address1": address.address_line1,
                    "address2": address.address_line2 or "",
                    "city": address.city,
                    "province": address.state,
                    "country": address.country,
                    "zip": address.pincode,
                    "phone": address.phone,
                    "email": address.email_id
                })
        elif doc.get("customer_primary_address"):
            primary_address = frappe.get_doc("Address", doc.customer_primary_address)
            email = primary_address.email_id or ""
            phone = primary_address.phone or ""
            address_list.append({
                "address1": primary_address.address_line1,
                "address2": primary_address.address_line2 or "",
                "city": primary_address.city,
                "province": primary_address.state or primary_address.custom_state,
                "country": primary_address.country,
                "zip": primary_address.pincode,
                "phone": primary_address.phone,
                "email": primary_address.email_id
            })
            


        customer_payload = {
            "customer": {
                "first_name": doc.customer_name or "",
                "email": email,
                "phone": phone,
                "addresses": address_list
            }
        }

        try:
            shopify_customer_id = doc.shopify_id or frappe.db.get_value("Customer", doc.name, "shopify_id")

            if shopify_customer_id:
                customer_payload["customer"]["id"] = shopify_customer_id
                url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}.json"
                response = requests.put(url, json=customer_payload, verify=False)
            else:
                url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"
                response = requests.post(url, json=customer_payload, verify=False)
        

            if response.status_code not in (200, 201):
                frappe.log_error(f"Shopify customer sync failed: {response.text}", "Shopify Sync Error")
            else:
                shopify_id = response.json()["customer"]["id"]
                shopify_email = response.json()["customer"]["email"]
                doc.flags.from_shopify = True
                doc.db_set("shopify_id",shopify_id)
                # doc.db_set("shopify_email",shopify_email)

        except Exception as e:
            frappe.log_error(f"Exception during Shopify customer sync: {str(e)}", "Shopify Sync Error")




def delete_customer_from_shopify(doc, method):
    if not doc.shopify_id:
        return

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = "2024-01"
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{doc.shopify_id}.json"

    response = requests.delete(url, verify=False)

    if response.status_code != 200:
        frappe.log_error(f"Failed to delete customer from Shopify: {response.text}", "Shopify Customer Delete Error")




def get_current_domain_name() -> str:
    if frappe.conf.developer_mode and frappe.conf.localtunnel_url:
        return frappe.conf.localtunnel_url
    else:
        return frappe.request.host

# def send_item_to_shopify(doc, method):
#     if getattr(doc.flags, "from_shopify", False):
#         return

#     item = frappe.get_doc("Item", doc.name)

#     if not item.has_variants and item.variant_of:
#         return

#     site_url = get_current_domain_name()
#     shopify_keys = frappe.get_single("Shopify Connector Setting")
#     SHOPIFY_API_KEY = shopify_keys.api_key
#     SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
#     SHOPIFY_STORE_URL = shopify_keys.shop_url
#     SHOPIFY_API_VERSION = "2024-01"
#     image_url = ""
#     if item.image:
#         if not site_url.startswith("http"):
#             site_url = "https://" + site_url
#         image_url = site_url + item.image

#     product_payload = {
#         "product": {
#             "title": item.item_name,
#             "body_html": f"<strong>{item.description or ''}</strong>",
#             "vendor": item.brand or "Default Vendor",
#             "product_type": item.item_group or "",
#             "variants": [],
#             "images": [],
#         }
#     }
#     product_payload["product"]["variants"].append({"price": item.shopify_selling_rate or 0.0})
#     if image_url:
#         product_payload["product"]["images"].append({"src": image_url})
        

#     if item.shopify_id:
#         url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{item.shopify_id}.json"
#         response = requests.put(url, json=product_payload, verify=False)
        
#     else:
#         url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json"
#         response = requests.post(url, json=product_payload, verify=False)

#         if response.status_code == 201:
#             shopify_product = response.json()["product"]
#             frappe.db.set_value("Item", item.name, "shopify_id", shopify_product["id"])

#             for variant in shopify_product.get("variants", []):
#                 sku = variant.get("sku")
#                 variant_id = variant.get("id")
#                 if sku and variant_id:
#                     try:
#                         frappe.db.set_value("Item", {"item_code": sku}, "shopify_variant_id", variant_id)
#                     except Exception as e:
#                         frappe.log_error(f"Failed to set variant ID for SKU {sku}: {str(e)}", "Shopify Sync")

def send_item_to_shopify(doc, method):
    if getattr(doc.flags, "from_shopify", False):
        return

    item = frappe.get_doc("Item", doc.name)

    if not item.has_variants and item.variant_of:
        return

    site_url = get_current_domain_name()
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = "2024-01"

    image_url = ""
    if item.image:
        if not site_url.startswith("http"):
            site_url = "https://" + site_url
        image_url = site_url + item.image

    product_payload = {
        "product": {
            "title": item.item_name,
            "body_html": f"<strong>{item.description or ''}</strong>",
            "vendor": item.brand or "Default Vendor",
            "product_type": item.item_group or "",
            "variants": [],
            "images": [],
            "options": []
        }
    }

    template_item = item.name
    variant_items = frappe.get_all("Item", filters={"variant_of": template_item}, fields=["name", "item_code", "shopify_selling_rate", "image"])

    if not variant_items:
        product_payload["product"]["variants"].append({
            "price": item.shopify_selling_rate or 0.0
        })
    else:
        
        template_attributes = frappe.get_all("Item Variant Attribute", filters={"parent": template_item}, fields=["attribute"])
        option_map = {attr["attribute"]: set() for attr in template_attributes}

        for position, variant in enumerate(variant_items, start=1):
            variant_doc = frappe.get_doc("Item", variant["name"])
            attributes = frappe.get_all("Item Variant Attribute", filters={"parent": variant_doc.name}, fields=["attribute", "attribute_value"])
            attr_dict = {attr.attribute: attr.attribute_value for attr in attributes}

            for attr in option_map:
                if attr in attr_dict:
                    option_map[attr].add(attr_dict[attr])

            values = list(attr_dict.values()) + [None] * 3
            variant_data = {
                "option1": values[0],
                "option2": values[1],
                "option3": values[2],
                "price": variant_doc.shopify_selling_rate or 0.0,
                "sku": variant_doc.item_code,
                "inventory_policy": "deny",
                "taxable": True,
                "position": position
            }
            product_payload["product"]["variants"].append(variant_data)

            if variant_doc.image:
                product_payload["product"]["images"].append({
                    "src": site_url + variant_doc.image
                })

        for attr_name, values in option_map.items():
            product_payload["product"]["options"].append({
                "name": attr_name,
                "values": list(values)
            })


    if item.shopify_id:
        url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{item.shopify_id}.json"
        response = requests.put(url, json=product_payload, verify=False)
        print(response.text)
    else:
        url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json"
        response = requests.post(url, json=product_payload, verify=False)

        if response.status_code == 201:
            shopify_product = response.json()["product"]
            frappe.db.set_value("Item", item.name, "shopify_id", shopify_product["id"])

            for variant in shopify_product.get("variants", []):
                sku = variant.get("sku")
                variant_id = variant.get("id")
                if sku and variant_id:
                    try:
                        frappe.db.set_value("Item", {"item_code": sku}, "shopify_variant_id", variant_id)
                    except Exception as e:
                        frappe.log_error(f"Failed to set variant ID for SKU {sku}: {str(e)}", "Shopify Sync")

    if response.status_code not in (200, 201):
        frappe.log_error(f"Shopify product/variant sync failed: {response.text}", "Shopify Sync Error")
