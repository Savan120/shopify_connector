import frappe
import requests
import json
from frappe import _
import random
import string
import frappe
from frappe.utils.password import check_password
from frappe import _
from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
from frappe.utils import flt
from frappe.utils import cint, cstr, getdate, nowdate
import hmac
import hashlib
import base64


@frappe.whitelist(allow_guest=True)
def receive_shopify_order():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error"
        )
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )

    order_data = json.loads(raw_request_body.decode("utf-8"))
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
            if item.get("product_id") and item.get("variant_id") and item.get("variant_title"):
                variant_id = item.get("variant_id")
                item_code = frappe.db.get_value("Item", {"custom_variant_id": variant_id})
            else:
                product_id = item.get("product_id")
                item_code = frappe.db.get_value("Item", {"shopify_id": product_id})
            if not item_code:
                item_code = product_creation()
            if item.get("tax_lines"):
                for tax in item.get("tax_lines", []):
                    tax_rate = flt(tax.get("rate")) * 100
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
            # tax_amount = float(tax.get("price", 0))
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

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Shopify Order Sync Error")
        frappe.throw(_("Error while processing Shopify order: {0}").format(str(e)))

    if True:
        if order_data.get("financial_status") == "paid":
            create_sales_invoice(sales_order)


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

    if si:
        frappe.session.user="Administrator"
        create_payment_entry(si)


def create_payment_entry(si):
    # from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    # account= frappe.db.get_value("Mode of Payment Account",{"parent":"Cash","company":si.company},"default_account")
    # payment_entry = get_payment_entry(si.doctype, si.name,bank_account=account)
    # payment_entry.flags.ignore_mandatory = True
    # payment_entry.reference_no = si.name
    # payment_entry.posting_date = nowdate()
    # payment_entry.reference_date = nowdate()
    # payment_entry.insert(ignore_permissions=True)
    # payment_entry.submit()
    setting = frappe.get_single("Shopify Connector Setting")
    invoice = frappe.get_doc("Sales Invoice", si.name)
    cost_center = frappe.db.get_value("Cost Center", {"company": si.company}, "name")
    paid_from = frappe.db.get_all(
        "Account",
        filters={"account_type": "Receivable", "company": si.company},
        fields=["name", "account_currency"],
    )
    paid_to = frappe.db.get_all(
        "Account",
        filters={"account_type": "Cash", "company": si.company},
        fields=["name", "account_currency"],
    )
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = invoice.customer
    pe.cost_center = cost_center
    pe.posting_date = nowdate()
    pe.paid_from = paid_from[0].name
    pe.mode_of_payment = "Cash"
    pe.paid_to = paid_to[1].name
    pe.paid_from_account_currency = paid_from[0].account_currency
    pe.paid_to_account_currency = paid_to[0].account_currency
    pe.paid_amount = invoice.rounded_total
    pe.received_amount = invoice.rounded_total
    pe.append(
        "references",
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": invoice.name,
            "total_amount": invoice.rounded_total,
            "allocated_amount": invoice.rounded_total,
        },
    )
    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)
    pe.submit()


def link_customer_and_address(raw_shipping_data, customer_name, contact_email):
    if raw_shipping_data:
        customer_shopify_email = contact_email
        customer_exists = frappe.get_value(
            "Customer", {"shopify_email": customer_shopify_email}
        )
        if not customer_exists:
            customer = frappe.new_doc("Customer")
        else:
            customer = frappe.get_doc(
                "Customer", {"shopify_email": customer_shopify_email}
            )
            old_name = customer.customer_name

        customer.customer_name = customer_name
        customer.shopify_email = customer_shopify_email
        customer.flags.ignore_permission = True
        customer.insert(ignore_permissions=True)
        customer.save()




@frappe.whitelist(allow_guest=True)
def customer_creation():
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    shopify_webhook_secret = shopify_keys.shopify_webhook_secret

    try:
        request_body = frappe.local.request.get_data()
    except Exception as e:
        frappe.log_error(f"Failed to get request data: {e}", "Shopify Webhook Error")
        frappe.throw("Invalid request data.")

    shopify_hmac = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")


    if not shopify_hmac:
        frappe.throw("Unauthorized: Webhook signature missing.")

    calculated_hmac = base64.b64encode(
        hmac.new(
            shopify_webhook_secret.encode("utf-8"), request_body, hashlib.sha256
        ).digest()
    )
    if not hmac.compare_digest(calculated_hmac, shopify_hmac.encode("utf-8")):
        frappe.log_error(
            f"Webhook signature mismatch. Calculated: {calculated_hmac.decode('utf-8')}, Received: {shopify_hmac}",
            "Shopify Webhook Error",
        )
        frappe.throw("Unauthorized: Invalid webhook signature.")

    if shopify_keys.sync_customer:

        def send_customer_to_shopify_hook(doc, method):
            if getattr(doc.flags, "from_shopify", False):
                return

        try:
            order_data = frappe.parse_json(request_body.decode("utf-8"))
        except Exception as e:
            frappe.log_error(
                f"Failed to parse JSON from request body: {e}", "Shopify Webhook Error"
            )
            frappe.throw("Invalid JSON payload.")


        customer_id = order_data.get("id")
        first_name = order_data.get("first_name")
        last_name = order_data.get("last_name")

        first_name_str = str(first_name) if first_name is not None else ""
        last_name_str = str(last_name) if last_name is not None else ""

        customer_name = f"{first_name_str} {last_name_str}".strip()
        
        headers = {
            'Content-Type': 'application/json',
            'X-Shopify-Access-Token': f'{shopify_keys.access_token}',
        }

        json_data = {
            'query': 'query getCustomerTags($id: ID!) { customer(id: $id) { id tags } }',
            'variables': {
                'id': f'gid://shopify/Customer/{customer_id}',
            },
        }

        response = requests.post(f'https://{shopify_keys.shop_url}/admin/api/{shopify_keys.shopify_api_version}/graphql.json', headers=headers, json=json_data)
        response_data = response.json()
        tag = ""
        tag = response_data["data"]["customer"]["tags"][0]
        
        if not tag:
            tag = shopify_keys.customer_group
            

        if not frappe.db.exists("Customer", {"shopify_email": order_data.get("email")}):
            cus = frappe.new_doc("Customer")
            cus.flags.from_shopify = True
            cus.shopify_id = customer_id
            cus.shopify_email = order_data.get("email")
            cus.customer_name = customer_name
            cus.default_currency = order_data.get("currency")
            cus.customer_group = tag 
            cus.flags.ignore_permissions = True
            cus.insert(ignore_mandatory=True)
            cus.save()
            if frappe.db.exists("Territory", order_data.get("default_address", {}).get("province")):
                cus.territory = order_data.get("default_address", {}).get("province")
            else:
                cus.territory = shopify_keys.territory 
            cus.save()
            if order_data.get("default_address").get("province") and order_data.get("default_address").get("zip"):
                address = order_data.get("default_address")
                cus_address = frappe.new_doc("Address")
                cus_address.address_title = cus.customer_name
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
                cus.customer_primary_address = cus_address.name
                cus.save()
                
        
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
                
            cus.customer_primary_contact = cus_contact.name
            
            cus.save()

            frappe.msgprint(
                _("Customer created for email: {0}").format(order_data.get("email"))
            )
        else:
            frappe.msgprint(
                _("Customer already exists for email: {0}").format(
                    order_data.get("email")
                )
            )

@frappe.whitelist(allow_guest=True)
def product_creation():
    shopify_keys = frappe.get_single("Shopify Connector Setting")
    shopify_webhook_secret = shopify_keys.shopify_webhook_secret

    try:
        request_body = frappe.local.request.get_data()
    except Exception as e:
        frappe.log_error(f"Failed to get request data: {e}", "Shopify Webhook Error")
        frappe.throw("Invalid request data.")

    shopify_hmac = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")


    if not shopify_hmac:
        frappe.throw("Unauthorized: Webhook signature missing.")

    calculated_hmac = base64.b64encode(
        hmac.new(
            shopify_webhook_secret.encode("utf-8"), request_body, hashlib.sha256
        ).digest()
    )
    if not hmac.compare_digest(calculated_hmac, shopify_hmac.encode("utf-8")):
        frappe.log_error(
            f"Webhook signature mismatch. Calculated: {calculated_hmac.decode('utf-8')}, Received: {shopify_hmac}",
            "Shopify Webhook Error",
        )
        frappe.throw("Unauthorized: Invalid webhook signature.")

    if shopify_keys.sync_product:
        try:
            order_data = frappe.parse_json(request_body.decode("utf-8"))
        except Exception as e:
            frappe.log_error(
                f"Failed to parse JSON from request body: {e}", "Shopify Webhook Error"
            )
            frappe.throw("Invalid JSON payload.")

        product_id = order_data.get("id")
        print(order_data)
        inventory_item_id = None
        for v in order_data.get("variants", []):
            inventory_item_id = v.get("inventory_item_id")

        sys_lang = frappe.get_single("System Settings").language or "en"
        settings = frappe.get_doc("Shopify Connector Setting")
        status = False
        price = 0
        hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
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
            return "Product already exists."

        item_group = ""
        if order_data.get("product_type"):
            item_type_from_shopify = frappe.db.exists("Item Group", {"item_group_name": order_data.get("product_type")})
            if not item_type_from_shopify:
                item_type = frappe.new_doc("Item Group")
                item_type.item_group_name = order_data.get("product_type")
                item_type.flags.ignore_permissions = True
                item_type.insert(ignore_permissions=True)
                
                item_group = item_type.name
        else:
            item_group = shopify_keys.item_group
            
        item = frappe.new_doc("Item")
        item.item_code = order_data.get("title")
        item.item_name = order_data.get("title")
        item.gst_hsn_code = hsn_code_shopify
        item.description = order_data.get("body_html")
        item.item_group = item_group
        item.stock_uom = settings.uom
        item.shopify_id = product_id
        item.custom_inventory_item_id = inventory_item_id
        item.custom_send_to_shopify = 1
        item.shopify_selling_rate = price

        options = order_data.get("options", [])
        has_real_variants = any(
            opt.get("name") != "Title" and len(opt.get("values", [])) > 1
            for opt in options
        )
        item.has_variants = 1 if has_real_variants else 0

        item.disabled = status

        options = order_data.get("options", [])

        if item.has_variants:
            for opt in options:
                attr_name = opt["name"]

                if not frappe.db.exists(
                    "Item Attribute", {"attribute_name": attr_name}
                ):
                    attr_doc = frappe.new_doc("Item Attribute")
                    attr_doc.attribute_name = attr_name
                    attr_doc.flags.ignore_permissions = True
                    attr_doc.insert()
                else:
                    attr_doc = frappe.get_doc(
                        "Item Attribute", {"attribute_name": attr_name}
                    )

                existing_values = frappe.get_all(
                    "Item Attribute Value",
                    filters={"parent": attr_name},
                    pluck="attribute_value",
                )

                for val in opt["values"]:
                    if val not in existing_values:
                        attr_doc.append(
                            "item_attribute_values",
                            {"attribute_value": val, "abbr": val},
                        )
                attr_doc.flags.ignore_permissions = True
                attr_doc.save()

                item.append("attributes", {"attribute": attr_name})

        images = order_data.get("images", [])
        img_link = images[0]["src"] if images else ""
        if img_link:
            file_doc = frappe.get_doc(
                {"doctype": "File", "file_url": img_link, "is_private": 0}
            )
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
                variant.item_name = order_data.get("title") +"-"+ v.get("title")
                variant.item_group = item_group
                variant.variant_of = item.name
                variant.stock_uom = item.stock_uom
                variant.custom_send_to_shopify = 1
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
                        attribute_values = [
                            d.attribute_value for d in attr_doc.item_attribute_values
                        ]
                        if opt_value in attribute_values:
                            matched_attr = attr_name
                            break

                    if matched_attr:
                        variant.append(
                            "attributes",
                            {"attribute": matched_attr, "attribute_value": opt_value},
                        )

                inventory_item_id = v.get("inventory_item_id")
                if inventory_item_id:
                    hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
                    if hsn_code_shopify:
                        if not frappe.db.exists(
                            "GST HSN Code", {"hsn_code": hsn_code_shopify}
                        ):
                            hs = frappe.new_doc("GST HSN Code")
                            hs.hsn_code = hsn_code_shopify
                            hs.insert(ignore_permissions=True)
                        variant.gst_hsn_code = hsn_code_shopify

                variant.flags.ignore_permissions = True
                variant.flags.from_shopify = True
                variant.insert(ignore_mandatory=True)
                variant.save()

        return "Product created with variants and HSN."
    else:
        return "Product sync is disabled in Shopify Connector Setting."



@frappe.whitelist(allow_guest=True)
def product_update():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    settings_for_secret = frappe.get_single("Shopify Connector Setting")
    try:
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _("Webhook secret not configured. Please set it up in Shopify Connector Setting."),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")
        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(calculated_hmac, shopify_hmac_header.encode("utf-8")):
            frappe.throw(_("Unauthorized: Invalid webhook signature."), frappe.PermissionError)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error")
        frappe.throw(_("An unexpected error occurred during webhook verification: {0}").format(e))

    order_data = json.loads(raw_request_body.decode("utf-8"))
    user = frappe.session.user = settings.webhook_session_user 
    if not user:
        frappe.log_error("Webhook User: Not Configure in Shopify Connector Setting")
    product_id = order_data.get("id")
    inventory_item_id = None
    for v in order_data.get("variants", []):
        inventory_item_id = v.get("inventory_item_id")

    sys_lang = frappe.get_single("System Settings").language or "en"
    settings = frappe.get_doc("Shopify Connector Setting")
    status = False
    price = 0
    hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
    if hsn_code_shopify:
        if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
            hs = frappe.new_doc("GST HSN Code")
            hs.hsn_code = hsn_code_shopify
            hs.insert(ignore_permissions=True)

    for prices in order_data.get("variants", []):
        price = prices.get("price")

    if order_data.get("status") == "draft":
        status = True
        
    item_group = ""
    if order_data.get("product_type"):
            item_group = order_data.get("product_type")
    else:
        item_group = settings_for_secret.item_group

    item_doc = frappe.db.exists("Item", {"shopify_id": product_id})
    item = frappe.get_doc("Item", item_doc)
    item.item_code = order_data.get("title")
    item.item_name = order_data.get("title")
    item.gst_hsn_code = hsn_code_shopify
    item.description = order_data.get("body_html")
    item.item_group = item_group
    item.stock_uom = settings.uom
    item.shopify_id = product_id
    item.custom_send_to_shopify = 1
    item.custom_inventory_item_id = inventory_item_id
    item.shopify_selling_rate = price

    options = order_data.get("options", [])
    has_real_variants = any(
        opt.get("name") != "Title" and len(opt.get("values", [])) > 1 for opt in options
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
                    attr_doc.append("item_attribute_values", {"attribute_value": val, "abbr": val})

            attr_doc.flags.ignore_permissions = True
            attr_doc.save()

            if len(item.attributes) > 0:
                for row in item.attributes:
                    if row.attribute == attr_name:
                        break
                else:
                    item.append("attributes", {"attribute": attr_name})
            else:
                item.append("attributes", {"attribute": attr_name})

    images = order_data.get("images", [])
    img_link = images[0]["src"] if images else ""
    if img_link:
        file_doc = frappe.get_doc(
            {"doctype": "File", "file_url": img_link, "is_private": 0}
        )
        file_doc.insert(ignore_permissions=True)
        item.image = file_doc.file_url

    item.flags.ignore_permissions = True
    item.flags.from_shopify = True

    
    item.save()

    if item.has_variants:
        for v in order_data.get("variants", []):
            if frappe.db.exists("Item", {"custom_variant_id": v.get("id")}):
                variant = frappe.get_doc("Item", {"custom_variant_id": v.get("id")})
            else:
                variant = frappe.new_doc("Item")

            variant.item_code = order_data.get("title") + "-" + v.get("title")
            variant.item_name = order_data.get("title") + "-" + v.get("title")
            variant.item_group = item_group
            variant.variant_of = item.name
            variant.custom_send_to_shopify = 1
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
                    if len(variant.attributes) > 0:
                        for row in variant.attributes:
                            if row.attribute == matched_attr:
                                break
                        else:
                            variant.append("attributes", {"attribute": matched_attr, "attribute_value": opt_value})
                    else:
                        variant.append("attributes", {"attribute": matched_attr, "attribute_value": opt_value})

            inventory_item_id = v.get("inventory_item_id")
            if inventory_item_id:
                hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
                if hsn_code_shopify:
                    if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
                        hs = frappe.new_doc("GST HSN Code")
                        hs.hsn_code = hsn_code_shopify
                        hs.insert(ignore_permissions=True)
                    variant.gst_hsn_code = hsn_code_shopify

            variant.flags.ignore_permissions = True
            variant.flags.from_shopify = True


            variant.save()
        

    return "Product created with variants and HSN."



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

@frappe.whitelist(allow_guest=True)
def get_inventory_level():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error"
        )
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )

    inv_level = json.loads(raw_request_body.decode("utf-8"))

    if inv_level.get("available") != 0:
        item = frappe.db.get_value("Item", {"custom_inventory_item_id": inv_level.get("inventory_item_id")},"name")
        item_doc = frappe.get_doc("Item",item)
        warehouse = frappe.db.get_value("Warehouse",{"custom_shopify_id":inv_level.get("location_id")},"name")
        
        se = frappe.new_doc("Stock Entry")
        se.stock_entry_type = "Material Receipt"
        se.append("items",{
            "item_code": item,
            "t_warehouse":warehouse,
            "qty": inv_level.get("available"),
            "basic_rate": item_doc.shopify_selling_rate,
            "uom":"Nos"
        })
        se.flags.ignore_permissions = True
        se.flags.ignore_mandatory = True
        se.insert()
        se.submit()


@frappe.whitelist(allow_guest=True)
def get_inventory_update():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error"
        )
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )

    inv_data = json.loads(raw_request_body.decode("utf-8"))
    location_id = inv_data.get("location_id")
    if location_id:
        frappe.cache().set_value("shopify_last_location_id", location_id)
    return location_id



@frappe.whitelist(allow_guest=True)
def customer_update():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")

    settings = frappe.get_single("Shopify Connector Setting")
    try:
        shopify_webhook_secret = settings.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _("Webhook secret not configured. Please set it up in Shopify Connector Setting."),
                frappe.ValidationError,
            )

        if not shopify_hmac_header:
            frappe.throw(_("Unauthorized: Webhook signature missing."), frappe.PermissionError)

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")
        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        ).decode()

        if not hmac.compare_digest(calculated_hmac, shopify_hmac_header):
            frappe.throw(_("Unauthorized: Invalid webhook signature."), frappe.PermissionError)

    except Exception as e:
        frappe.throw(_(f"Webhook verification error: {e}"))

    try:
        order_data = frappe.parse_json(raw_request_body.decode("utf-8"))
    except Exception as e:
        frappe.log_error(f"Failed to parse JSON: {e}", "Shopify Webhook Error")
        frappe.throw(_("Invalid JSON payload."))

    user = frappe.session.user = settings.webhook_session_user 
    if not user:
        frappe.log_error("Webhook User: Not Configure in Shopify Connector Setting")
        
    shopify_id = order_data.get("id")
    
    headers = {
            'Content-Type': 'application/json',
            'X-Shopify-Access-Token': f'{settings.access_token}',
        }

    json_data = {
        'query': 'query getCustomerTags($id: ID!) { customer(id: $id) { id tags } }',
        'variables': {
            'id': f'gid://shopify/Customer/{shopify_id}',
        },
    }

    response = requests.post(f'https://{settings.shop_url}/admin/api/{settings.shopify_api_version}/graphql.json', headers=headers, json=json_data)
    response_data = response.json()
    tag = ""
    tag = response_data["data"]["customer"]["tags"][0]
    
    if not tag:
        tag = settings.customer_group
        
        
    if not shopify_id:
        frappe.throw(_("Shopify customer ID is missing in the payload."))

    if frappe.db.exists("Customer", {"shopify_id": shopify_id}):
        customer = frappe.get_doc("Customer", {"shopify_id": shopify_id})

        if not customer:
            frappe.msgprint(_("Customer not found with Shopify ID."))
            return

        customer.flags.ignore_permissions = True
        
        customer_name = ""
        if order_data.get("first_name") or order_data.get("last_name"):
            customer_name = f"{order_data.get('first_name', '')} {order_data.get('last_name', '')}".strip()
        if not order_data.get("last_name"):
            customer_name = order_data.get("first_name")
        
        customer.db_set("customer_name", customer_name)
        customer.db_set("shopify_email", order_data.get("email"))
        customer.db_set("customer_group", tag)
        customer.db_set("default_currency", order_data.get("currency"))
        customer.save()
        
        customer.flags.from_shopify = True
        state = order_data.get("default_address").get("province") 
        pincode = order_data.get("default_address").get("zip")
        
        if state and pincode:
            
            address_data = order_data.get("default_address")
            address = None

            if customer.customer_primary_address:
                address = frappe.get_doc("Address", customer.customer_primary_address)
            
            if not address:
                address = frappe.new_doc("Address")
                address.address_title = customer.name
                address.address_type = "Shipping"
                address.append("links", {
                    "link_doctype": "Customer",
                    "link_name": customer.name,
                })

            address.update({
                "address_line1": address_data.get("address1"),
                "address_line2": address_data.get("address2"),
                "city": address_data.get("city"),
                "state": address_data.get("province"),
                "country": address_data.get("country"),
                "pincode": address_data.get("zip"),
                "phone": address_data.get("phone"),
                "address_title": f"{address_data.get('first_name', '')} {address_data.get('last_name', '')}",
                "address_type": "Shipping"
            })
            
            address.flags.ignore_permissions = True
            address.save(ignore_permissions=True)

            frappe.db.set_value("Customer", customer.name, "customer_primary_address", address.name)

            contact = None
            if customer.customer_primary_contact:
                contact = frappe.get_doc("Contact", customer.customer_primary_contact)
            
            if not contact:
                contact = frappe.new_doc("Contact")
                contact.first_name = address_data.get("first_name")
                contact.middle_name = address_data.get("middle_name") or ""
                contact.last_name = address_data.get("last_name")
                contact.append("email_ids", {
                    "email_id": order_data.get("email"),
                    "is_primary": 1,
                })
                contact.append("phone_nos", {
                    "phone": order_data.get("phone"),
                    "is_primary_phone": 1,
                })
                contact.append("links", {
                    "link_doctype": "Customer",
                    "link_name": customer.name,
                })
                contact.flags.ignore_permissions = True
                contact.save(ignore_permissions=True)
                frappe.db.set_value("Customer", customer.name, "customer_primary_contact", contact.name)
            else:
                contact.update({
                    "first_name": address_data.get("first_name"),
                    "middle_name": address_data.get("middle_name") or "",
                    "last_name": address_data.get("last_name")
                })
                contact.set("email_ids", [{
                    "email_id": order_data.get("email"),
                    "is_primary": 1
                }])
                contact.set("phone_nos", [{
                    "phone": order_data.get("phone"),
                    "is_primary_phone": 1
                }])
                contact.flags.ignore_permissions = True
                contact.save(ignore_permissions=True)

            frappe.msgprint(_("Customer updated for email: {0}").format(order_data.get("email")))            
    else:
        frappe.msgprint(_("Customer does not exist for email: {0}").format(order_data.get("email")))

@frappe.whitelist(allow_guest=True)
def delete_customer_webhook():

    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")

    try:
        settings = frappe.get_single("Shopify Connector Setting")
        secret = settings.shopify_webhook_secret

        if not secret:
            frappe.throw("Webhook secret not set in Shopify Connector Setting.")

        secret_bytes = secret.encode("utf-8")
        calculated_hmac = base64.b64encode(
            hmac.new(secret_bytes, raw_request_body, hashlib.sha256).digest()
        )

        if not hmac.compare_digest(calculated_hmac, shopify_hmac_header.encode("utf-8")):
            frappe.throw("Unauthorized: Invalid webhook signature.")

        data = json.loads(raw_request_body.decode("utf-8"))
        shopify_customer_id = str(data.get("id"))

        if not shopify_customer_id:
            frappe.throw("Customer ID missing in webhook payload.")

        customer_names = frappe.get_all("Customer", filters={"shopify_id": shopify_customer_id}, pluck="name")
        if not customer_names:
            return

        customer_name = customer_names[0]
        frappe.db.set_value("Customer", customer_name, "disabled", 1)
        

    except Exception:
        frappe.log_error(frappe.get_traceback(), "Shopify Delete Webhook Error")
        frappe.clear_messages()
        frappe.response["http_status_code"] = 500
        return "Error"



@frappe.whitelist(allow_guest=True)
def order_update():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")

    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        if not shopify_hmac_header:
            frappe.throw(
                _("Unauthorized: Webhook signature missing."), frappe.PermissionError
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )

        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )

    try:
        order_data = frappe.parse_json(raw_request_body.decode("utf-8"))
    except Exception as e:
        frappe.log_error(
            f"Failed to parse JSON from request body: {e}", "Shopify Webhook Error"
        )
        frappe.throw("Invalid JSON payload.")

    customer_email = order_data.get("email")
    customer_name = frappe.db.get_value(
        "Customer", {"shopify_email": customer_email}, "name"
    )

    settings = frappe.get_doc("Shopify Connector Setting")
    password = settings.access_token
    shopify_url = settings.shop_url

    company_abbr = frappe.db.get_value("Company", settings.company, "abbr")
    sys_lang = frappe.get_single("System Settings").language or "en"

    order_number = order_data.get("order_number")
    location_id = order_data.get("location_id") or frappe.cache().get_value("shopify_last_location_id")
    warehouse = frappe.db.get_value("Warehouse", {"custom_shopify_id": location_id})
    if not warehouse:
        warehouse = settings.warehouse or f"Stores - {company_abbr}"
    customer = order_data.get("customer", {})
    customer_full_name = (
        customer.get("first_name", "") + " " + customer.get("last_name", "")
    ).strip() or "Guest"
    created_date = order_data.get("created_at", "").split("T")[0]
    items = order_data.get("line_items", [])
    discount_info = order_data.get("discount_applications", [])

    discount_percentage = sum(
        float(dis.get("value", 0))
        for dis in discount_info
        if dis.get("value_type") == "percentage"
    )
    discount_fixed = sum(
        float(dis.get("value", 0))
        for dis in discount_info
        if dis.get("value_type") == "fixed_amount"
    )

    sales_id = frappe.db.get_value("Sales Order", {"shopify_id": order_number})

    if not sales_id:
        frappe.throw(
            _("Sales Order not found for Shopify Order: {0}").format(order_number)
        )

    sales_order = frappe.get_doc("Sales Order", sales_id)
    sales_order.customer = customer_full_name
    sales_order.shopify_id = order_number
    sales_order.company = settings.company
    sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
    sales_order.transaction_date = created_date
    sales_order.delivery_date = frappe.utils.add_days(
        created_date, settings.delivery_after_days or 7
    )
    sales_order.additional_discount_percentage = discount_percentage or 0
    sales_order.discount_amount = discount_fixed or 0

    address = order_data.get("shipping_address") or order_data.get("billing_address")
    if address and sales_order.customer_address:
        cus_address = frappe.get_doc("Address", sales_order.customer_address)
        cus_address.db_set(
            "address_title",
            (
                address.get("first_name", "") + " " + address.get("last_name", "")
            ).strip(),
        )
        cus_address.address_type = "Shipping"
        cus_address.address_line1 = address.get("address1")
        cus_address.address_line2 = address.get("address2")
        cus_address.city = address.get("city")
        cus_address.state = address.get("province")
        cus_address.country = address.get("country")
        cus_address.pincode = address.get("zip")
        cus_address.phone = address.get("phone")
        cus_address.flags.ignore_permissions = True
        cus_address.save()

    sales_order.set("items", [])

    for item in items:
        product_id = item.get("product_id") or item.get("id")
        item_name = item.get("name")
        quantity = item.get("quantity")
        price = item.get("price")
        item_code = f"Shopify-{product_id}"

        exist_item = frappe.db.get_value("Item", {"name": item_code}, "name")

        if not exist_item:
            new_item = frappe.new_doc("Item")
            new_item.item_code = f"Shopify-{product_id or a }"
            new_item.item_name = item_name
            new_item.stock_uom = settings.uom or _("Nos", sys_lang)
            new_item.item_group = _("Shopify Products", sys_lang)
            new_item.shopify_id = product_id
            new_item.shopify_selling_rate = item.get("price", 0)
            new_item.flags.ignore_mandatory = True
            new_item.insert(ignore_permissions=True)
            new_item.save()
            exist_item = new_item.name

        for tax in item.get("tax_lines", []):
            tax_account = frappe.db.get_value(
                "Item Tax Template", {"gst_rate": tax.get("rate")}
            )
            sales_order.append(
                "items",
                {
                    "item_code": exist_item,
                    "item_name": item_name,
                    "qty": quantity,
                    "rate": price,
                    "uom": settings.uom or _("Nos", sys_lang),
                    "delivery_date": sales_order.delivery_date,
                    "warehouse": settings.warehouse or f"Stores - {company_abbr}",
                    "item_tax_template": tax_account,
                    "gst_treatment": "Taxable",
                },
            )

    # sales_order.set("taxes", [])
    # for tax in order_data.get("tax_lines", []):
    #     sales_order.append(
    #         "taxes",
    #         {
    #             "charge_type": "Actual",
    #             "account_head": tax_account,
    #             "description": tax.get("title") or "Shopify Tax",
    #             "rate": (tax.get("rate") or 0) * 100,
    #             "tax_amount": float(tax.get("price", 0)),
    #         },
    #     )

    sales_order.flags.ignore_permissions = True
    sales_order.save()

    return {
        "status": "success",
        "message": f"Sales Order updated for Shopify Order: {order_number}",
        "sales_order": sales_order.name,
    }


@frappe.whitelist(allow_guest=True)
def get_shopify_location():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error"
        )
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )

    response = json.loads(raw_request_body.decode("utf-8"))
    if settings_for_secret.sync_location:

        if not response:
            frappe.log_error("No locations found.")
            return

        disabled = not response.get("active", True)
        shopify_id = response.get("id")
        warehouse_name = response.get("name")

        warehouse_existing = frappe.db.get_value(
            "Warehouse", {"custom_shopify_id": shopify_id}, "name"
        )
        if warehouse_existing:
            warehouse = frappe.get_doc("Warehouse", warehouse_existing)

        else:
            warehouse = frappe.new_doc("Warehouse")
        warehouse.warehouse_name = warehouse_name
        warehouse.address_line_1 = response.get("address1")
        warehouse.address_line_2 = response.get("address2")
        warehouse.city = response.get("city")
        warehouse.state = response.get("province")
        warehouse.custom_country = response.get("country_name")
        warehouse.pin = response.get("zip")
        warehouse.phone_no = response.get("phone")
        warehouse.custom_shopify_id = shopify_id
        warehouse.disabled = disabled
        warehouse.flags.ignore_shopify_sync = True
        warehouse.flags.ignore_permissions = True
        warehouse.save()




@frappe.whitelist(allow_guest = True)
def order_payment_update():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error"
        )
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )
    order_payment = json.loads(raw_request_body.decode("utf-8"))

    if order_payment.get("order_number"):
        sales_order = frappe.db.get_value("Sales Order", {"shopify_id": order_payment.get("order_number")},"name")
        sal_order = frappe.get_doc("Sales Order",sales_order)
        sal_order.flags.ignore_permissions = True 
        sal_order.flags.ignore_mandatory = True
        sal_order.submit()
        create_sales_invoice(sal_order)


#######################################################################################

@frappe.whitelist(allow_guest=True)
def update_shopify_location():
    raw_request_body = frappe.local.request.get_data()
    shopify_hmac_header = frappe.local.request.headers.get("X-Shopify-Hmac-Sha256")
    try:
        settings_for_secret = frappe.get_single("Shopify Connector Setting")
        shopify_webhook_secret = settings_for_secret.shopify_webhook_secret

        if not shopify_webhook_secret:
            frappe.throw(
                _(
                    "Webhook secret not configured. Please set it up in Shopify Connector Setting."
                ),
                frappe.ValidationError,
            )

        secret_key_bytes = shopify_webhook_secret.encode("utf-8")

        calculated_hmac = base64.b64encode(
            hmac.new(secret_key_bytes, raw_request_body, hashlib.sha256).digest()
        )
        if not hmac.compare_digest(
            calculated_hmac, shopify_hmac_header.encode("utf-8")
        ):
            frappe.throw(
                _("Unauthorized: Invalid webhook signature."), frappe.PermissionError
            )

    except Exception as e:
        frappe.log_error(
            frappe.get_traceback(), "Shopify Webhook Unexpected Verification Error"
        )
        frappe.throw(
            _(f"An unexpected error occurred during webhook verification: {e}")
        )

    response = json.loads(raw_request_body.decode("utf-8"))

    if settings_for_secret.sync_location:

        if not response:
            frappe.log_error("No locations found.")
            return

        disabled = not response.get("active", True)
        shopify_id = response.get("id")
        warehouse_name = response.get("name")

        warehouse_existing = frappe.db.get_value(
            "Warehouse", {"custom_shopify_id": shopify_id}, "name"
        )
        if warehouse_existing:
            warehouse = frappe.get_doc("Warehouse", warehouse_existing)
        else:
            frappe.throw("No such Warehouse Exists")

        warehouse.warehouse_name = warehouse_name
        warehouse.address_line_1 = response.get("address1")
        warehouse.address_line_2 = response.get("address2")
        warehouse.city = response.get("city")
        warehouse.state = response.get("province")
        warehouse.custom_country = response.get("country_name")
        warehouse.pin = response.get("zip")
        warehouse.phone_no = response.get("phone")
        warehouse.custom_shopify_id = shopify_id
        warehouse.disabled = disabled
        warehouse.flags.ignore_shopify_sync = True
        warehouse.flags.ignore_permissions = True
        warehouse.save()

