import frappe
import requests
from frappe import _


@frappe.whitelist(allow_guest=True)
def receive_shopify_order():
    order_data = frappe.local.request.get_json()
    print(order_data)
    settings = frappe.get_doc("Shopify Connector Setting")
    password = settings.access_token

    company_abbr = frappe.db.get_value("Company", settings.company, "abbr")
    sys_lang = frappe.get_single("System Settings").language or "en"
    shopify_url = settings.shop_url
    order_number = order_data.get("order_number")
    customer = order_data.get("customer", {})
    customer_name = customer.get("first_name", "") + " " + customer.get("last_name", "")
    contact_email = customer.get("email")
    created_date = order_data.get("created_at", "").split("T")[0]
    items = order_data.get("line_items", [])
    shipping_lines = sum(
        float(line.get("price", 0)) for line in order_data.get("shipping_lines", [])
    )
    total_tax = sum(
        float(tax.get("price", 0)) for tax in order_data.get("tax_lines", [])
    )
    billing = order_data.get("billing_address")
    raw_billing_data = billing

    shipping = order_data.get("shipping_address", False)
    raw_shipping_data = shipping

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

    if frappe.db.exists("Sales Order", {"shopify_id": order_number}):
        return "Order already exists."

    if not customer_name:
        frappe.throw(_(f"Customer name is missing in the order id {order_number}."))

    get_customer = frappe.db.get_value("Customer", {"shopify_email": customer.get("email")})
    if not get_customer:
        link_customer_and_address(raw_shipping_data, customer_name, contact_email)
    
    exists_item = frappe.db.exists("Item", {"name": "Shipping Charge"})
    
    if not exists_item:
        ship_item = frappe.new_doc("Item")
        ship_item.item_code = "Shipping Charge"
        ship_item.item_name = "Shipping Charge"
        ship_item.item_group = "Shopify Products"
        ship_item.is_stock_item = 0
        
        ship_item.flags.ignore_permissions = 1
        ship_item.insert(ignore_permissions=True)

    sales_order = frappe.new_doc("Sales Order")
    sales_order.customer = customer_name.strip() or "Guest"
    sales_order.shopify_id = order_number
    sales_order.company = settings.company
    sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
    sales_order.transaction_date = created_date
    sales_order.additional_discount_percentage = discount_percentage or ""
    sales_order.discount_amount = discount_fixed or ""
    sales_order.delivery_date = frappe.utils.add_days(
        created_date, settings.delivery_after_days or 7
    )

                
    for item in items:
        product_id = item.get("product_id")
        item_name = item.get("name")
        exist_item = frappe.db.get_value("Item", {"shopify_id": product_id})

        if not exist_item:
            new_item = frappe.new_doc("Item")
            new_item.item_code = f"Shopify-{product_id}"
            new_item.item_name = item_name
            new_item.stock_uom = settings.uom or _("Nos", sys_lang)
            new_item.item_group = _("Shopify Products", sys_lang)
            new_item.shopify_id = product_id
            new_item.shopify_selling_rate = item.get("price", 0)
            new_item.flags.ignore_permissions = 1
            new_item.insert(ignore_permissions=True)
            new_item.save()

            # Fetch product details from Shopify
            response = requests.get(
                f"https://{shopify_url}/admin/api/2021-10/products/{product_id}.json",
                headers={"X-Shopify-Access-Token": password},
            )

            if response.status_code == 200:
                product_data = response.json()["product"]
                product_images = product_data.get("images", [])
                img_link = product_images[0]["src"] if product_images else ""

                if img_link:
                    file_doc = frappe.new_doc("File")
                    file_doc.file_url = img_link
                    file_doc.is_private = 0
                    file_doc.flags.ignore_permissions = True
                    file_doc.insert(ignore_permissions=True)
                    file_doc.save()

                    new_item.image = file_doc.file_url

                    new_item.flags.ignore_permissions = 1
                    new_item.save()
            else:
                print(f"Failed to fetch product details: {response.status_code} - {response.text}")


        sales_order.append(
            "items",
            {
                "item_code": exist_item,
                "delivery_date": sales_order.delivery_date,
                "uom": settings.uom or _("Nos", sys_lang),
                "qty": item.get("quantity", 1),
                "rate": item.get("price", 0),
                "warehouse": settings.warehouse or f"Stores - {company_abbr}",
            },
        )

    if order_data.get("tax_lines"):
        for tax in order_data.get("tax_lines", []):
            sales_order.append(
                "taxes",
                {
                    "charge_type": "Actual",
                    "account_head": "",
                    "rate": (tax.get("rate") or 0) * 100,
                    "tax_amount": tax.get("price"),
                },
            )

    sales_order.flags.ignore_permissions = True
    sales_order.insert()
    sales_order.save()

    frappe.msgprint(_("Sales Order created for order number: {0}").format(order_number))
    return "Success"


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
    order_data = frappe.local.request.get_json()
    if not frappe.db.exists("Customer", {"shopify_email": order_data.get("email")}):
        cus = frappe.new_doc("Customer")
        cus.shopify_email = order_data.get("email")
        cus.customer_name = (
            order_data.get("first_name", "") + " " + order_data.get("last_name", "")
        )
        cus.default_currency = order_data.get("currency")
        cus.flags.ignore_permissions = True
        cus.insert(ignore_mandatory=True)
        cus.save()
        customer = frappe.get_doc("Customer", cus.name)
        if order_data.get("default_address"):
            address = order_data.get("default_address")
            cus_address = frappe.new_doc(
                "Address",
            )
            cus_address.address_title = (
                order_data.get("first_name", "") + " " + order_data.get("last_name", "")
            )
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
            cus_contact.middle_name = address.get("middlw_name") or ""
            cus_contact.last_name = address.get("last_name")
            cus_contact.address = cus_address
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
                }
            )
            cus_contact.flags.ignore_permissions = True
            cus_contact.insert(ignore_mandatory=True)
            cus_contact.save()

        cus.save()
        frappe.msgprint( 
            _("Customer created for email: {0}").format(order_data.get("email"))
        )
    else:
        frappe.msgprint(
            _("Customer already exists for email: {0}").format(order_data.get("email"))
        )


@frappe.whitelist(allow_guest=True)
def product_creation():
    order_data = frappe.local.request.get_json()
    product_id = order_data.get("id")
    sys_lang = frappe.get_single("System Settings").language or "en"
    status = False
    settings = frappe.get_doc("Shopify Connector Setting")
    price = 0
    for prices in order_data.get("variants"):
        price = prices.get("price")

    if order_data.get("status") == "draft":
        status = True

    if frappe.db.get_value("Item", {"shopify_id": product_id}):
        return "Order already exists."

    item = frappe.new_doc("Item")
    item.item_code = f"Shopify-{product_id}"
    item.item_name = order_data.get("title")
    item.description = order_data.get("body_html")
    item.item_group = _("Shopify Products", sys_lang)
    item.stock_uom = settings.uom
    item.shopify_id = order_data.get("product_id")
    item.shopify_selling_rate = price
    item.disabled = status
    response = requests.get(
        f"https://{settings.shop_url}/admin/api/2021-10/products/{product_id}.json",
        headers={"X-Shopify-Access-Token": settings.access_token},
    )
    if response.status_code == 200:
        product_data = response.json()["product"]
        product_images = product_data.get("images", [])
        img_link = product_images[0]["src"] if product_images else ""

        if img_link:
            file_doc = frappe.new_doc("File")
            file_doc.file_url = img_link
            file_doc.is_private = 0
            file_doc.flags.ignore_permissions = True
            file_doc.insert(ignore_permissions=True)
            file_doc.save()
            item.image = file_doc.file_url if file_doc else ""
        else:
            print(f"Failed to fetch product details: {response.status_code} - {response.text}")

    item.flags.ignore_permissions = True
    item.insert(ignore_mandatory=True)
    item.save()


@frappe.whitelist(allow_guest=True)
def product_update():
    order_data = frappe.local.request.get_json()
    # print(order_data)
    product_id = order_data.get("id")
    sys_lang = frappe.get_single("System Settings").language or "en"
    status = False
    price = 0
    for prices in order_data.get("variants"):
        price = prices.get("price")

    existing_product = frappe.db.get_value("Item", f"Shopify-{product_id}")
    if existing_product:
        item = frappe.get_doc("Item", f"Shopify-{product_id}")
        item.item_name = order_data.get("title")
        item.item_group = _("Shopify Products", sys_lang)
        item.shopify_selling_rate = price
        item.disabled = status
        item.description = order_data.get("body_html")
        item.flags.ignore_permissions = True
        item.save()

@frappe.whitelist(allow_guest=True)
def customer_update():
    order_data = frappe.local.request.get_json()
    print(order_data)

    if frappe.db.exists("Customer", {"shopify_email": order_data.get("email")}):
        cus = frappe.get_doc("Customer", {"shopify_email": order_data.get("email")})
        cus.db_set("shopify_email", order_data.get("email"))
        cus.db_set(
            "customer_name",
            order_data.get("first_name", "") + " " + order_data.get("last_name", ""),
        )
        cus.db_set("default_currency", order_data.get("currency"))
        cus.flags.ignore_mandatory = True
        # cus.insert(ignore_permissions=True)
        # cus.save()
        customer = frappe.get_doc("Customer", cus.name)
        if order_data.get("default_address"):
            print(order_data.get("default_address"))
            address = order_data.get("default_address")
            cus_address = frappe.get_doc("Address", cus)
            cus_address.db_set(
                "address_title",
                address.get("first_name", "") + " " + address.get("last_name", ""),
            )
            cus_address.db_set("address_type", "Shipping")
            cus_address.db_set("address_line1", address.get("address1"))
            cus_address.db_set("address_line2", address.get("address2"))
            cus_address.db_set("city", address.get("city"))
            cus_address.db_set("state", address.get("province"))
            cus_address.db_set("country", address.get("country"))
            cus_address.db_set("pincode", address.get("zip"))
            cus_address.db_set("phone", address.get("phone"))
            cus.flags.ignore_mandatory = True
        # cus.save()
        frappe.msgprint(
            _("Customer created for email: {0}").format(order_data.get("email"))
        )
    else:
        frappe.msgprint(
            _("Customer already exists for email: {0}").format(order_data.get("email"))
        )


@frappe.whitelist(allow_guest=True)
def order_update():
    order_data = frappe.local.request.get_json()
    print(order_data)
    cus = frappe.get_doc("Customer", {"shopify_email": order_data.get("email")})
    settings = frappe.get_doc("Shopify Connector Setting")
    password = settings.access_token
    shopify_url = settings.shop_url

    company_abbr = frappe.db.get_value("Company", settings.company, "abbr")
    sys_lang = frappe.get_single("System Settings").language or "en"

    order_number = order_data.get("order_number")
    customer = order_data.get("customer", {})
    customer_name = customer.get("first_name", "") + " " + customer.get("last_name", "")
    contact_email = customer.get("email")
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
    sales_order.customer = customer_name.strip() or "Guest"
    sales_order.shopify_id = order_number
    sales_order.company = settings.company
    sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
    sales_order.transaction_date = created_date
    sales_order.delivery_date = frappe.utils.add_days(
        created_date, settings.delivery_after_days or 7
    )
    sales_order.additional_discount_percentage = discount_percentage or 0
    sales_order.discount_amount = discount_fixed or 0
    

    if order_data.get("shipping_address") or order_data.get("billing_address"):
        address = order_data.get("shipping_address")
        cus_address = frappe.get_doc("Address", {"name": sales_order.customer_address})
        cus_address.db_set(
            "address_title",
            address.get("first_name", "") + " " + address.get("last_name", ""),
        )
        cus_address.address_type =  "Shipping"
        cus_address.address_line1 =  address.get("address1")
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
        product_id = item.get("product_id")
        item_name = item.get("name")
        quantity = item.get("quantity")
        price = item.get("price")
        item_code = f"Shopify-{product_id}"

        exist_item = frappe.db.get_value("Item", {"name": item_code})

        if not exist_item:
            new_item = frappe.new_doc("Item")
            new_item.item_code = item_code
            new_item.item_name = item_name
            new_item.rate = price
            new_item.qty = quantity
            new_item.stock_uom = settings.uom or _("Nos", sys_lang)
            new_item.item_group = _("Shopify Products", sys_lang)
            new_item.flags.ignore_mandatory = True
            new_item.flags.ignore_permissions = True
            new_item.insert()
            # exist_item = new_item.name

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
            },
        )

    sales_order.set("taxes", [])
    tax_account = settings.tax_account or f"Sales Tax - {company_abbr}"
    for tax in order_data.get("tax_lines", []):
        sales_order.append(
            "taxes",
            {
                "charge_type": "Actual",
                "account_head": tax_account,
                "description": tax.get("title") or "Shopify Tax",
                "rate": (tax.get("rate") or 0) * 100,
                "tax_amount": float(tax.get("price", 0)),
            },
        )

    sales_order.flags.ignore_permissions = True
    sales_order.save()

    frappe.msgprint(_("Sales Order updated for order number: {0}").format(order_number))
    return "Success"
