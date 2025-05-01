# import frappe
# import requests

# def send_customer_to_shopify_hook(doc, method):
#     if getattr(doc.flags, "from_shopify", False):
#         return
#     # if getattr(doc.flags, "from_shopify", False):
#     #     return
    
#     shopify_keys = frappe.get_single("Shopify Connector Setting")
#     SHOPIFY_API_KEY = shopify_keys.api_key
#     SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
#     SHOPIFY_STORE_URL = shopify_keys.shop_url
#     SHOPIFY_API_VERSION = "2024-01"
#     if shopify_keys.sync_customer:
        
#         customer_payload = {
#             "customer": {
#                 "first_name": doc.customer_name or "",
#                 "addresses": []
#             }
#         }

#         address_links = frappe.get_all("Dynamic Link", filters={
#             "link_doctype": "Customer",
#             "link_name": doc.name,
#             "parenttype": "Address"
#         }, fields=["parent"])

#         for link in address_links:
#             address = frappe.get_doc("Address", link["parent"])
#             customer_payload["customer"]["addresses"].append({
#                 "address1": address.address_line1,
#                 "address2": address.address_line2 or "",
#                 "city": address.city,
#                 "province": address.state,
#                 "country": address.country,
#                 "zip": address.pincode,
#                 "phone": address.phone,
#                 "email": address.email_id
#             })
#             # customer_doc.flags.from_shopify = True

#         try:
#             if doc.shopify_customer_id:
#                 customer_payload["customer"]["id"] = doc.shopify_customer_id
#                 url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{doc.shopify_customer_id}.json"
#                 response = requests.put(url, json=customer_payload, verify=False)
#                 print(url)
#                 9/0
#             else:
#                 url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"
#                 response = requests.post(url, json=customer_payload, verify=False)

#             if response.status_code not in (200, 201):
#                 frappe.log_error(f"Shopify customer sync failed: {response.text}", "Shopify Sync Error")
#             else:
#                 shopify_id = response.json()["customer"]["id"]
#                 doc.flags.from_shopify = True
#                 frappe.db.set_value("Customer", doc.name, "shopify_customer_id", shopify_id)

#         except Exception as e:
#             frappe.log_error(f"Exception during Shopify customer sync: {str(e)}", "Shopify Sync Error")



# import frappe
# import requests

# def send_customer_to_shopify_hook(doc, method):
#     if getattr(doc.flags, "from_shopify", False):
#         return

#     shopify_keys = frappe.get_single("Shopify Connector Setting")
#     SHOPIFY_API_KEY = shopify_keys.api_key
#     SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
#     SHOPIFY_STORE_URL = shopify_keys.shop_url
#     SHOPIFY_API_VERSION = "2024-01"

#     if shopify_keys.sync_customer:

#         # Default values
#         email = ""
#         phone = ""

#         # Get all linked addresses
#         address_links = frappe.get_all("Dynamic Link", filters={
#             "link_doctype": "Customer",
#             "link_name": doc.customer_name,
#             "parenttype": "Address"
#         }, fields=["parent"])

#         if not address_links:
#             address_links = frappe.get_all("Dynamic Link", filters={
#             "link_doctype": "Customer",
#             "link_name": doc.name,
#             "parenttype": "Address"
#         }, fields=["parent"])
        

#         address_list = []
#         if address_links:
#             # Use the first address to populate email/phone
#             primary_address = frappe.get_doc("Address", address_links[0]["parent"])
#             email = primary_address.email_id or ""
#             phone = primary_address.phone or ""
#             for link in address_links:
#                 address = frappe.get_doc("Address", link["parent"])
#                 address_list.append({
#                     "address1": address.address_line1,
#                     "address2": address.address_line2 or "",
#                     "city": address.city,
#                     "province": address.state,
#                     "country": address.country,
#                     "zip": address.pincode,
#                     "phone": address.phone,
#                     "email": address.email_id
#                 })
#         if not address_links:
#             primary_address = frappe.get_doc("Address", doc.customer_primary_address)
#             print("2",primary_address)
#             email = primary_address.email_id or ""
#             phone = primary_address.phone or ""
#             address_list.append({
#             "address1": primary_address.address_line1,
#             "address2": primary_address.address_line2 or "",
#             "city": primary_address.city,
#             "province": primary_address.state,
#             "country": primary_address.country,
#             "zip": primary_address.pincode,
#             "phone": primary_address.phone,
#             "email": primary_address.email_id
#             })

#         # Build the Shopify customer payload
#         customer_payload = {
#             "customer": {
#                 "first_name": doc.customer_name or "",
#                 "email": email,
#                 "phone": phone,
#                 "addresses": address_list
#             }
#         }

#         try:
#             # Update or Create based on existing shopify_customer_id
#             if doc.shopify_customer_id:
#                 customer_payload["customer"]["id"] = doc.shopify_customer_id
#                 url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{doc.shopify_customer_id}.json"
#                 response = requests.put(url, json=customer_payload, verify=False)
#                 print(url)
#             else:
#                 url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"
#                 response = requests.post(url, json=customer_payload, verify=False)

#             # Log response and save Shopify ID
#             if response.status_code not in (200, 201):
#                 frappe.log_error(f"Shopify customer sync failed: {response.text}", "Shopify Sync Error")
#             else:
#                 shopify_id = response.json()["customer"]["id"]
#                 doc.flags.from_shopify = True
#                 frappe.db.set_value("Customer", doc.customer_name, "shopify_customer_id", shopify_id)

#         except Exception as e:
#             frappe.log_error(f"Exception during Shopify customer sync: {str(e)}", "Shopify Sync Error")



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
            print(address_list)


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
                print(customer_payload)
                url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}.json"
                response = requests.put(url, json=customer_payload, verify=False)
                print(response.text)
                print("Updating customer:", url)
            else:
                url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"
                response = requests.post(url, json=customer_payload, verify=False)
                print("Creating new customer:", url)

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