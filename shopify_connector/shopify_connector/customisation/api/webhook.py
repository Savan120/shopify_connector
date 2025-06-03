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


import requests


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

    # print("\n\n\n\n>>>>>>>>>>>>>.",shopify_hmac, "\n\n\n\n>>>>>>>>",shopify_webhook_secret.encode('utf-8'))

    if not shopify_hmac:
        frappe.throw("Unauthorized: Webhook signature missing.")

    calculated_hmac = base64.b64encode(
        hmac.new(
            shopify_webhook_secret.encode("utf-8"), request_body, hashlib.sha256
        ).digest()
    )
    # print(calculated_hmac)
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

        print(f"\n\n\n\n\n{order_data}\n\n\n\n")

        customer_id = order_data.get("id")
        shop_url = "https://mysolufy.myshopify.com"
        access_token = "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"
        shopify_url = f"{shop_url}/admin/api/2025-04/customers/{customer_id}.json"

        headers = {"X-Shopify-Access-Token": access_token}

        full_data = requests.get(shopify_url, headers=headers).json()
        tags = full_data.get("customer", {}).get("tags", "")
        first_name = order_data.get("first_name")
        last_name = order_data.get("last_name")

        first_name_str = str(first_name) if first_name is not None else ""
        last_name_str = str(last_name) if last_name is not None else ""

        customer_name = f"{first_name_str} {last_name_str}".strip()

        # filters=or_(
        # {"shopify_email": order_data.get("email")},
        # {"shopify_id": order_data.get("shopify_id")}
        # ),

        if not frappe.db.exists("Customer", {"shopify_email": order_data.get("email")}):

            cus = frappe.new_doc("Customer")
            cus.flags.from_shopify = True
            cus.shopify_id = customer_id
            cus.shopify_email = order_data.get("email")
            cus.customer_name = customer_name
            cus.default_currency = order_data.get("currency")
            cus.customer_group = tags
            cus.flags.ignore_permissions = True
            cus.insert(ignore_mandatory=True)
            cus.save()

            if order_data.get("default_address"):
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
            cus.customer_primary_address = cus_address.name
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

    # print("\n\n\n\n>>>>>>>>>>>>>.",shopify_hmac, "\n\n\n\n>>>>>>>>",shopify_webhook_secret.encode('utf-8'))

    if not shopify_hmac:
        frappe.throw("Unauthorized: Webhook signature missing.")

    calculated_hmac = base64.b64encode(
        hmac.new(
            shopify_webhook_secret.encode("utf-8"), request_body, hashlib.sha256
        ).digest()
    )
    # print(calculated_hmac)
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

        print("\n\n\norder_data", order_data)
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

        if frappe.db.exists("Item", {"shopify_id": product_id}):
            return "Product already exists."

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
    print("\n\n\n\n\n\n\n\n", inv_level, "\n\n\n\n\n\n")

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
        
    frappe.log_error("order", order_data)
  
    # first_name = order_data.get("first_name")
    # last_name = order_data.get("last_name")

    # if last_name:
    #     customer_name = f"{first_name} {last_name}"
    # else:
    #     customer_name = first_name
        
    # print(first_name)
        

    if frappe.db.exists("Customer", {"shopify_id": order_data.get("id")}):
        customer = frappe.get_doc("Customer", {"shopify_id": order_data.get("id")})

        if not customer:
            frappe.msgprint("Customer not found with Shopify ID.")
            return

        customer.flags.ignore_permissions = True 

        customer.db_set("shopify_email", order_data.get("email"))
        customer.db_set("default_currency", order_data.get("currency"))
        customer.save()

        if order_data.get("default_address"):
            address = order_data.get("default_address")
            
            if customer.customer_primary_address:
                cus_address = frappe.get_doc("Address", customer.customer_primary_address)
                cus_address.db_set("address_title", f"{address.get('first_name', '')} {address.get('last_name', '')}")
                cus_address.db_set("address_type", "Shipping")
                cus_address.db_set("address_line1", address.get("address1"))
                cus_address.db_set("address_line2", address.get("address2"))
                cus_address.db_set("city", address.get("city"))
                cus_address.db_set("state", address.get("province"))
                cus_address.db_set("country", address.get("country"))
                cus_address.db_set("pincode", address.get("zip"))
                cus_address.db_set("phone", address.get("phone"))
                cus_address.flags.ignore_permissions = True
                cus_address.save()
            else:
                frappe.msgprint("No primary address found for the customer.")

        #     if customer.customer_primary_contact:
        #         contact = frappe.get_doc("Contact", customer.customer_primary_contact)

        #         # new_first_name = order_data.get("first_name")
        #         # if new_first_name and contact.first_name != new_first_name:
        #         #     contact.db_set("first_name", new_first_name)

        #         # new_last_name = order_data.get("last_name")
        #         # if new_last_name and contact.last_name != new_last_name:
        #         #     contact.db_set("last_name", new_last_name)

        #         new_email = order_data.get("email")
        #         if new_email:
        #             found_email = False
        #             for email_entry in contact.email_ids:
        #                 if email_entry.is_primary:
        #                     if email_entry.email_id != new_email:
        #                         email_entry.email_id = new_email
        #                     found_email = True
        #                     break

        #             if not found_email:
        #                 contact.append("email_ids", {
        #                     "email_id": new_email,
        #                     "is_primary": 1
        #                 })

        #         new_phone = address.get("phone")
        #         if new_phone:
        #             found_phone = False
        #             for phone_entry in contact.phone_nos:
        #                 if phone_entry.is_primary_phone or phone_entry.is_primary_mobile_no:
        #                     if phone_entry.phone != new_phone:
        #                         phone_entry.phone = new_phone
        #                         phone_entry.is_primary_phone = 1
        #                         phone_entry.is_primary_mobile_no = 1
        #                     found_phone = True
        #                     break

        #             if not found_phone:
        #                 contact.append("phone_nos", {
        #                     "phone": new_phone,
        #                     "is_primary_phone": 1,
        #                     "is_primary_mobile_no": 1
        #                 })

        #         contact.flags.ignore_permissions = True
        #         contact.save()
        #     else:
        #         frappe.msgprint("No primary contact found for the customer.")

        # frappe.msgprint(_("Customer updated for email: {0}").format(order_data.get("email")))

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
            print("FFFFFFFFFFFFFFFFFFFFFFFFFFFFF", tax_account)
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
        print("\n\n\n\nresponse", response)

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
    print(f"\n\n\n\n{order_payment}\n\n\n\n")

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


################################################################################

# @frappe.whitelist(allow_guest=True)
# def product_update():
#     order_data = frappe.local.request.get_json()
#     print(order_data)
#     product_id = order_data.get("id")

#     settings = frappe.get_doc("Shopify Connector Setting")
#     sys_lang = frappe.get_single("System Settings").language or "en"

#     template_item = frappe.get_value("Item", {"shopify_id": product_id, "variant_of": ""}, "name")
#     if not template_item:
#         return "Template product not found in ERPNext."

#     item = frappe.get_doc("Item", template_item)
#     item.item_name = order_data.get("title")
#     item.description = order_data.get("body_html")
#     item.disabled = order_data.get("status") == "draft"

#     # Update image
#     images = order_data.get("images", [])
#     if images:
#         img_link = images[0].get("src")
#         if img_link:
#             file_doc = frappe.get_doc({
#                 "doctype": "File",
#                 "file_url": img_link,
#                 "is_private": 0
#             })
#             file_doc.insert(ignore_permissions=True)
#             item.image = file_doc.file_url

#     # HSN update from first variant
#     first_variant = order_data.get("variants", [])[0]
#     inventory_item_id = first_variant.get("inventory_item_id")
#     hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
#     if hsn_code_shopify:
#         if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
#             hs = frappe.new_doc("GST HSN Code")
#             hs.hsn_code = hsn_code_shopify
#             hs.insert(ignore_permissions=True)
#         item.gst_hsn_code = hsn_code_shopify

#     # Update attributes
#     shopify_options = order_data.get("options", [])
#     current_attr_names = []
#     for opt in shopify_options:
#         attr_name = opt["name"]
#         current_attr_names.append(attr_name)

#         attr_doc = frappe.get_doc("Item Attribute", {"attribute_name": attr_name}) \
#             if frappe.db.exists("Item Attribute", {"attribute_name": attr_name}) \
#             else frappe.new_doc("Item Attribute")

#         attr_doc.attribute_name = attr_name
#         existing_values = [d.attribute_value for d in attr_doc.item_attribute_values]
#         for val in opt.get("values", []):
#             if val not in existing_values:
#                 attr_doc.append("item_attribute_values", {"attribute_value": val, "abbr": val})
#         attr_doc.flags.ignore_permissions = True
#         attr_doc.save()

#     # Remove old attributes from template
#     item.attributes = []
#     for attr in current_attr_names:
#         item.append("attributes", {"attribute": attr})

#     item.flags.ignore_permissions = True
#     item.save()

#     # Sync variants
#     existing_variants = frappe.get_all("Item", filters={"variant_of": item.name}, fields=["name", "shopify_variant_id"])
#     existing_map = {v.shopify_variant_id: v.name for v in existing_variants}
#     incoming_ids = []

#     created, updated = 0, 0

#     for v in order_data.get("variants", []):
#         variant_id = v.get("id")
#         incoming_ids.append(variant_id)

#         if variant_id in existing_map:
#             variant = frappe.get_doc("Item", existing_map[variant_id])
#             updated += 1
#         else:
#             variant = frappe.new_doc("Item")
#             created += 1
#             variant.variant_of = item.name

#         variant.item_code = v.get("sku") or f"{item.item_code}-{variant_id}"
#         variant.item_name = v.get("title")
#         variant.item_group = item.item_group
#         variant.stock_uom = item.stock_uom
#         variant.shopify_selling_rate = v.get("price")
#         variant.shopify_id = product_id
#         variant.shopify_variant_id = variant_id
#         variant.custom_inventory_item_id = v.get("inventory_item_id")

#         variant.attributes = []
#         print("?//////////////")
#         for i, val in enumerate([v.get("option1"), v.get("option2"), v.get("option3")]):
#             if val and i < len(shopify_options):
#                 attr_name = shopify_options[i]["name"]
#                 variant.append("attributes", {
#                     "attribute": attr_name,
#                     "attribute_value": val
#                 })

#         # Update HSN
#         inventory_item_id = v.get("inventory_item_id")
#         hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
#         if hsn_code_shopify:
#             if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
#                 hs = frappe.new_doc("GST HSN Code")
#                 hs.hsn_code = hsn_code_shopify
#                 hs.insert(ignore_permissions=True)
#             variant.gst_hsn_code = hsn_code_shopify

#         variant.flags.ignore_permissions = True
#         variant.insert(ignore_mandatory=True)
#         variant.save()

#     # Delete removed variants
#     deleted = 0
#     for variant_id, item_name in existing_map.items():
#         if variant_id not in incoming_ids:
#             frappe.delete_doc("Item", item_name, ignore_permissions=True)
#             deleted += 1

#     return {
#         "message": "Product updated",
#         "template": item.name,
#         "created_variants": created,
#         "updated_variants": updated,
#         "deleted_variants": deleted
#     }

# @frappe.whitelist(allow_guest=True)
# def get_hsn_from_shopify(inventory_item_id, settings):
#     url = f"https://{settings.shop_url}/admin/api/2024-01/inventory_items/{inventory_item_id}.json"
#     headers = {
#         "X-Shopify-Access-Token": settings.access_token,
#         "Content-Type": "application/json"
#     }
#     try:
#         response = requests.get(url, headers=headers)
#         if response.status_code == 200:
#             return response.json().get("inventory_item", {}).get("harmonized_system_code")
#         else:
#             frappe.log_error(f"HSN Fetch Failed: {response.text}", "Shopify HSN Fetch")
#             return None
#     except Exception as e:
#         frappe.log_error(f"HSN Fetch Error: {str(e)}", "Shopify HSN Fetch")
#         return None


# import frappe
# from frappe.model.document import Document
# from frappe import _

# @frappe.whitelist(allow_guest=True)
# def product_update():
#     import json
#     from frappe.utils import flt
#     frappe.set_user("Administrator")

#     data = json.loads(frappe.request.data)
#     print(data)


#     shopify_product_id = str(data.get("id"))
#     title = data.get("title")
#     options = data.get("options", [])
#     variants = data.get("variants", [])


#     for option in options:
#         attribute_name = option.get("name")
#         values = option.get("values", [])

#         if not attribute_name:
#             continue

#         if frappe.db.exists("Item Attribute", {"attribute_name": attribute_name}):
#             attr = frappe.get_doc("Item Attribute", {"attribute_name": attribute_name})
#         else:
#             attr = frappe.new_doc("Item Attribute")
#             attr.attribute_name = attribute_name

#         existing_values = [v.attribute_value for v in attr.item_attribute_values]
#         for value in values:
#             if value and value not in existing_values:
#                 abbr = value[:3].upper() if value else "DEF"
#                 attr.append("item_attribute_values", {
#                     "attribute_value": value,
#                     "abbr": abbr
#                 })

#         for val in attr.item_attribute_values:
#             if not val.abbr:
#                 val.abbr = val.attribute_value[:3].upper() if val.attribute_value else "DEF"

#         attr.save(ignore_permissions=True)


#     if not shopify_product_id or not variants:
#         frappe.throw(_("Invalid product update payload"))

#     template = frappe.get_all("Item", filters={"shopify_id": shopify_product_id, "variant_of": ""}, limit=1)
#     if template:
#         item = frappe.get_doc("Item", template[0].name)
#         item.item_name = title
#         item.item_group = item.item_group or "All Item Groups"
#         item.has_variants = 1
#     else:
#         item = frappe.new_doc("Item")
#         item.item_name = title
#         item.item_code = f"SHOPIFY-{shopify_product_id}"
#         item.item_group = "All Item Groups"
#         item.shopify_product_id = shopify_product_id
#         item.has_variants = 1
#         item.is_stock_item = 1


#     attributes = []
#     for opt in options:
#         attribute_name = opt.get("name")
#         values = opt.get("values", [])

#         if not frappe.db.exists("Item Attribute", attribute_name):
#             attr = frappe.new_doc("Item Attribute")
#             attr.attribute_name = attribute_name
#             attr.insert(ignore_permissions=True)
#         else:
#             attr = frappe.get_doc("Item Attribute", attribute_name)


#         existing_values = [d.attribute_value for d in attr.item_attribute_values]
#         for v in values:
#             if v not in existing_values:
#                 attr.append("item_attribute_values", {"attribute_value": v})
#         attr.save(ignore_permissions=True)

#         attributes.append({
#             "attribute": attribute_name,
#             "insert_after": "",
#         })

#     item.attributes = []
#     for a in attributes:
#         item.append("attributes", a)

#     # item.save(ignore_permissions = True)
#     item.flags.ignore_permissions = True
#     item.flags.from_shopify = False
#     item.save()
#     # item.submit()
#     frappe.db.commit()

#     existing_variants = frappe.get_all("Item", filters={"variant_of": item.name}, fields=["name", "custom_variant_id"])
#     existing_variant_map = {v.custom_variant_id: v.name for v in existing_variants if v.custom_variant_id}

#     incoming_ids = []
#     for variant in variants:
#         v_id = str(variant["id"])
#         incoming_ids.append(v_id)

#         attrs = []
#         if "option1" in variant and variant["option1"]:
#             attrs.append(variant["option1"])
#         if "option2" in variant and variant["option2"]:
#             attrs.append(variant["option2"])
#         if "option3" in variant and variant["option3"]:
#             attrs.append(variant["option3"])

#         attribute_values = []
#         for i, value in enumerate(attrs):
#             attribute_values.append({
#                 "attribute": options[i]["name"],
#                 "attribute_value": value
#             })

#         if v_id in existing_variant_map:
#             v_item = frappe.get_doc("Item", existing_variant_map[v_id])
#         else:
#             v_item = frappe.new_doc("Item")
#             v_item.variant_of = item.name

#         v_item.custom_variant_id = v_id
#         v_item.item_name = variant.get("name") or title
#         v_item.item_code = f"{item.item_code}-{v_id[-6:]}"  # unique code
#         v_item.is_stock_item = 1
#         v_item.attributes = []

#         for av in attribute_values:
#             v_item.append("attributes", av)

#         if variant.get("price"):
#             v_item.standard_rate = flt(variant["price"])

#         v_item.flags.from_shopify = False
#         v_item.save(ignore_permissions=True)


#     for v_id, v_name in existing_variant_map.items():
#         if v_id not in incoming_ids:
#             frappe.delete_doc("Item", v_name, ignore_permissions=True)
#     frappe.flags.from_shopify = False
#     frappe.db.commit()
#     return {"status": "success", "message": "Product and variants updated successfully"}


# def create_invoice(order=None,sal_order = None,company_abbr=None,settings=None):

#     sales_order = frappe.get_doc("Sales Order", sal_order)
#     sales_order.submit()

#     # invoice = frappe.new_doc("Sales Invoice")
#     # invoice.customer = sales_order.customer
#     # invoice.company = sales_order.company
#     # invoice.set_posting_time = 1
#     # invoice.set_is_pos = 0
#     # invoice.set_is_return = 0
#     # invoice.set_is_recurring = 0
#     # invoice.set_is_opening = 0
#     # invoice.set_is_internal_customer = 0
#     # invoice.set_is_advance = 0
#     # invoice.set_is_fixed_asset = 0
#     # invoice.set_is_deferred_income = 0

#     # for item in sales_order.items:
#     #     invoice.append("items", {
#     #         "item_code": item.item_code,
#     #         "qty": item.qty,
#     #         "rate": item.rate,
#     #         "uom": item.uom,
#     #         "warehouse": item.warehouse,
#     #         "conversion_factor": item.conversion_factor,
#     #         "item_tax_template": item.item_tax_template,
#     #         "gst_treatment":"Taxable"
#     #     })

#     # # Set other fields as needed
#     # if order_data.get("financial_status") == "paid":
#     #     sales_order.submit()

#     sal_inv= frappe.new_doc("Sales Invoice")
#     sal_inv.company = settings.company
#     sal_inv.customer = sales_order.customer
#     sal_inv.update_stock == 1
#     sal_inv.debit_to = f"Debtors - {company_abbr}"
#     for row in sales_order.items:
#         sal_inv.append("items", {
#                 "item_code": row.item_code,
#                 "delivery_date": row.delivery_date,
#                 "uom": row.uom,
#                 "qty": row.qty,
#                 "rate": row.rate,
#                 "warehouse": row.warehouse,
#                 "item_tax_template":row.item_tax_template or "",
# #
#                 "gst_treatment":row.gst_treatment or ""
#             })

#     sal_inv.flags.ignore_permissions = True
#     sal_inv.flags.ignore_mandatory = True

#     sal_inv.insert()
#     # sal_inv.save()
#     sal_inv.submit()

# if sal_inv:
#     pay_entry = frappe.new_doc("Payment Entry")
#     pay_entry.party_type = "Customer"
#     pay_entry.posting_date = nowdate()
#     pay_entry.payment_type = "Receive"
#     pay_entry.mode_of_payment = "Cash"
#     pay_entry.party = sal_inv.customer
#     pay_entry.paid_amount = sal_inv.rounded_total
#     pay_entry.received_amount = sal_inv.rounded_total
#     pay_entry.paid_from = sal_inv.debit_to
#     pay_entry.cost_center = frappe.db.get_value("Company", settings.company, "cost_center") or f"Main - {company_abbr}"
#     pay_entry.append("references", {
#         "reference_doctype": "Sales Invoice",
#         "reference_name": sal_inv.name,
#         "total_amount": sal_inv.rounded_total,
#         "allocated_amount": sal_inv.rounded_total
#     })

#     pay_entry.flags.ignore_permissions = True
#     pay_entry.flags.ignore_mandatory = True
#     pay_entry.insert()
#     pay_entry.save()
#     pay_entry.submit()
# invoice.submit()


###############################################################################################################################


##############################################################################################
# @frappe.whitelist(allow_guest=True)
# def receive_shopify_order():
#     order_data = frappe.local.request.get_json()
#     print(order_data)
#     settings = frappe.get_doc("Shopify Connector Setting")
#     password = settings.access_token

#     company_abbr = frappe.db.get_value("Company", settings.company, "abbr")
#     sys_lang = frappe.get_single("System Settings").language or "en"
#     shopify_url = settings.shop_url
#     order_number = order_data.get("order_number")
#     customer = order_data.get("customer", {})
#     customer_name = customer.get("first_name", "") + " " + customer.get("last_name", "")
#     contact_email = customer.get("email")
#     created_date = order_data.get("created_at", "").split("T")[0]
#     items = order_data.get("line_items", [])
#     shipping_lines = sum(
#         float(line.get("price", 0)) for line in order_data.get("shipping_lines", [])
#     )
#     total_tax = sum(
#         float(tax.get("price", 0)) for tax in order_data.get("tax_lines", [])
#     )
#     billing = order_data.get("billing_address")
#     raw_billing_data = billing

#     shipping = order_data.get("shipping_address", False)
#     raw_shipping_data = shipping

#     discount_info = order_data.get("discount_applications", [])
#     discount_percentage = sum(
#         float(dis.get("value", 0))
#         for dis in discount_info
#         if dis.get("value_type") == "percentage"
#     )
#     discount_fixed = sum(
#         float(dis.get("value", 0))
#         for dis in discount_info
#         if dis.get("value_type") == "fixed_amount"
#     )

#     if frappe.db.exists("Sales Order", {"shopify_id": order_number}):
#         return "Order already exists."

#     if not customer_name:
#         frappe.throw(_(f"Customer name is missing in the order id {order_number}."))

#     get_customer = frappe.db.get_value("Customer", {"shopify_email": customer.get("email")})
#     if not get_customer:
#         link_customer_and_address(raw_shipping_data, customer_name, contact_email)

#     exists_item = frappe.db.exists("Item", {"name": "Shipping Charge"})
#     print("\n\n\n get_customer ",get_customer)
#     print("\n\n\n get_customer ",exists_item)
#     if not exists_item:
#         ship_item = frappe.new_doc("Item")
#         ship_item.item_code = "Shipping Charge"
#         ship_item.item_name = "Shipping Charge"
#         ship_item.item_group = "Shopify Products"
#         ship_item.is_stock_item = 0

#         ship_item.flags.ignore_mandatory = True
#         ship_item.insert(ignore_permissions=True)

#     sales_order = frappe.new_doc("Sales Order")
#     sales_order.customer = customer_name.strip() or "Guest"
#     sales_order.shopify_id = order_number
#     sales_order.company = settings.company
#     sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
#     sales_order.transaction_date = created_date
#     sales_order.additional_discount_percentage = discount_percentage or ""
#     sales_order.discount_amount = discount_fixed or ""
#     sales_order.delivery_date = frappe.utils.add_days(
#         created_date, settings.delivery_after_days or 7
#     )


#     for item in items:
#         product_id = item.get("product_id")
#         item_name = item.get("name")
#         exist_item = frappe.db.get_value("Item", {"shopify_id": product_id})

#         if not exist_item:
#             product_creation()
#             # new_item = frappe.new_doc("Item")
#             # new_item.item_code = f"Shopify-{product_id}"
#             # new_item.item_name = item_name
#             # new_item.stock_uom = settings.uom or _("Nos", sys_lang)
#             # new_item.item_group = _("Shopify Products", sys_lang)
#             # new_item.shopify_id = product_id
#             # new_item.shopify_selling_rate = item.get("price", 0)
#             # new_item.flags.ignore_mandatory = True
#             # new_item.insert(ignore_permissions=True)
#             # new_item.save()


#             # response = requests.get(
#             #     f"https://{shopify_url}/admin/api/2021-10/products/{product_id}.json",
#             #     headers={"X-Shopify-Access-Token": password},
#             # )

#             # if response.status_code == 200:
#             #     product_data = response.json()["product"]
#             #     product_images = product_data.get("images", [])
#             #     img_link = product_images[0]["src"] if product_images else ""

#             #     if img_link:
#             #         file_doc = frappe.new_doc("File")
#             #         file_doc.file_url = img_link
#             #         file_doc.is_private = 0
#             #         file_doc.flags.ignore_mandatory = True
#             #         file_doc.insert()
#             #         file_doc.save()

#             #         new_item.image = file_doc.file_url

#             #         new_item.flags.ignore_permissions = True
#             #         new_item.save()
#             # else:
#             #     print(f"Failed to fetch product details: {response.status_code} - {response.text}")


#         sales_order.append(
#             "items",
#             {
#                 "item_code": exist_item,
#                 "delivery_date": sales_order.delivery_date,
#                 "uom": settings.uom or _("Nos", sys_lang),
#                 "qty": item.get("quantity", 1),
#                 "rate": item.get("price", 0),
#                 "warehouse": settings.warehouse or f"Stores - {company_abbr}",
#             },
#         )

#     if order_data.get("tax_lines"):
#         for tax in order_data.get("tax_lines", []):
#             sales_order.append(
#                 "taxes",
#                 {
#                     "charge_type": "Actual",
#                     "account_head": "",
#                     "rate": (tax.get("rate") or 0) * 100,
#                     "tax_amount": tax.get("price"),
#                 },
#             )
#     sales_order.flags.ignore_mandatory = True
#     sales_order.flags.ignore_permissions = True
#     sales_order.insert()
#     sales_order.save()

#     frappe.msgprint(_("Sales Order created for order number: {0}").format(order_number))
#     return "Success"


# @frappe.whitelist(allow_guest=True)
# def product_creation():
# 	shopify_keys = frappe.get_single("Shopify Connector Setting")
# 	if shopify_keys.sync_product:
# 		order_data = frappe.local.request.get_json()
# 		print("\n\n\norder_data",order_data)
# 		product_id = order_data.get("id")
# 		for v in order_data.get("variants", []):
# 			inventory_item_id = v.get("inventory_item_id")

# 		sys_lang = frappe.get_single("System Settings").language or "en"
# 		settings = frappe.get_doc("Shopify Connector Setting")
# 		status = False
# 		price = 0
# 		hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
# 		if hsn_code_shopify:
# 			if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
# 				hs = frappe.new_doc("GST HSN Code")
# 				hs.hsn_code = hsn_code_shopify
# 				hs.insert(ignore_permissions=True)

# 		for prices in order_data.get("variants", []):
# 			price = prices.get("price")

# 		if order_data.get("status") == "draft":
# 			status = True

# 		if frappe.db.exists("Item", {"shopify_id": product_id}):
# 			return "Product already exists."

# 		item = frappe.new_doc("Item")
# 		item.item_code = order_data.get("title")
# 		item.item_name = order_data.get("title")
# 		item.gst_hsn_code = hsn_code_shopify
# 		item.description = order_data.get("body_html")
# 		item.item_group = _("Shopify Products", sys_lang)
# 		item.stock_uom = settings.uom
# 		item.shopify_id = product_id
# 		item.custom_inventory_item_id =inventory_item_id
# 		item.shopify_selling_rate = price

# 		options = order_data.get("options", [])
# 		has_real_variants = any(opt.get("name") != "Title" and len(opt.get("values", [])) > 1 for opt in options)
# 		item.has_variants = 1 if has_real_variants else 0

# 		item.disabled = status

# 		options = order_data.get("options", [])

# 		if item.has_variants:
# 			for opt in options:
# 				attr_name = opt["name"]

# 				if not frappe.db.exists("Item Attribute", {"attribute_name": attr_name}):
# 					attr_doc = frappe.new_doc("Item Attribute")
# 					attr_doc.attribute_name = attr_name
# 					attr_doc.flags.ignore_permissions = True
# 					attr_doc.insert()
# 				else:

# 					attr_doc = frappe.get_doc("Item Attribute", {"attribute_name": attr_name})


# 				existing_values = frappe.get_all(
# 					"Item Attribute Value", filters={"parent": attr_name}, pluck="attribute_value"
# 				)

# 				for val in opt["values"]:
# 					if val not in existing_values:
# 						attr_doc.append("item_attribute_values", {
# 							"attribute_value": val,
# 							"abbr": val
# 						})
# 				attr_doc.flags.ignore_permissions = True
# 				attr_doc.save()


# 				item.append("attributes", {"attribute": attr_name})

# 		images = order_data.get("images", [])
# 		img_link = images[0]["src"] if images else ""
# 		if img_link:
# 			file_doc = frappe.get_doc({
# 				"doctype": "File",
# 				"file_url": img_link,
# 				"is_private": 0
# 			})
# 			file_doc.insert(ignore_permissions=True)
# 			item.image = file_doc.file_url


# 		item.flags.ignore_permissions = True
# 		item.flags.from_shopify = True
# 		item.insert(ignore_mandatory=True)
# 		item.save()

# 		if item.has_variants:
# 			for v in order_data.get("variants", []):
# 				variant = frappe.new_doc("Item")
# 				# variant.item_code = v.get("sku") or f"{item.item_code}-{v.get('id')}"
# 				variant.item_code = v.get("title")
# 				variant.item_name = v.get("title")
# 				variant.item_group = _("Shopify Products", sys_lang)
# 				variant.variant_of = item.name
# 				variant.stock_uom = item.stock_uom
# 				variant.shopify_selling_rate = v.get("price")
# 				# variant.shopify_id = product_id
# 				variant.custom_variant_id = v.get("id")
# 				variant.custom_inventory_item_id = v.get("inventory_item_id")


# 				variant_options = [v.get("option1"), v.get("option2"), v.get("option3")]

# 				for opt_value in variant_options:
# 					if not opt_value:
# 						continue  # skip empty/null options

# 					matched_attr = None
# 					for opt in options:
# 						attr_name = opt["name"]
# 						attr_doc = frappe.get_doc("Item Attribute", attr_name)
# 						attribute_values = [d.attribute_value for d in attr_doc.item_attribute_values]
# 						if opt_value in attribute_values:
# 							matched_attr = attr_name
# 							break

# 					if matched_attr:
# 						variant.append("attributes", {
# 							"attribute": matched_attr,
# 							"attribute_value": opt_value
# 						})


# 				inventory_item_id = v.get("inventory_item_id")
# 				if inventory_item_id:
# 					hsn_code_shopify = get_hsn_from_shopify(inventory_item_id, settings)
# 					if hsn_code_shopify:
# 						if not frappe.db.exists("GST HSN Code", {"hsn_code": hsn_code_shopify}):
# 							hs = frappe.new_doc("GST HSN Code")
# 							hs.hsn_code = hsn_code_shopify
# 							hs.insert(ignore_permissions=True)

# 						variant.gst_hsn_code = hsn_code_shopify

# 				variant.flags.ignore_permissions = True
# 				variant.flags.from_shopify = True
# 				variant.insert(ignore_mandatory=True)
# 				variant.save()

# 		return "Product created with variants and HSN."
