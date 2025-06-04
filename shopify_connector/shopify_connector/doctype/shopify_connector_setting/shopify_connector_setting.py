
import frappe
from frappe.model.document import Document
import requests
from frappe import _
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from typing import Dict, List
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.nestedset import get_root_of
from frappe.utils import cstr
import datetime

from frappe.utils import flt
from frappe.utils import cint, cstr, getdate, nowdate

from shopify_connector.shopify_connector.constants import (
    ADDRESS_ID_FIELD,
    CUSTOMER_ID_FIELD,
    FULLFILLMENT_ID_FIELD,
    ITEM_SELLING_RATE_FIELD,
    ORDER_ID_FIELD,
    ORDER_ITEM_DISCOUNT_FIELD,
    ORDER_NUMBER_FIELD,
    ORDER_STATUS_FIELD,
    SUPPLIER_ID_FIELD,
)

class ShopifyConnectorSetting(Document):
    
    def validate(self):
        if self.enable_shopify:
            setup_custom_fields()
            # create_delete_custom_fields(self)
            # product_creation()
            customer_creation() 
            # get_order() 
            # get_shopify_location()
            # sync_shopify_products_to_erpnext()
            # get_inv_level()
            # get_inventory_levels_for_all_items()



def setup_custom_fields():
    custom_fields = {
        "Item": [
            dict(
                fieldname=ITEM_SELLING_RATE_FIELD,
                label="Shopify Selling Rate",
                fieldtype="Currency",
                insert_after="standard_rate",
            )
        ],
        "Customer": [
            dict(
                fieldname=CUSTOMER_ID_FIELD,
                label="Shopify Customer Id",
                fieldtype="Data",
                insert_after="series",
                read_only=1,
                print_hide=1,
            )
        ],
        "Supplier": [
            dict(
                fieldname=SUPPLIER_ID_FIELD,
                label="Shopify Supplier Id",
                fieldtype="Data",
                insert_after="supplier_name",
                read_only=1,
                print_hide=1,
            )
        ],
        "Address": [
            dict(
                fieldname=ADDRESS_ID_FIELD,
                label="Shopify Address Id",
                fieldtype="Data",
                insert_after="fax",
                read_only=1,
                print_hide=1,
            )
        ],
        "Sales Order": [
            dict(
                fieldname=ORDER_ID_FIELD,
                label="Shopify Order Id",
                fieldtype="Small Text",
                insert_after="title",
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=ORDER_NUMBER_FIELD,
                label="Shopify Order Number",
                fieldtype="Small Text",
                insert_after=ORDER_ID_FIELD,
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=ORDER_STATUS_FIELD,
                label="Shopify Order Status",
                fieldtype="Small Text",
                insert_after=ORDER_NUMBER_FIELD,
                read_only=1,
                print_hide=1,
            ),
        ],
        "Sales Order Item": [
            dict(
                fieldname=ORDER_ITEM_DISCOUNT_FIELD,
                label="Shopify Discount per unit",
                fieldtype="Float",
                insert_after="discount_and_margin",
                read_only=1,
            ),
        ],
        "Delivery Note": [
            dict(
                fieldname=ORDER_ID_FIELD,
                label="Shopify Order Id",
                fieldtype="Small Text",
                insert_after="title",
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=ORDER_NUMBER_FIELD,
                label="Shopify Order Number",
                fieldtype="Small Text",
                insert_after=ORDER_ID_FIELD,
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=ORDER_STATUS_FIELD,
                label="Shopify Order Status",
                fieldtype="Small Text",
                insert_after=ORDER_NUMBER_FIELD,
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=FULLFILLMENT_ID_FIELD,
                label="Shopify Fulfillment Id",
                fieldtype="Small Text",
                insert_after="title",
                read_only=1,
                print_hide=1,
            ),
        ],
        "Sales Invoice": [
            dict(
                fieldname=ORDER_ID_FIELD,
                label="Shopify Order Id",
                fieldtype="Small Text",
                insert_after="title",
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=ORDER_NUMBER_FIELD,
                label="Shopify Order Number",
                fieldtype="Small Text",
                insert_after=ORDER_ID_FIELD,
                read_only=1,
                print_hide=1,
            ),
            dict(
                fieldname=ORDER_STATUS_FIELD,
                label="Shopify Order Status",
                fieldtype="Small Text",
                insert_after=ORDER_ID_FIELD,
                read_only=1,
                print_hide=1,
            ),
        ],
    }
    create_custom_fields(custom_fields)
def create_delete_custom_fields(self):
    create_custom_fields(
        {
            ("Customer", "Sales Order", "Item", "Address"): dict(
                fieldname="shopify_id",
                label="Shopify ID",
                fieldtype="Data",
                read_only=1,
                print_hide=1,
            ),
            ("Customer", "Address"): dict(
                fieldname="shopify_email",
                label="Shopify Email",
                fieldtype="Data",
                read_only=1,
                print_hide=1,
            ),
        }
    )
    if not frappe.get_value("Item Group", {"name": _("Shopify Products")}):
        item_group = frappe.new_doc("Item Group")
        item_group.item_group_name = _("Shopify Products")
        item_group.parent_item_group = get_root_of("Item Group")
        item_group.insert()
  

def get_shopify_location():
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version
    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_ACCESS_TOKEN}@{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/locations.json"

    response = requests.get(url, headers=headers, verify=False)

    if response.status_code == 200:
        locations = response.json().get("locations", [])

        if not locations:
            frappe.log_error("No locations found.")
            return

        for location in locations:
            disabled = not location.get("active", True)
            shopify_id = location.get("id")
            warehouse_name = location.get("name")


            warehouse_existing = frappe.db.get_value("Warehouse", {"custom_shopify_id": shopify_id}, "name")
            if warehouse_existing:
                warehouse = frappe.get_doc("Warehouse", warehouse_existing)

            else:
                warehouse = frappe.new_doc("Warehouse")
            warehouse.warehouse_name = warehouse_name
            warehouse.address_line_1 = location.get("address1")
            warehouse.address_line_2 = location.get("address2")
            warehouse.city = location.get("city")
            warehouse.state = location.get("province")
            warehouse.custom_country = location.get("country_name")
            warehouse.pin = location.get("zip")
            warehouse.phone_no = location.get("phone")
            warehouse.custom_shopify_id = shopify_id
            warehouse.disabled = disabled
            warehouse.flags.ignore_shopify_sync = True
            warehouse.save()

    else:
        frappe.log_error("Failed to fetch locations from Shopify")

# def get_order(self):
#     api_key = self.api_key
#     password = self.access_token
#     shopify_url = self.shop_url
#     endpoint = f"https://{shopify_url}/admin/api/2024-01/orders.json"
#     headers = {
#         "X-Shopify-Access-Token": password,
#         "Content-Type": "application/json"
#     }
#     response = requests.get(endpoint, headers=headers, verify=False)
#     orders = response.json()["orders"]
#     if orders:
#         shopify_connector_setting = frappe.get_doc("Shopify Connector Setting")
#         sys_lang = frappe.get_single("System Settings").language or "en"
#         for order_data in orders:
#             order_id = order_data.get('order_number')

#             shipping = order_data.get('shipping')

#             line_items = order_data.get('line_items')
#             items_list = line_items

#             images_src = []
#             for image_item in line_items:
#                 idd = image_item.get('product_id')
#                 response = requests.get(f'https://{shopify_url}/admin/api/2021-10/products/{idd}.json', headers={'X-Shopify-Access-Token': password},verify=False)

#                 if response.status_code == 200:
#                     product_data = response.json()['product']
#                     images_src += [image['src'] for image in product_data['images']]
#                 else:
#                     print(f"Failed to fetch product details: {response.status_code} - {response.text}")
#             img_link  = images_src[0] if len(images_src)>0 else ''

#             billing = order_data.get('billing_address')
#             raw_billing_data = billing

#             shipping = order_data.get('shipping_address',False)
#             raw_shipping_data = shipping

#             contact_email = order_data.get('contact_email')
#             if raw_shipping_data:
#                 customer_name = (raw_shipping_data.get("first_name") or "") + " " + (raw_shipping_data.get("last_name") or "")

#             else: 
#                 customer_name = ""

#             discount_info = order_data.get('discount_applications')
#             disc_type = ''
#             for dis_value in discount_info:
#                 disc_type = dis_value.get('value_type')
#                 dis_value.get('value')
#                 disc_type = dis_value.get('value_type')

#             discount_per = 0
#             if disc_type == 'percentage':
#                 if len(discount_info) > 0 :
#                     for line_price in discount_info:
#                         discount_per+= float(line_price.get('value'))
            

#             discount_codes = order_data.get('discount_codes')
#             discount_amount = 0
#             if disc_type == 'fixed_amount':
#                 if len(discount_codes) > 0 :
#                     for line_price in discount_codes:
#                         discount_amount+= float(line_price.get('amount'))


#             tax_lines = order_data.get('tax_lines')

#             tax_lines_amount = 0
#             for tl in tax_lines: 
#                 tax_lines_amount = tl.get('price')

#             shipping_lines_data = order_data.get('shipping_lines')
        
#             shipping_lines = 0
#             if len(shipping_lines_data) > 0 :
#                 for line_price in shipping_lines_data:
#                     shipping_lines+= float(line_price.get('price'))

#             date_created = order_data.get('created_at').split("T")
#             date_created = date_created[0]

#             if not customer_name:
#                 print(_(f"Not Customer Available in Shopify Order !! Please check the order id {order_id}"))
#                 continue          
#     else:
#         frappe.throw(_("Shopify Order is not available !!"))

def get_order():
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }

    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/orders.json"

    response = requests.get(url, headers=headers, verify=False)
    if response.status_code != 200:
        frappe.throw(f"Failed to fetch product data: {response.text}")

    data = response.json()
    orderdata = data.get("orders", [])
    # print("\n\n\n\n\n>>>>>>>>>>",order_data)
    for order_data in orderdata:
        print(order_data) 
        try:
            settings = frappe.get_doc("Shopify Connector Setting")
            company_abbr = frappe.db.get_value("Company", settings.company, "abbr")
            sys_lang = frappe.get_single("System Settings").language or "en"
            shopify_url = settings.shop_url
            password = settings.access_token

            order_number = order_data.get("order_number")
            if frappe.db.exists("Sales Order", {"shopify_id": order_number}):
                return "Order already exists."

            location_id = order_data.get("location_id") or frappe.cache().get_value("shopify_last_location_id")
            warehouse = frappe.db.get_value("Warehouse", {"custom_shopify_id": location_id})
            if not warehouse:
                warehouse = settings.warehouse or f"Stores - {company_abbr}"

            customer = order_data.get("customer", {})

            customer_email = customer.get("email")
            id = customer.get("id")
            customer_name = (
                (customer.get("first_name") or "") + " " + (customer.get("last_name") or "")
            )
            customer_name = customer_name.strip() or "Guest"

            created_date = order_data.get("created_at", "").split("T")[0]
            items = order_data.get("line_items", [])
            tax_lines = order_data.get("tax_lines", [])
            tax_total_amt = order_data.get("current_total_tax")

            shipping_lines = order_data.get("shipping_lines", [])

            shipping_address = order_data.get("shipping_address") or {}
            billing_address = order_data.get("billing_address") or {}

            discount_info = order_data.get("discount_applications", [])
            discount_percentage = sum(
                float(d.get("value", 0))
                for d in discount_info
                if d.get("value_type") == "percentage"
            )
            discount_fixed = sum(
                float(d.get("value", 0))
                for d in discount_info
                if d.get("value_type") == "fixed_amount"
            )

            customer_docname = frappe.db.get_value("Customer", {"shopify_id": id})
            if not customer_docname:
                customer_docname = customer_creation()
            sales_order = frappe.new_doc("Sales Order")
            sales_order.customer = customer_name
            sales_order.shopify_id = order_number
            sales_order.delivery_date = created_date
            sales_order.company = settings.company
            sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
            sales_order.transaction_date = created_date
            sales_order.additional_discount_percentage = discount_percentage
            sales_order.discount_amount = discount_fixed

            for item in items:
                variant_id = item.get("variant_id")
                variant_title = item.get("variant_title")
                product_id = item.get("product_id")
                item_code = None
                if variant_title:
                    item_code = frappe.db.get_value("Item", {"shopify_id": variant_id})
                else:
                    item_code = frappe.db.get_value("Item", {"shopify_id": product_id})
                if not item_code:
                    item_code = product_creation()
                if item.get("tax_lines"):
                    for tax in item.get("tax_lines", []):
                        tax_rate = flt(tax.get("rate")) * 100
                        print(tax_rate)
                        tax_account = frappe.db.get_value(
                            "Item Tax Template", {"gst_rate": tax_rate}
                        )
                        sales_order.append(
                            "items",
                            {
                                "item_code": item_code,
                                "delivery_date": sales_order.delivery_date,
                                "uom": settings.uom or "Nos",
                                "qty": item.get("quantity", 1),
                                "rate": item.get("price", 0),
                                "warehouse": warehouse
                                or f"Stores - {company_abbr}",
                                # "item_tax_template": tax_account,
                                # "gst_treatment": "Taxable",
                            },
                        )
                else:
                    sales_order.append(
                        "items",
                        {
                            "item_code": item_code,
                            "delivery_date": sales_order.delivery_date,
                            "uom": settings.uom or "Nos",
                            "qty": item.get("quantity", 1),
                            "rate": item.get("price", 0),
                            "warehouse": warehouse,
                        },
                    )

            for line in shipping_lines:
                price = float(line.get("price", 0))
                if price > 0:
                    sales_order.append(
                        "items",
                        {
                            "item_code": "Shipping Charge",
                            "delivery_date": sales_order.delivery_date,
                            "uom": settings.uom or "Nos",
                            "qty": 1,
                            "rate": price,
                            "warehouse": warehouse,
                        },
                    )

            for tax in tax_lines:
                rate = (tax.get("rate") or 0) * 100
                tax_amount = float(tax.get("price", 0))
                sales_order.append("taxes", {
                    "charge_type": "On Net Total",
                    "account_head": settings.tax_account,
                    "rate": rate
                })

            sales_order.flags.ignore_permissions = True
            sales_order.flags.ignore_mandatory = True
            sales_order.insert()

            if order_data.get("financial_status") == "paid":
                sales_order.submit()

            # sales_order.submit()

            frappe.msgprint(
                _("Sales Order created for order number: {0}").format(order_number)
            )

            if True:
                if order_data.get("financial_status") == "paid":
                    create_sales_invoice(sales_order)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Shopify Order Sync Error")
            frappe.throw(_("Error while processing Shopify order: {0}").format(str(e)))



def create_sales_invoice(so):
    cost_center = frappe.db.get_value("Cost Center", {"company": so.company}, "name")
    si = make_sales_invoice(so.name, ignore_permissions=True)
    si.customer = so.customer
    si.company = so.company
    si.update_stock = 1
    si.cost_center = cost_center
    si.due_date = nowdate()
    si.posting_date = nowdate()

    si.flags.ignore_mandatory = True
    si.insert(ignore_mandatory=True)
    si.submit()


def customer_creation():
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }

    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/customers.json"

    response = requests.get(url, headers=headers, verify=False)
    if response.status_code != 200:
        frappe.throw(f"Failed to fetch product data: {response.text}")

    order_data = response.json()
            
    customer_data = order_data.get("customers", [])
    for order_data in customer_data:
        customers_group = ""
        if order_data.get("tags"):
            get_customer_group = frappe.db.get_value("Customer Group", {"customer_group_name": order_data.get("tags")})
            if not get_customer_group:
                customer_group = frappe.new_doc("Customer Group")
                customer_group.customer_group_name = order_data.get("tags")
                customer_group.flags.ignore_permissions = True
                customer_group.insert(ignore_mandatory=True)
                customer_group.save()
                customers_group = customer_group.name

        first_name = order_data.get("first_name")
        last_name = order_data.get("last_name")
        
        if last_name:
            customer_name =f"{first_name} {last_name}".strip()
        else:
            customer_name = first_name
            
        print(first_name)
        if not frappe.db.exists("Customer", {"shopify_email": order_data.get("email")}):
            cus = frappe.new_doc("Customer")
            cus.flags.from_shopify = True
            cus.shopify_email = order_data.get("email")
            cus.shopify_id = order_data.get("id")
            cus.customer_name = customer_name
            cus.customer_group = order_data.get("tags") or customers_group
            cus.default_currency = order_data.get("currency")
            cus.flags.ignore_permissions = True
            cus.insert(ignore_mandatory=True)
            cus.save()

            if order_data.get("default_address").get("province") and order_data.get("default_address").get("zip"):
                address = order_data.get("default_address")
                cus_address = frappe.new_doc("Address")
                cus_address.address_title = cus.name
                cus_address.address_type = "Shipping"
                cus_address.address_line1 = address.get("address1")
                cus_address.address_line2 = address.get("address2")
                cus_address.city = address.get("city")
                cus_address.state = address.get("province")  
                cus_address.country = address.get("country")
                cus_address.postal_code = address.get("zip")
                cus_address.append(
                    "links",
                    {
                        "link_doctype": "Customer",
                        "link_name": cus.name,
                    },
                )
                cus_address.flags.ignore_permissions = True
                cus_address.insert(ignore_mandatory=True)
                cus_address.save()
                frappe.db.set_value("Customer", cus.name, "customer_primary_address", cus_address.name)

            address = order_data.get("default_address")
            cus_contact = frappe.new_doc("Contact")
            cus_contact.first_name = address.get("first_name")
            cus_contact.middle_name = address.get("middle_name") or ""
            cus_contact.last_name = address.get("last_name")
            cus_contact.append(
                "email_ids",
                {
                    "email_id": order_data.get("email"),
                    "is_primary": 1,
                },
            )
            cus_contact.append(
                "phone_nos",
                {
                    "phone": order_data.get("phone"),
                    "is_primary_phone": 1,
                    "is_primary_mobile_no":1
                },
            )
            cus_contact.append(
                "links",
                {
                    "link_doctype": "Customer",
                    "link_name": cus.name,
                },
            )
            cus_contact.flags.ignore_permissions = True
            cus_contact.insert(ignore_mandatory=True)
            cus_contact.save()
            frappe.db.set_value("Customer", cus.name, "customer_primary_contact", cus_contact.name)
            
            

@frappe.whitelist()
def product_creation():
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    SHOPIFY_API_KEY = shopify_keys.api_key
    SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
    SHOPIFY_STORE_URL = shopify_keys.shop_url
    SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

    headers = {
        "Content-Type": "application/json",
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN
    }

    url = f"https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/products.json"

    response = requests.get(url, headers=headers, verify=False)
    if response.status_code != 200:
        frappe.throw(f"Failed to fetch product data: {response.text}")

    data = response.json()
    print(f"\n\n\n\n\n{data}\n\n\n")

    for order_data in data.get("products", []):
        product_id = order_data.get("id")
        inventory_item_id = None
        for v in order_data.get("variants", []):
            inventory_item_id = v.get("inventory_item_id")

        sys_lang = frappe.get_single("System Settings").language or "en"
        settings = frappe.get_doc("Shopify Connector Setting")
        status = False
        price = 0

        hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, shopify_keys)
        if hsn_code_shopify:
            if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
                hs = frappe.new_doc("GST HSN Code")
                hs.hsn_code = hsn_code_shopify
                hs.insert(ignore_permissions=True)

        for prices in order_data.get("variants", []):
            price = prices.get("price")

        if order_data.get("status") == "draft":
            status = True

        if frappe.db.exists("Item", {"shopify_id": product_id}):
            continue

        item = frappe.new_doc("Item")
        item.item_code = order_data.get("title")
        item.item_name = order_data.get("title")
        item.gst_hsn_code = hsn_code_shopify
        item.description = order_data.get("body_html")
        item.item_group = _("Shopify Products", sys_lang)
        item.stock_uom = settings.uom
        item.shopify_id = product_id
        item.custom_inventory_item_id = inventory_item_id
        item.shopify_selling_rate = price

        options = order_data.get("options", [])
        has_real_variants = any(
            opt.get("name") != "Title" and len(opt.get("values", [])) > 1
            for opt in options
        )
        item.has_variants = 1 if has_real_variants else 0
        item.disabled = status

        if item.has_variants:
            for opt in options:
                attr_name = opt["name"]

                if not frappe.db.exists("Item Attribute", {"attribute_name": attr_name}):
                    attr_doc = frappe.new_doc("Item Attribute")
                    attr_doc.attribute_name = attr_name
                    attr_doc.flags.ignore_permissions = True
                    attr_doc.insert()
                else:
                    attr_doc = frappe.get_doc("Item Attribute", {"attribute_name": attr_name})

                existing_values = frappe.get_all(
                    "Item Attribute Value",
                    filters={"parent": attr_name},
                    pluck="attribute_value",
                )

                for val in opt["values"]:
                    if val not in existing_values:
                        attr_doc.append("item_attribute_values", {
                            "attribute_value": val,
                            "abbr": val
                        })
                attr_doc.flags.ignore_permissions = True
                attr_doc.save()

                item.append("attributes", {"attribute": attr_name})

        images = order_data.get("images", [])
        img_link = images[0]["src"] if images else ""
        if img_link:
            file_doc = frappe.get_doc({
                "doctype": "File",
                "file_url": img_link,
                "is_private": 0
            })
            file_doc.insert(ignore_permissions=True)
            item.image = file_doc.file_url

        item.flags.ignore_permissions = True
        item.flags.from_shopify = True
        item.insert(ignore_mandatory=True)
        item.save()

        if item.has_variants:
            for v in order_data.get("variants", []):
                variant = frappe.new_doc("Item")
                variant.item_code = order_data.get("title") +"-"+ v.get("title")
                variant.shopify_id= v.get("id")
                variant.item_name = order_data.get("title") +"-"+ v.get("title")
                variant.item_group = _("Shopify Products", sys_lang)
                variant.variant_of = item.name
                variant.stock_uom = item.stock_uom
                variant.shopify_selling_rate = v.get("price")
                variant.custom_variant_id = v.get("id")
                variant.custom_inventory_item_id = v.get("inventory_item_id")

                variant_options = [v.get("option1"), v.get("option2"), v.get("option3")]

                for opt_value in variant_options:
                    if not opt_value:
                        continue
                    matched_attr = None
                    for opt in options:
                        attr_name = opt["name"]
                        attr_doc = frappe.get_doc("Item Attribute", attr_name)
                        attribute_values = [d.attribute_value for d in attr_doc.item_attribute_values]
                        if opt_value in attribute_values:
                            matched_attr = attr_name
                            break
                    if matched_attr:
                        variant.append("attributes", {
                            "attribute": matched_attr,
                            "attribute_value": opt_value,
                        })

                inventory_item_id = v.get("inventory_item_id")
                if inventory_item_id:
                    hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, shopify_keys)
                    if hsn_code_shopify:
                        if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
                            hs = frappe.new_doc("GST HSN Code")
                            hs.hsn_code = hsn_code_shopify
                            hs.insert(ignore_permissions=True)
                        variant.gst_hsn_code = hsn_code_shopify

                variant.flags.ignore_permissions = True
                variant.flags.from_shopify = True
                variant.insert(ignore_mandatory=True)
                variant.save()

    return "Product(s) created with variants and HSN."




@frappe.whitelist(allow_guest=True)
def get_hsn_from_shopify(inventory_item_id, settings):
    """Fetch HSN code from Shopify inventory item"""
    url = f"https://{settings.shop_url}/admin/api/2024-01/inventory_items/{inventory_item_id}.json"
    headers = {
        "X-Shopify-Access-Token": settings.access_token,
        "Content-Type": "application/json",
    }
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return (
                response.json().get("inventory_item", {}).get("harmonized_system_code")
            )
        else:
            frappe.log_error(f"HSN Fetch Failed: {response.text}", "Shopify HSN Fetch")
            return None
    except Exception as e:
        frappe.log_error(f"HSN Fetch Error: {str(e)}", "Shopify HSN Fetch")
        return None


@frappe.whitelist()
def get_series():
    return {
        "sales_order_series": frappe.get_meta("Sales Order").get_options("naming_series") or "SO-SPF-",
    }

def create_sales_order(order_id, shopify_connector_setting, customer_name, sys_lang, line_items, shipping_lines, tax_lines_amount, discount_amount, discount_per, date_created=None):
    already_synched_ids = frappe.db.get_list('Sales Order', filters=[('shopify_id', '=', order_id)], fields=['name'], as_list=True, ignore_permissions=True)

    if not already_synched_ids:
        new_sales_order = frappe.new_doc("Sales Order")
        new_sales_order.customer = customer_name
        new_sales_order.po_no = order_id
        new_sales_order.shopify_id = order_id
        new_sales_order.naming_series = shopify_connector_setting.sales_order_series or "SO-SPF-"
        

        created_date = date_created
        new_sales_order.transaction_date = created_date
        delivery_after = shopify_connector_setting.delivery_after_days or 7
        new_sales_order.delivery_date = frappe.utils.add_days(created_date, delivery_after)
        new_delivery_date = new_sales_order.delivery_date
        new_delivery_date = datetime.datetime.strptime(new_delivery_date, "%Y-%m-%d")
        new_formmat_delivery_date = new_delivery_date.date()
        final_delivery_date = datetime.datetime.strptime(str(new_formmat_delivery_date), "%Y-%m-%d")

        new_sales_order.company = shopify_connector_setting.company
        set_items_in_sales_order(new_sales_order, shopify_connector_setting, order_id, sys_lang,line_items,shipping_lines,final_delivery_date, tax_lines_amount, discount_amount, discount_per)
        new_sales_order.flags.ignore_mandatory = True
        new_sales_order.insert(ignore_mandatory=True)
        new_sales_order.submit()

        frappe.db.commit()

def set_items_in_sales_order(new_sales_order, shopify_connector_setting, order_id, sys_lang,line_items, shipping_lines, final_delivery_date, tax_lines_amount, discount_amount, discount_per):
    company_abbr = frappe.db.get_value("Company", shopify_connector_setting.company, "abbr")

    default_warehouse = _("Stores - {0}", sys_lang).format(company_abbr)
    if not frappe.db.exists("Warehouse", default_warehouse) and not shopify_connector_setting.warehouse:
        frappe.throw(_("Please set Warehouse in shopify_connector_setting"))

    # total_amount = 0.0
    for item in line_items:
        shopify_item_id = item.get("product_id")
        found_item = frappe.get_doc("Item", {"shopify_id": cstr(shopify_item_id)})		
    
        ordered_items_tax = tax_lines_amount


        new_sales_order.append(
            "items",
            {
                "item_code": found_item.name,
                "item_name": found_item.item_name,
                "description": found_item.item_name,
                "delivery_date": final_delivery_date,
                "uom": shopify_connector_setting.uom or _("Nos", sys_lang),
                "qty": item.get("quantity"),
                "rate": item.get("price"),
                "warehouse": shopify_connector_setting.warehouse or default_warehouse,
            },
        )
    
    new_sales_order.apply_discount_on = 'Net Total'
    new_sales_order.additional_discount_percentage = discount_per
    new_sales_order.discount_amount = discount_amount


    add_tax_details(
        new_sales_order, ordered_items_tax, "Ordered Item tax", shopify_connector_setting.tax_account
    )

    add_tax_details(
        new_sales_order, shipping_lines, "Shipping Tax", shopify_connector_setting.f_n_f_account
    )

def add_tax_details(sales_order, ordered_items_tax, desc, tax_account_head=None):
    sales_order.append(
        "taxes",
        {
            "charge_type": "Actual",
            "account_head": tax_account_head,
            "tax_amount": ordered_items_tax,
            "description": desc,
        },
    )

# def get_inv_level():
#     shopify_keys = frappe.get_single("Shopify Connector Setting")
#     SHOPIFY_ACCESS_TOKEN = shopify_keys.access_token
#     SHOPIFY_STORE_URL = shopify_keys.shop_url
#     SHOPIFY_API_VERSION = shopify_keys.shopify_api_version

#     shopify_location_ids = frappe.get_all(
#         "Warehouse",
#         filters={"custom_shopify_id": ["!=", ""]},
#         fields=["custom_shopify_id"]
#     )
#     print(shopify_location_ids)

#     headers = {
#         'X-Shopify-Access-Token': SHOPIFY_ACCESS_TOKEN,
#     }
    

#     location_ids = [loc["custom_shopify_id"] for loc in shopify_location_ids]

#     params = {
#         'location_ids': ','.join(location_ids),
#     }

#     response = requests.get(
#         f'https://{SHOPIFY_STORE_URL}/admin/api/{SHOPIFY_API_VERSION}/inventory_levels.json',
#         params=params,
#         headers=headers,
#     )
#     print(response)

#     if response.status_code != 200:
#         frappe.log_error(response.text, "Shopify Inventory Fetch Failed")

#     print(response.json())

    

#     return response.json()
###################################################
