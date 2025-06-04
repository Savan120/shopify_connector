import frappe
import requests

from frappe.utils.background_jobs import enqueue

def enqueue_send_customer_to_shopify(doc, method):
    if not getattr(doc.flags, "from_shopify", False):
        enqueue("shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_customer_to_shopify_hook_delayed", queue="default", timeout=300, doc=doc, enqueue_after_commit=True)

def send_customer_to_shopify_hook_delayed(doc):
    send_customer_to_shopify_hook(doc, "after_insert") 

def send_customer_to_shopify_hook(doc, method):
    if getattr(doc.flags, "from_shopify", True):
        return

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

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
        
        if phone == "":
            phone = doc.mobile_no
        
        if email == "":
            email = doc.email_id

        customer_payload = {
            "customer": {
                "first_name": doc.customer_name or "",
                "email": email,
                "phone": phone,
                "addresses": address_list or [],
                "tags":doc.customer_group or ""
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
                print(response.json())
                shopify_id = response.json()["customer"]["id"]
                shopify_email = response.json()["customer"]["email"]
                doc.flags.from_shopify = True
                doc.db_set("shopify_id",shopify_id)
                doc.db_set("shopify_email",shopify_email)

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
    if getattr(doc.flags, "from_shopify", True):
        return

    item = frappe.get_doc("Item", doc.name)
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

    product_shopify_id_to_update = None
    frappe_template_item_name = None

    if item.variant_of:
        frappe_template_item_name = frappe.get_value("Item", doc.name, "variant_of")
        product_shopify_id_to_update = frappe.get_value("Item", frappe_template_item_name, "shopify_id")
        parent_doc = frappe.get_doc("Item", frappe_template_item_name)
    elif item.has_variants:
        frappe_template_item_name = item.name
        product_shopify_id_to_update = item.shopify_id
        parent_doc = item
    else:
        product_shopify_id_to_update = item.shopify_id
        parent_doc = item 

    product_payload = {
        "product": {
            "title": parent_doc.item_name,
            "body_html": f"<strong>{parent_doc.description or ''}</strong>",
            "vendor": parent_doc.brand or "Default Vendor",
            "product_type": parent_doc.item_group or "",
            "sku": parent_doc.item_code if not parent_doc.has_variants else None,
            "variants": [],
            "images": [],
            "options": [],
        }
    }

    if image_url:
        product_payload["product"]["images"].append({"src": image_url})

    if frappe_template_item_name:
        variant_items_from_frappe = frappe.get_all(
            "Item",
            filters={"variant_of": frappe_template_item_name},
            fields=["name", "item_code", "shopify_selling_rate", "image", "custom_variant_id"]
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
            except requests.exceptions.RequestException as e:
                frappe.log_error(f"Failed to fetch existing Shopify product {product_shopify_id_to_update}: {e}", "Shopify Sync Error")

        existing_shopify_variants_map = {}
        if existing_shopify_product and "variants" in existing_shopify_product:
            for sv in existing_shopify_product["variants"]:
                existing_shopify_variants_map[sv["sku"]] = sv

        variants_to_send_to_shopify = []
        images_to_send_to_shopify = []

        for position, variant_frappe in enumerate(variant_items_from_frappe, start=1):
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
                "position": position,
            }

            if variant_frappe.get("custom_variant_id"):
                variant_data["id"] = variant_frappe["custom_variant_id"]
            elif variant_frappe["item_code"] in existing_shopify_variants_map:
                variant_data["id"] = existing_shopify_variants_map[variant_frappe["item_code"]]["id"]
                frappe.db.set_value("Item", variant_frappe["name"], "custom_variant_id", variant_data["id"])


            variants_to_send_to_shopify.append(variant_data)

            if variant_doc.image:
                variant_image_url = site_url + variant_doc.image
                if {"src": variant_image_url} not in images_to_send_to_shopify and {"src": variant_image_url} not in product_payload["product"]["images"]:
                    images_to_send_to_shopify.append({"src": variant_image_url})

        product_payload["product"]["images"].extend(images_to_send_to_shopify)
        product_payload["product"]["variants"] = variants_to_send_to_shopify

        for attr in attribute_order:
            product_payload["product"]["options"].append({
                "name": attr,
                "values": list(option_map[attr])
            })

    elif not item.has_variants:
        print("Simple product processing")
        product_payload = {
            "product": {
                "title": item.item_name,
                "body_html": f"<strong>{item.description or ''}</strong>",
                "vendor": item.brand or "Default Vendor",
                "product_type": item.item_group or "",
                "sku": item.item_code,
                "variants": [],
                "images": [],
            }
        }
        variant_data = {
            "price": item.shopify_selling_rate or 0.0,
            "sku": item.item_code,
            "inventory_policy": "deny",
            "taxable": True,
        }
        if item.custom_variant_id:
            variant_data["id"] = item.custom_variant_id

        product_payload["product"]["variants"].append(variant_data)

        if image_url:
            product_payload["product"]["images"].append({"src": image_url})


    if doc.custom_send_to_shopify:
        if product_shopify_id_to_update:
            url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products/{product_shopify_id_to_update}.json"
            response = requests.put(url, json=product_payload, verify=False)
            print("Updating existing product/variants")
            doc.flags.from_shopify = True
        else: 
            url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json"
            response = requests.post(url, json=product_payload, verify=False)
            print(response.json())
            print("Creating new product")

        if response.status_code == 201:
            shopify_product = response.json()["product"]
            frappe.db.set_value("Item", item.name, "shopify_id", shopify_product["id"])
            item.shopify_id = shopify_product["id"]

            for variant in shopify_product.get("variants", []):
                sku = variant.get("sku")
                variant_id = variant.get("id")
                inventory_item_id = variant.get("inventory_item_id")
                if variant_id:
                    try:
                        frappe.db.set_value("Item", {"item": item.name}, {
                            "shopify_variant_id": variant_id,
                            "custom_inventory_item_id": inventory_item_id
                        })
                        update_shopify_hsn_code(item.gst_hsn_code, inventory_item_id)
                        doc.flags.from_shopify = True
                    except Exception as e:
                        frappe.log_error(f"Failed to set variant/inventory ID for SKU {sku}: {str(e)}", "Shopify Sync")
                        doc.flags.from_shopify = True





def update_shopify_hsn_code(hsn_code, inventory_item_id):
    """Send harmonized system code (HSN) to Shopify for the given inventory item ID"""

    if not hsn_code or not inventory_item_id:
        return

    shopify_keys = frappe.get_single("Shopify Connector Setting")
    access_token = shopify_keys.access_token
    store_url = shopify_keys.shop_url
    api_version = "2024-01"

    url = f"https://{store_url}/admin/api/{api_version}/inventory_items/{inventory_item_id}.json"

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": access_token
    }

    payload = {
        "inventory_item": {
            "id": int(inventory_item_id),
            "harmonized_system_code": hsn_code,
            "country_code_of_origin": "IN"
        }
    }

    response = requests.put(url, json=payload, headers=headers)

    if response.status_code != 200:
        frappe.log_error(f"HSN update failed: {response.text}", "Shopify HSN Sync Error")
       
###################################################################################################


import pycountry
import unicodedata

def clean_name(name):
    return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('utf-8').lower().strip()

def get_country_code(country_name):
    name_clean = clean_name(country_name)
    
    for country in pycountry.countries:
        # print("\n\n\ncountry",country)
        if clean_name(country.name) == name_clean:
            return country.alpha_2
    return None


def get_country_and_state_codes(country_name, state_name):
    country_code = get_country_code(country_name)
    # print("\n\n\ncountry_code",country_code)
    if not country_code:
        return None, None

    state_clean = clean_name(state_name)

    for subdiv in pycountry.subdivisions.get(country_code=country_code):
        # print("\n\n\nsubdiv",subdiv)
        if state_clean in clean_name(subdiv.name):
            # print("\n\n\nstate_clean",state_clean)
            state_code = subdiv.code.split('-')[-1]  
            # print("\n\nstate_code",state_code)
            return country_code, state_code
    else:
        return frappe.throw(f"{state_name} not found in {country_name}")

    # return country_code, None 


def shopify_credentials():
    doc=frappe.get_single("Shopify Connector Setting")
    access_token = doc.access_token
    url=doc.shop_url
    version = doc.shopify_api_version
    shopify_graph_url = f"https://{url}/admin/api/{version}/graphql.json"
    return {"access_token":access_token,
            "shopify_graph_url":shopify_graph_url}


def create_shopify_location(doc, method):
    if doc.flags.ignore_shopify_sync:
        return
    
    if getattr(doc.flags, "from_shopify", False):
        return
    
    shopify = frappe.get_single("Shopify Connector Setting")

    if shopify.enable_shopify == False:
        return
    
    address = f"{doc.address_line_1} {doc.address_line_2 or ''}"
    country = "India"
    # city = doc.city or " "
    # province = doc.state or " "
    # postal_code = doc.pin or "000000"
    # phone = doc.phone_no or ""
    country_code,state_code=get_country_and_state_codes(doc.custom_country,doc.state)

    query = f"""
    mutation {{
        locationAdd(input: {{
            name: "{doc.name}",
            address: {{
                address1:"",
                address2: "{address}",
                city: "{doc.city}",
                provinceCode: "{state_code}",
                countryCode: {country_code},
                zip: "{doc.pin if doc.pin else '000000'}"
                phone: "{doc.phone_no if doc.phone_no else ''}"
            }},
            fulfillsOnlineOrders: true
        }}) {{
            location {{
                id
                name
                address {{
                    address1
                    provinceCode
                    countryCode
                    zip
                    phone
                }}
                fulfillsOnlineOrders
            }}
        }}
        
    }}
    """

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": shopify_credentials().get("access_token")
    }

    response = requests.post(shopify_credentials().get("shopify_graph_url"), json={"query": query}, headers=headers)

    if response.status_code != 200 or "errors" in response.json():
        frappe.log_error(f"Shopify location creation failed: {response.text}")
        return
    
    response_json = response.json()
    data = response_json.get("data")
    locationAdd = data.get("locationAdd") if data else None
    location = locationAdd.get("location") if locationAdd else None

    if not location:
        frappe.log_error("No location data")
        return

    location_get = location.get("id")
    if location_get:
        location_id = location_get.split("/")[-1]
        doc.custom_shopify_id = location_id
        doc.flags.from_shopify = True  
        doc.save(ignore_permissions=True)
        frappe.msgprint(f"Shopify location created for warehouse {doc.name}")
    else:
        frappe.log_error("Shopify location ID missing ")


def activate_deactivate_shopify_location(doc, method):
    if doc.flags.ignore_shopify_sync:
        return
    shopify_id = doc.custom_shopify_id
    if not shopify_id:
        frappe.log_error("Missing Shopify Location ID")
        return

    location_get= f"gid://shopify/Location/{shopify_id}"
    # status = bool(doc.disabled)    

    if doc.disabled:
        query = f"""
        mutation {{
            locationDeactivate(locationId: "{location_get}") {{
                location {{
                    id
                    isActive
                }}
                locationDeactivateUserErrors {{
                    message
                    code
                    field
                }}
            }}
        }}
        """
    else:
        query = f"""
        mutation {{
            locationActivate(locationId: "{location_get}") {{
                location {{
                    id
                    isActive
                }}
            }}
        }}
        """

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": shopify_credentials().get("access_token")
    }

    response = requests.post(shopify_credentials().get("shopify_graph_url"), json={"query": query}, headers=headers)

    if response.status_code != 200:
        frappe.log_error(f"Shopify request failed: {response.text}", "Shopify Sync Error")
        return
    else:
        status_msg = "deactivated" if doc.disabled else "activated"
        frappe.msgprint(f"Shopify location {status_msg}: {doc.name}")




def delete_shopify_location(doc, method):
    if doc.disabled == False:
        frappe.throw("Disable the location before deleting it from Shopify")
    if doc.flags.ignore_shopify_sync:
        return
    shopify_id = doc.custom_shopify_id
    if not shopify_id:
        return

    location_get= f"gid://shopify/Location/{shopify_id}"

    query = f"""
    mutation {{
        locationDelete(locationId: "{location_get}") {{
            deletedLocationId
        }}
    }}
    """

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": shopify_credentials().get("access_token")
    }

    response = requests.post(shopify_credentials().get("shopify_graph_url"), json={"query": query}, headers=headers)

    if response.status_code == 200:
        frappe.msgprint(f"Shopify location deleted: {doc.name}")
    else:
        status_msg = "Deleted"
        frappe.msgprint(f"Shopify location {status_msg}: {doc.name}")



def update_shopify_location(doc, method):
    if doc.flags.ignore_shopify_sync:
        return
    shopify_id = doc.custom_shopify_id
    if not shopify_id:
        frappe.log_error("Missing Shopify Location ID")
        return

    location_get = f"gid://shopify/Location/{shopify_id}"
    address = f"{doc.address_line_1} {doc.address_line_2 or ''}"
    # country = "India"
    country_code,state_code=get_country_and_state_codes(doc.custom_country,doc.state)

    # city = doc.city or " "
    # province = doc.state or " "
    # postal_code = doc.pin or ""
    # phone = doc.phone_no or ""

    query = """
    mutation updateLocation($input: LocationEditInput!, $ownerId: ID!) {
      locationEdit(input: $input, id: $ownerId) {
        location {
          id
          name
          address {
            address1
            address2
            city
            provinceCode
            countryCode
            zip
            phone
          }
        }
        userErrors {
          message
          field
        }
      }
    }
    """

    variables = {
        "input": {
            "address": {
                "address1": "",
                "address2": address,
                "city": doc.city if doc.city else "",
                "provinceCode": state_code,
                "countryCode": country_code,
                "zip": doc.pin if doc.pin else "",
                "phone": doc.phone_no if doc.phone_no else ""
            }
        },
        "ownerId": location_get
    }

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": shopify_credentials().get("access_token")
    }

    response = requests.post(shopify_credentials().get("shopify_graph_url"), json={"query": query, "variables": variables}, headers=headers)


    if response.status_code != 200 or "errors" in response.json():
        frappe.log_error(f"Shopify address update failed: {response.text}", "Shopify Sync Error")
        return

    # frappe.msgprint(f"Shopify location address updated for: {doc.name}")



###################### ORDER TO SHOPIFY#####################


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
    print(f"\n\n\n\n\n{response}\n\n\n\n")

    if response.status_code != 200 or "errors" in response.json():
        frappe.log_error("Shopify Draft Order Creation Failed", response.text)
        return
    abc=response.json().get("data", {})
    print(f"\n\n\n\n{abc}\n\n\n\n")
    draft_order = response.json().get("data", {}).get("draftOrderCreate", {}).get("draftOrder")
    print(f"\n\n\n\n\n{draft_order}\n\n\n\n")
    if draft_order and draft_order.get("id"):
        doc.custom_shopify_draft_order_id = draft_order["id"].split("/")[-1]
        doc.flags.from_shopify = True
        doc.save(ignore_permissions=True)
        frappe.msgprint("Shopify draft order created successfully.")
    else:
        frappe.log_error(" Shopify Draft Order missing ID", response.text)
