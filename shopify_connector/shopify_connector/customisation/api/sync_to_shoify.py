import frappe
import requests
from frappe import _
import json
from frappe.utils.background_jobs import enqueue
from shopify_connector.controllers.scheduling import need_to_run
from shopify_connector.constants import SETTING_DOCTYPE


def validate_api_path():
    url = frappe.request.url
    path = url.split("//")[1].split("/")[-1] if "//" in url else url.split("/", 1)[-1]
    endpoint_key = path.split("/")[0] if path else ""
    if endpoint_key != "frappe.desk.form.save.savedocs":
        return False
    return True


    
#! >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>send_customer_to_shopify_hook>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>.
def send_customer_to_shopify_hook(doc, method):
    from_desk = validate_api_path()
    if not from_desk:
        return
    
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    if not shopify_keys.sync_customer:
        return

    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    email = doc.email_id or ""
    phone = doc.mobile_no or ""
    
    contact_name = None

    linked_contacts = frappe.db.get_value("Dynamic Link",{"link_doctype": "Customer","link_name": doc.name,"parenttype": "Contact" }, "parent", order_by="creation asc") 

    if linked_contacts:
        try:
            contact_doc_name = linked_contacts
            contact_doc = frappe.get_doc("Contact", contact_doc_name)
            
            contact_name = contact_doc.name 
            
            if contact_doc.email_id:
                email = contact_doc.email_id
            if contact_doc.phone:
                phone = contact_doc.phone
                
        except Exception as e:
            frappe.log_error(f"Error fetching linked contact '{contact_doc_name}' for customer {doc.name}: {str(e)}", "Shopify Sync Error")


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

    existing_shopify_addresses = {}
    shopify_customer_id = doc.shopify_id or frappe.db.get_value("Customer", doc.name, "shopify_id")
    if shopify_customer_id:
        try:
            headers = {
                "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            }
            url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}/addresses.json"
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                for addr in response.json().get("addresses", []):
                    key = f"{addr.get('address1', '')}-{addr.get('city', '')}-{addr.get('country', '')}".lower()
                    existing_shopify_addresses[key] = addr.get("id")
        except Exception as e:
            frappe.log_error(f"Could not fetch existing Shopify addresses for customer {doc.name}: {str(e)}")

    def create_address_payload(address_doc):
        payload = {
            "address1": address_doc.address_line1,
            "address2": address_doc.address_line2 or "",
            "city": address_doc.city,
            "province": address_doc.state or address_doc.custom_state or "",
            "country": address_doc.country,
            "zip": address_doc.pincode,
            "phone": address_doc.phone,
            "email": address_doc.email_id
        }
        if address_doc.shopify_id:
            payload["id"] = address_doc.shopify_id
        else:
            key = f"{address_doc.address_line1 or ''}-{address_doc.city or ''}-{address_doc.country or ''}".lower()
            if key in existing_shopify_addresses:
                payload["id"] = existing_shopify_addresses[key]

        return payload

    if address_links:
        for link in address_links:
            address = frappe.get_doc("Address", link["parent"])
            address_list.append(create_address_payload(address))
    elif doc.get("customer_primary_address"):
        primary_address = frappe.get_doc("Address", doc.customer_primary_address)
        address_list.append(create_address_payload(primary_address))

    customer_payload = {
        "customer": {
            "first_name": doc.customer_name or "",
            "last_name": "",
            "email": email,
            "phone": phone,
            "addresses": address_list or [],
            "tags": doc.customer_group or ""
        }
    }

    frappe.log_error(title="Customer Payload", message=f"{customer_payload}")
    try:
        headers = {
            "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
            "Content-Type": "application/json"
        }

        shopify_customer_id = doc.shopify_id or frappe.db.get_value("Customer", doc.name, "shopify_id")

        if shopify_customer_id:
            customer_payload["customer"]["id"] = shopify_customer_id
            url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}.json"
            response = requests.put(url, json=customer_payload, headers=headers, timeout=30)
        else:
            url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"
            response = requests.post(url, json=customer_payload, headers=headers, timeout=30)

        if response.status_code not in (200, 201):
            frappe.log_error(f"Shopify customer sync failed: {response.text}", "Shopify Sync Error")
            return

        shopify_customer = response.json().get("customer", {})
        shopify_id = shopify_customer.get("id")
        shopify_email = shopify_customer.get("email")
        
        doc.flags.from_shopify = True
        doc.db_set("shopify_id", shopify_id)
        if contact_name:
            doc.db_set("customer_primary_contact", contact_name)
        doc.db_set("shopify_email", shopify_email)
    except Exception as e:
        frappe.log_error(f"Exception during Shopify customer sync: {str(e)}", "Shopify Sync Error")

#!>>>>>>>>>>>>>>>>>>on_address_update>>>>>>>>>>>>>>>>>>>>


def on_address_update(doc, method):
    address_payload = {
        "address": {
            "first_name": doc.address_title,
            "address1": doc.address_line1,
            "address2": doc.address_line2 or "",
            "city": doc.city,
            "province": doc.state or doc.custom_state or "",
            "country": doc.country,
            "zip": doc.pincode,
            "phone": doc.phone or ""
        }
    }

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    if not shopify_keys.sync_customer:
        return

    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }

    shopify_customer_id = frappe.db.get_value("Customer", {"customer_primary_address": doc.name}, "shopify_id")
    if not shopify_customer_id:
        for row in doc.links:
            if row.link_doctype == "Customer":
                shopify_customer_id = frappe.db.get_value("Customer", row.link_name, "shopify_id")
                if shopify_customer_id:
                    break

    if not shopify_customer_id:
        frappe.log_error("Shopify customer ID not found for address update.", "Shopify Sync Error")
        return

    shopify_address_id = frappe.db.get_value("Address", doc.name, "shopify_id")

    if not shopify_address_id:
        url_get_addresses = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}/addresses.json"
        try:
            response_get = requests.get(url_get_addresses, headers=headers)

            response_get.raise_for_status()
            addresses_on_shopify = response_get.json().get("addresses", [])

            found_address_id = None
            for shopify_addr in addresses_on_shopify:
                if (shopify_addr.get("address1") == doc.address_line1 and shopify_addr.get("city") == doc.city and shopify_addr.get("zip") == doc.pincode):
                    found_address_id = shopify_addr.get("id")
                    break
            

            if found_address_id:
                shopify_address_id = found_address_id
                frappe.db.set_value("Address", doc.name, "shopify_id", shopify_address_id)
            else:
                frappe.log_error(f"Matching Shopify address not found for local address '{doc.name}'. Cannot update.", "Shopify Sync Error")
                return
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Error fetching Shopify addresses for customer {shopify_customer_id}: {e}", "Shopify Sync Error")
            return
    else:
        pass


    if shopify_address_id:
        url_update_address = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}/addresses/{shopify_address_id}.json"

        try:
            response = requests.put(url_update_address, headers=headers, json=address_payload)
            response.raise_for_status() 

            updated_data = response.json()
        except requests.exceptions.HTTPError as e:
            error_message = e.response.json()
            frappe.log_error(f"Shopify address update failed for address '{doc.name}' (Shopify ID: {shopify_address_id}): {error_message}, {updated_data}", "Shopify Sync Error")
        except requests.exceptions.RequestException as e:
            frappe.log_error(f"Network or connection error updating Shopify address for '{doc.name}': {e}", "Shopify Sync Error")
    else:
        frappe.log_error(f"Shopify address ID is missing after all attempts for address '{doc.name}'. Update aborted.", "Shopify Sync Error")
    
    
#!>>>>>>>>>>>>>>>>>>>>>>>>>>send_contact_to_shopify>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def send_contact_to_shopify(doc, method):
    data = {
        "customer": {
            "email": doc.email_id,
            "phone": doc.phone,
            "verified_email": True,
        }
    }
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    if not shopify_keys.sync_customer:
        return

    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    shopify_customer_id = frappe.db.get_value("Customer", {"customer_primary_contact": doc.name}, "shopify_id")
    if not shopify_customer_id:
        for row in doc.links:
            if row.link_doctype == "Customer":
                shopify_customer_id = frappe.db.get_value("Customer", row.link_name, "shopify_id")

    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}.json"
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }

    response = requests.put(url, json=data, headers=headers)
    if response.status_code not in (200, 201):
        frappe.log_error(f"Shopify customer sync failed: {response.text}", "Shopify Sync Error")



#!>>>>>>>>>>>>>>>>>>>>>>>>delete_customer_from_shopify>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

def delete_customer_from_shopify(doc, method):
    if not doc.shopify_id:
        return

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{doc.shopify_id}.json"

    response = requests.delete(url, verify=False)

    if response.status_code != 200:
        frappe.log_error(f"Failed to delete customer from Shopify: {response.text}", "Shopify Customer Delete Error")


#!>>>>>>>>>>>>>>>>>>>>>>>>>To Get Current Host URLs>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    
# def get_current_domain_name() -> str:
#     if hasattr(frappe.local, 'request') and frappe.local.request:
#         return frappe.local.request.host
#     else:
#         if frappe.conf.developer_mode and frappe.conf.localtunnel_url:
#             return frappe.conf.localtunnel_url
#         elif frappe.conf.get('host_name'):
#             return frappe.conf.get('host_name')
#         else:
#             return "localhost"


#!>>>>>>>>>>>>>>>>>>>>>>>>>>>>send_item_to_shopify>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
def send_item_to_shopify(doc, method):
    from_desk = validate_api_path()
    if not from_desk:
        return

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    if not shopify_keys.sync_product and not doc.custom_send_to_shopify:
        return

    item_triggering_sync = frappe.get_doc("Item", doc.name)

    frappe_template_item_name = None
    parent_doc_for_payload = None

    if item_triggering_sync.variant_of:
        frappe_template_item_name = item_triggering_sync.variant_of
        parent_doc_for_payload = frappe.get_doc("Item", frappe_template_item_name)
    elif item_triggering_sync.has_variants:
        frappe_template_item_name = item_triggering_sync.name
        parent_doc_for_payload = item_triggering_sync
    else:
        parent_doc_for_payload = item_triggering_sync

    if not parent_doc_for_payload or not parent_doc_for_payload.custom_send_to_shopify:
        return

    # site_url = get_current_domain_name()
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    product_shopify_id_to_update = parent_doc_for_payload.shopify_id
    inventory_policy = (
        "continue" if parent_doc_for_payload.custom_continue_selling_when_out_of_stock else "deny"
    )

    # image_url = ""
    # if parent_doc_for_payload.image:
    #     if not site_url.startswith("http"):
    #         site_url = "https://" + site_url
    #     image_url = site_url + parent_doc_for_payload.image
    # elif parent_doc_for_payload.has_variants or parent_doc_for_payload.name != item_triggering_sync.name:
    #     variants = frappe.get_all("Item", filters={"variant_of": parent_doc_for_payload.name}, fields=["image"])
    #     for variant in variants:
    #         if variant.image:
    #             image_url = site_url + variant.image if not variant.image.startswith("http") else variant.image
    #             break

    product_payload = {
        "product": {
            "title": parent_doc_for_payload.item_name,
            "body_html": f"<strong>{parent_doc_for_payload.description or ''}</strong>",
            "vendor": parent_doc_for_payload.brand or "Default Vendor",
            "product_type": parent_doc_for_payload.item_group or "",
            "inventory_policy": inventory_policy,
            "sku": parent_doc_for_payload.item_code if not parent_doc_for_payload.has_variants else None,
            "variants": [],
            # "images": [],
            "options": [],
        }
    }

    # if image_url:
    #     product_payload["product"]["images"].append({"src": image_url})

    if frappe_template_item_name:
        all_variant_items_from_frappe = frappe.get_all(
            "Item",
            filters={"variant_of": frappe_template_item_name},
            fields=["name", "item_code", "shopify_selling_rate", "image", "custom_variant_id", "custom_send_to_shopify"]
        )

        template_attributes = frappe.get_all(
            "Item Variant Attribute",
            filters={"parent": frappe_template_item_name},
            fields=["attribute"],
            order_by="idx asc"
        )
        attribute_order = [attr["attribute"] for attr in template_attributes]
        option_map = {attr: set() for attr in attribute_order}

        existing_shopify_product = None
        if product_shopify_id_to_update:
            get_product_url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{product_shopify_id_to_update}.json"
            try:
                get_response = requests.get(get_product_url, verify=False)
                if get_response.status_code == 200:
                    existing_shopify_product = get_response.json()["product"]
                else:
                    frappe.log_error(f"Failed to fetch existing Shopify product {product_shopify_id_to_update}: Status {get_response.status_code} - {get_response.text}", "Shopify Sync Error")
            except requests.exceptions.RequestException as e:
                frappe.log_error(f"Failed to fetch existing Shopify product {product_shopify_id_to_update}: {e}", "Shopify Sync Error")

        existing_shopify_variants_map = {}
        if existing_shopify_product and "variants" in existing_shopify_product:
            for sv in existing_shopify_product["variants"]:
                existing_shopify_variants_map[sv["sku"]] = sv

        variants_to_send_to_shopify = []
        # images_to_send_to_shopify = []
        position_counter = 1

        for variant_frappe in all_variant_items_from_frappe:
            if not variant_frappe.get("custom_send_to_shopify"):
                continue

            variant_doc = frappe.get_doc("Item", variant_frappe["name"])

            # variant_ids = set()

            # variants = frappe.get_all(
            #     "Item",
            #     filters={
            #         "variant_of": variant_doc.variant_of,
            #         "image": ["!=", ""]
            #     },
            #     fields=["custom_variant_id"]
            # )

            # for variant in variants:
            #     if variant.custom_variant_id:
            #         variant_ids.add(variant.custom_variant_id)

            # variant_ids = list(variant_ids)

            attributes = frappe.get_all(
                "Item Variant Attribute",
                filters={"parent": variant_doc.name},
                fields=["attribute", "attribute_value"]
            )
            attr_dict = {attr.attribute: attr.attribute_value for attr in attributes}

            for attr in attribute_order:
                if attr in attr_dict:
                    option_map[attr].add(attr_dict[attr])

            values = [attr_dict.get(attr) for attr in attribute_order]
            values += [None] * (3 - len(values))
            variant_inventory_policy = "continue" if variant_doc.custom_continue_selling_when_out_of_stock else "deny"
            variant_data = {
                "option1": values[0],
                "option2": values[1],
                "option3": values[2],
                "price": variant_doc.shopify_selling_rate or 0.0,
                "sku": variant_doc.item_code,
                "inventory_policy": variant_inventory_policy,
                "taxable": True,
                "position": position_counter,
            }
            position_counter += 1

            if variant_frappe.get("custom_variant_id"):
                variant_data["id"] = variant_frappe["custom_variant_id"]
            elif variant_frappe["item_code"] in existing_shopify_variants_map:
                variant_data["id"] = existing_shopify_variants_map[variant_frappe["item_code"]]["id"]
                frappe.db.set_value("Item", variant_frappe["name"], "custom_variant_id", variant_data["id"])

            variants_to_send_to_shopify.append(variant_data)

            # if variant_doc.image and variant_doc.custom_variant_id:
            #     if variant_doc.image.startswith("https://"):
            #         variant_image_url = variant_doc.image
            #     else:
            #         variant_image_url = site_url + variant_doc.image

            #     image_payload = {
            #         "src": variant_image_url,
            #         "variant_ids": [variant_doc.custom_variant_id]
            #     }

            #     existing_srcs = [img.get("src") for img in images_to_send_to_shopify]
            #     existing_payload_srcs = [img.get("src") for img in product_payload["product"].get("images", [])]
            #     if variant_image_url not in existing_srcs and variant_image_url not in existing_payload_srcs:
            #         images_to_send_to_shopify.append(image_payload)

        # product_payload["product"]["images"].extend(images_to_send_to_shopify)
        product_payload["product"]["variants"] = variants_to_send_to_shopify

        for attr in attribute_order:
            if option_map[attr]:
                product_payload["product"]["options"].append({
                    "name": attr,
                    "values": list(option_map[attr])
                })
            elif product_shopify_id_to_update and existing_shopify_product and "options" in existing_shopify_product:
                for existing_option in existing_shopify_product["options"]:
                    if existing_option["name"] == attr:
                        if existing_option.get("values"):
                            product_payload["product"]["options"].append(existing_option)
                        else:
                            product_payload["product"]["options"].append({"name": existing_option["name"], "values": []})

    elif not item_triggering_sync.has_variants:
        if not item_triggering_sync.custom_send_to_shopify:
            return

        product_payload = {
            "product": {
                "title": item_triggering_sync.item_name,
                "body_html": f"<strong>{item_triggering_sync.description or ''}</strong>",
                "vendor": item_triggering_sync.brand or "Default Vendor",
                "product_type": item_triggering_sync.item_group or "",
                "sku": item_triggering_sync.item_code,
                "variants": [],
                # "images": [],
            }
        }
        variant_data = {
            "price": item_triggering_sync.shopify_selling_rate or 0.0,
            "inventory_policy": inventory_policy,
            "sku": item_triggering_sync.item_code,
            "taxable": True,
        }
        if item_triggering_sync.custom_variant_id:
            variant_data["id"] = item_triggering_sync.custom_variant_id

        product_payload["product"]["variants"].append(variant_data)

        # if image_url:
        #     product_payload["product"]["images"].append({"src": image_url})

    if parent_doc_for_payload.has_variants and not product_payload["product"]["variants"]:
        return

    hsn_code = parent_doc_for_payload.gst_hsn_code or ""
    stock_uom = parent_doc_for_payload.stock_uom or ""
    product_payload["product"]["metafields"] = [
        {
            "namespace": "custom",
            "key": "hsn",
            "value": str([int(hsn_code)]),
            # "value": int(hsn_code),           #* Use this when you are trying in your develop shopify app
            # "type": "number_integer"          #* Use this when you are trying in your develop shopify app
            "type": "list.number_integer"
        },
        {
            "namespace": "custom",
            "key": "default_unit_of_measure",
            "value": stock_uom,
            "type": "single_line_text_field"
        }
    ]

    if product_shopify_id_to_update:
        url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{product_shopify_id_to_update}.json"
        response = requests.put(url, json=product_payload, verify=False)
    else:
        url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json"
        response = requests.post(url, json=product_payload, verify=False)

    print(response.json())

    if response.status_code in [200, 201]:
        shopify_product = response.json()["product"]
        if frappe_template_item_name:
            frappe.db.set_value("Item", frappe_template_item_name, "shopify_id", shopify_product["id"])
            frappe.db.set_value("Item", frappe_template_item_name, "custom_send_to_shopify", 1)
        else:
            frappe.db.set_value("Item", item_triggering_sync.name, "shopify_id", shopify_product["id"])
            frappe.db.set_value("Item", item_triggering_sync.name, "custom_send_to_shopify", 1)

        sent_skus = {v["sku"] for v in product_payload["product"]["variants"]}

        for variant in shopify_product.get("variants", []):
            sku = variant.get("sku")
            variant_id = variant.get("id")
            inventory_item_id = variant.get("inventory_item_id")

            if sku in sent_skus and variant_id:
                frappe_variant_item_name = frappe.db.get_value("Item", {"item_code": sku}, "name")
                if frappe_variant_item_name:
                    try:
                        frappe.db.set_value("Item", frappe_variant_item_name, {
                            "custom_variant_id": variant_id,
                            "custom_inventory_item_id": inventory_item_id,
                            "custom_send_to_shopify": 1
                        })
                    except Exception as e:
                        frappe.log_error(f"Failed to set variant/inventory ID for SKU {sku} (Frappe item: {frappe_variant_item_name}): {str(e)}", "Shopify Sync")
    else:
        frappe.log_error(title=f"Failed to sync product {parent_doc_for_payload.name} to Shopify", message=f"Status {response.status_code} - {response.text}")
        return


#!##################################################################################################


def update_inventory_on_shopify() -> None:
    """Upload stock levels from ERPNext to Shopify. Called by scheduler."""
    
    setting = frappe.get_doc(SETTING_DOCTYPE)

    if not setting.update_erpnext_stock_levels_to_shopify:
        return

    if not need_to_run(SETTING_DOCTYPE, "inventory_sync_frequency", "last_inventory_sync"):
        return

    bins = frappe.get_all("Bin", filters={
        "modified": [">", setting.last_inventory_sync]
    }, fields=["name"])
    
    for bin_data in bins:
        try:
            bin_doc = frappe.get_doc("Bin", bin_data.name)
            enqueue(
                method="shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_inventory_to_shopify",
                queue="long",
                job_name="Sync Inventory to Shopify",
                kwargs={"doc": bin_doc}
            )
            send_inventory_to_shopify(bin_doc)
        except Exception as e:
            frappe.log_error(f"Error syncing bin {bin_doc.name}: {str(e)}", "Shopify Inventory Sync")


def send_inventory_to_shopify(bin_doc=None, **kwargs):
        
    connector_settings = frappe.get_single(SETTING_DOCTYPE)

    item_code = bin_doc.item_code
    warehouse = bin_doc.warehouse
    actual_qty = bin_doc.actual_qty
    reserved_qty = bin_doc.reserved_qty

    available_qty = actual_qty - reserved_qty
    if available_qty < 0:
        available_qty = 0  

    item = frappe.get_doc("Item", {"item_code": item_code})

    inventory_item_id = item.get("custom_inventory_item_id")

    if not inventory_item_id:
        frappe.log_error(title= "No inventory_item_id found. Exiting...", message=f"{item}")
        return

    warehouse_setting = connector_settings.get("warehouse_setting", [])

    shopify_location_id = None
    for row in warehouse_setting:
        if (row.erpnext_warehouse or '').strip() == (warehouse or '').strip():
            shopify_location_id = row.shopify_id
            break

    if not shopify_location_id:
        frappe.log_error(f"Shopify Location ID not found for warehouse {warehouse}", "Shopify Inventory Sync")
        return

    api_key = connector_settings.api_key
    access_token = connector_settings.access_token
    shop_url = connector_settings.shop_url
    api_version = connector_settings.shopify_api_version
    
    url = f"https://{api_key}:{access_token}@{shop_url}/admin/api/{api_version}/inventory_items/{inventory_item_id}.json"

    payload = {
        "inventory_item": {
            "id": inventory_item_id,
            "tracked": True
        }
    }

    response = requests.put(url, json=payload, verify=False)


    url = f"https://{api_key}:{access_token}@{shop_url}/admin/api/{api_version}/inventory_levels/set.json"
    payload = {
        "location_id": shopify_location_id,
        "inventory_item_id": inventory_item_id,
        "available": int(available_qty)
    }

    try:
        response = requests.post(url, json=payload, verify=False)
        if response.status_code not in [200, 201]:
            frappe.log_error(title=f"Shopify inventory update failed:",message= {response.status_code} - {response.text})
        else:
            frappe.log_error(title="Shopify inventory update successful.", message=f"{response.json()}")

    except Exception as e:
        frappe.log_error(str(e), "Shopify Inventory Sync")
        
        

def item_on_update_sync_inventory(doc, method=None):
    bins = frappe.get_all("Bin", filters={"item_code": doc.item_code}, fields=["name"])
    frappe.log_error(title="Total Bin", message=f"{bins}")
    if not bins:
        frappe.log_error(title="Send Invenotry to Shopify", message="Not Bin Record Fetch on Updated item")
        return
    for bin_row in bins:
        try:
            bin_doc = frappe.get_doc("Bin", bin_row.name)
            send_inventory_to_shopify(bin_doc)
        except Exception as e:
            frappe.log_error(f"Error syncing bin {bin_row.name}: {str(e)}", "Shopify Inventory Sync - Item Update")
