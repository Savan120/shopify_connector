import frappe
import requests

from frappe.utils.background_jobs import enqueue

def enqueue_send_customer_to_shopify(doc, method):
    if not getattr(doc.flags, "from_shopify", False):
        enqueue("shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_customer_to_shopify_hook_delayed", queue="default", timeout=300, doc=doc, enqueue_after_commit=True)

def send_customer_to_shopify_hook_delayed(doc,method):
    send_customer_to_shopify_hook(doc, "after_insert")
    
def send_customer_to_shopify_hook(doc, method):
    if doc.flags.from_shopify:
        return

    if doc.get("custom_ignore_address_update"):
        doc.custom_ignore_address_update = False
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
            "phone": doc.phone
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
        url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}/addresses.json"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        addresses = response.json().get("addresses", [])
        shopify_address_id = addresses[0]["id"] if addresses else None
        frappe.db.set_value("Address", doc.name, "shopify_id", shopify_address_id)
    
    else :
        frappe.log_error(f"Shopify address ID not found for address '{doc.name}'. Cannot update.", "Shopify Sync Error")
        return

    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers/{shopify_customer_id}/addresses/{shopify_address_id}.json"
    
    response = requests.put(url, headers=headers, json=address_payload)
    response.raise_for_status()

    updated_data = response.json()
    frappe.msgprint(f"Shopify address updated successfully: {updated_data['customer_address']['id']}")
    
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




def get_current_domain_name() -> str:
    if hasattr(frappe.local, 'request') and frappe.local.request:
        return frappe.local.request.host
    else:
        if frappe.conf.developer_mode and frappe.conf.localtunnel_url:
            return frappe.conf.localtunnel_url
        elif frappe.conf.get('host_name'):
            return frappe.conf.get('host_name')
        else:
            return "localhost"

def send_item_to_shopify(doc, method):
    if doc.flags.from_shopify:
        return
    
    if doc.custom_ignore_product_update:
        doc.db_set("custom_ignore_product_update", 0)
        return
    
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    if not shopify_keys.sync_product:
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

    if not parent_doc_for_payload:
        frappe.log_error(f"No parent or template item found to sync for {doc.name}", "Shopify Sync Error")
        return

    if not parent_doc_for_payload.custom_send_to_shopify:
        return

    site_url = get_current_domain_name()
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = "2025-04"

    product_shopify_id_to_update = parent_doc_for_payload.shopify_id

    image_url = ""
    if parent_doc_for_payload.image:
        if not site_url.startswith("http"):
            site_url = "https://" + site_url
        image_url = site_url + parent_doc_for_payload.image

    product_payload = {
        "product": {
            "title": parent_doc_for_payload.item_name,
            "body_html": f"<strong>{parent_doc_for_payload.description or ''}</strong>",
            "vendor": parent_doc_for_payload.brand or "Default Vendor",
            "product_type": parent_doc_for_payload.item_group or "",
            "sku": parent_doc_for_payload.item_code if not parent_doc_for_payload.has_variants else None,
            "variants": [],
            "images": [],
            "options": [],
        }
    }

    if image_url:
        product_payload["product"]["images"].append({"src": image_url})

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
        images_to_send_to_shopify = []
        position_counter = 1

        for variant_frappe in all_variant_items_from_frappe:
            if not variant_frappe.get("custom_send_to_shopify"):
                continue

            variant_doc = frappe.get_doc("Item", variant_frappe["name"])

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
            variant_data = {
                "option1": values[0],
                "option2": values[1],
                "option3": values[2],
                "price": variant_doc.shopify_selling_rate or 0.0,
                "sku": variant_doc.item_code,
                "inventory_policy": "deny",
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

            if variant_doc.image and variant_doc.custom_variant_id:
                variant_image_url = site_url + variant_doc.image
                if {"src": variant_image_url} not in images_to_send_to_shopify and {"src": variant_image_url} not in product_payload["product"]["images"]:
                    images_to_send_to_shopify.append({"src": variant_image_url, "variant_ids": [variant_doc.custom_variant_id]})

        product_payload["product"]["images"].extend(images_to_send_to_shopify)
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
                "images": [],
            }
        }
        variant_data = {
            "price": item_triggering_sync.shopify_selling_rate or 0.0,
            "sku": item_triggering_sync.item_code,
            "inventory_policy": "deny",
            "taxable": True,
        }
        if item_triggering_sync.custom_variant_id:
            variant_data["id"] = item_triggering_sync.custom_variant_id

        product_payload["product"]["variants"].append(variant_data)

        if image_url:
            product_payload["product"]["images"].append({"src": image_url})

    if parent_doc_for_payload.has_variants and not product_payload["product"]["variants"]:
        return

    hsn_code = parent_doc_for_payload.gst_hsn_code or ""    
    product_payload["product"]["metafields"] = [
        {
            "namespace": "custom",
            "key": "hsn",
            "value": int(hsn_code),
        }
    ]

    if product_shopify_id_to_update:
        url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{product_shopify_id_to_update}.json"
        response = requests.put(url, json=product_payload, verify=False)
    else:
        url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json"
        response = requests.post(url, json=product_payload, verify=False)
        

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
        doc.flags.from_shopify = True
        frappe.db.commit()
    else:
        frappe.log_error(f"Failed to sync product {parent_doc_for_payload.name} to Shopify: Status {response.status_code} - {response.text}", "Shopify Sync Error")




###################################################################################################



def shopify_credentials():
    doc=frappe.get_single("Shopify Connector Setting")
    access_token = doc.access_token
    url=doc.shop_url
    version = doc.shopify_api_version
    shopify_graph_url = f"https://{url}/admin/api/{version}/graphql.json"
    return {"access_token":access_token,
            "shopify_graph_url":shopify_graph_url}


def create_shopify_draft_order(doc, method):
   
    shopify = frappe.get_single("Shopify Connector Setting")
    if not shopify.enable_shopify:
        return

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": shopify_credentials().get("access_token")
    }

    add= frappe.db.get_all("Dynamic Link", filters={"link_doctype": "Customer", "parenttype": "Address","link_name":doc.customer}, fields=["parent"])
    address = frappe.get_doc("Address",add[0].parent)

    customer = frappe.get_doc("Customer", doc.customer)
    shopify_customer_id = customer.shopify_id
    if not shopify_customer_id:
        frappe.throw("Customer does not have a linked Shopify ID.")
    contact= frappe.db.get_all("Dynamic Link", filters={"link_doctype": "Customer", "parenttype": "Contact","link_name":doc.customer}, fields=["parent"])
    
    customer_email = frappe.db.get_value("Contact", contact[0].parent, "email_id") if contact else None


    line_items = []
    for item in doc.items:
        line_item = {}

        items = frappe.get_doc("Item", item)

        if items.custom_variant_id:
            line_item["variantId"] = f"gid://shopify/ProductVariant/{items.custom_variant_id}"
        else:
            line_item["title"] = item.item_name
            line_item["originalUnitPrice"] = float(item.rate)

        line_item["quantity"] = int(item.qty)

        if item.discount_amount:
            line_item["appliedDiscount"] = {
                "description": "Line item discount",
                "value": float(item.discount_percentage or 0),
                "amount": float(item.discount_amount),
                "valueType": "FIXED_AMOUNT",
                "title": "Item Discount"
            }

        line_items.append(line_item)

   
    shipping_address = {
        "address1": address.address_line1,
        "address2": address.address_line2 or "",
        "city": address.city ,
        "province": address.state,
        "country": address.country,
        "zip": address.pincode
    }

    billing_address = {
        "address1": address.address_line1 or "",
        "address2": address.address_line2 or "",
        "city": address.city ,
        "province": address.state,
        "country": address.country,
        "zip": address.pincode
    }

    applied_discount = None
    if doc.discount_amount or doc.additional_discount_percentage:
        applied_discount = {
            "description": "Order Discount",
            "value": float(doc.additional_discount_percentage or 0),
            "amount": float(doc.discount_amount or 0),
            "valueType": "PERCENTAGE" if doc.additional_discount_percentage else "FIXED_AMOUNT",
            "title": "ERP Discount"
        }

  
    query = """
    mutation draftOrderCreate($input: DraftOrderInput!) {
      draftOrderCreate(input: $input) {
        draftOrder {
          id
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "customerId": f"gid://shopify/Customer/{shopify_customer_id}",
            "note": doc.po_no or "ERPNext Draft Order",
            "email": customer_email,
            "tags": [doc.status],
            "taxExempt": False,
            "shippingLine": {
                "title": "Standard Shipping",
                "price": float(0)
            },
            "shippingAddress": shipping_address,
            "billingAddress": billing_address,
            "lineItems": line_items
        }
    }

    if applied_discount:
        variables["input"]["appliedDiscount"] = applied_discount

    response = requests.post(
        shopify_credentials().get("shopify_graph_url"),
        headers=headers,
        json={"query": query, "variables": variables}
    )

    if response.status_code != 200 or "errors" in response.json():
        frappe.log_error("Shopify Draft Order Creation Failed", response.text)
        return
    abc=response.json().get("data", {})
    draft_order = response.json().get("data", {}).get("draftOrderCreate", {}).get("draftOrder")
    if draft_order and draft_order.get("id"):
        doc.custom_shopify_draft_order_id = draft_order["id"].split("/")[-1]
        doc.flags.from_shopify = True
        doc.save(ignore_permissions=True)
        frappe.msgprint("Shopify draft order created successfully.")
    else:
        frappe.log_error(" Shopify Draft Order missing ID", response.text)
        
        
        
        
# import pycountry
# import unicodedata

# def clean_name(name):
#     return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8').lower().strip()

# def get_country_code(country_name):
#     name_clean = clean_name(country_name)
    
#     for country in pycountry.countries:
#         if clean_name(country.name) == name_clean:
#             return country.alpha_2
#     return None


# def get_country_and_state_codes(country_name, state_name):
#     country_code = get_country_code(country_name)
#     if not country_code:
#         return None, None

#     state_clean = clean_name(state_name)

#     for subdiv in pycountry.subdivisions.get(country_code=country_code):
#         if state_clean in clean_name(subdiv.name):
#             state_code = subdiv.code.split('-')[-1]  
#             return country_code, state_code
#     else:
#         return frappe.throw(f"{state_name} not found in {country_name}")
