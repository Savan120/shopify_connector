import frappe
import requests
import datetime
from frappe import _

@frappe.whitelist(allow_guest=True)
def receive_shopify_order():
    order_data = frappe.local.request.get_json()
    settings = frappe.get_doc("Shopify Connector Setting")
    
    company_abbr = frappe.db.get_value("Company", settings.company, "abbr")
    sys_lang = frappe.get_single("System Settings").language or "en"
    shopify_url = settings.shop_url
    
    order_number = order_data.get("order_number")
    customer = order_data.get("customer", {})
    customer_name = customer.get("first_name", "") + " " + customer.get("last_name", "")
    created_date = order_data.get("created_at", "").split("T")[0]
    items = order_data.get("line_items", [])
    shipping_lines = sum(float(line.get('price', 0)) for line in order_data.get('shipping_lines', []))
    total_tax = sum(float(tax.get("price", 0)) for tax in order_data.get("tax_lines", []))
    
    discount_info = order_data.get("discount_applications", [])
    discount_percentage = sum(float(dis.get("value", 0)) for dis in discount_info if dis.get("value_type") == "percentage")
    discount_fixed = sum(float(dis.get("value", 0)) for dis in discount_info if dis.get("value_type") == "fixed_amount")
    
    if frappe.db.exists("Sales Order", {"shopify_id": order_number}):
        return "Order already exists."
    
    if not customer_name:
        frappe.throw(_(f"Customer name is missing in the order id {order_number}."))
        
    
    sales_order = frappe.new_doc("Sales Order")
    sales_order.customer = customer_name.strip() or "Guest"
    sales_order.shopify_id = order_number
    sales_order.company = settings.company
    sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
    sales_order.transaction_date = created_date
    sales_order.delivery_date = frappe.utils.add_days(created_date, settings.delivery_after_days or 7)
    
    for item in items:
        product_id = item.get("product_id")
        item_name = item.get("name")
        
        if not frappe.db.exists("Item", {"shopify_id": product_id}):
            frappe.throw("called")
            new_item = frappe.new_doc("Item")
            new_item.item_code = f"Shopify-{product_id}"
            new_item.item_name = item_name
            new_item.stock_uom = settings.uom or _( "Nos", sys_lang)
            new_item.item_group = _( "Shopify Products", sys_lang)
            new_item.shopify_id = product_id
            new_item.shopify_selling_rate = item.get("price", 0)
            new_item.flags.ignore_mandatory = True
            print(f"\n\n\n\n new item: {new_item.__dict__}")
            new_item.insert(ignore_permissions=True)
            new_item.save()
        
        sales_order.append("items", {
            "item_code": f"Shopify-{product_id}",
            "item_name": item_name,
            "description": item_name,
            "delivery_date": sales_order.delivery_date,
            "uom": settings.uom or _( "Nos", sys_lang),
            "qty": item.get("quantity", 1),
            "rate": item.get("price", 0),
            "warehouse": settings.warehouse or f"Stores - {company_abbr}"
        })
    
    sales_order.flags.ignore_mandatory = True
    sales_order.insert(ignore_permissions=True)
    sales_order.submit()
    
    frappe.msgprint(_("Sales Order created for order number: {0}").format(order_number))
    return "success"


@frappe.whitelist(allow_guest=True)
def customer_creation():
    order_data = frappe.local.request.get_json()
    if not frappe.db.exists("Customer", {"shopify_email": order_data.get("email")}):
        cus = frappe.new_doc("Customer")
        cus.shopify_email = order_data.get("email")
        cus.customer_name = order_data.get("first_name", "") + " " + order_data.get("last_name", "")
        cus.default_currency = order_data.get("currency")
        cus.flags.ignore_mandatory = True
        cus.insert(ignore_permissions=True)
        cus.save()
        customer = frappe.get_doc("Customer", cus.name)
        if order_data.get("default_address"):
            address = order_data.get("default_address")
            cus_address = frappe.new_doc("Address")
            cus_address.address_title = order_data.get("first_name", "") + " " + order_data.get("last_name", "")
            cus_address.address_type = "Shipping"
            cus_address.address_line1 = address.get("address1")
            cus_address.address_line2 = address.get("address2")
            cus_address.city = address.get("city")
            cus_address.state = address.get("province")
            cus_address.country = address.get("country")
            cus_address.postal_code = address.get("zip")
            cus_address.phone = address.get("phone")
            
            cus_address.append("links", {
                "link_doctype": "Customer",
                "link_name": cus.name,
            })
            cus_address.flags.ignore_mandatory = True
            cus_address.insert(ignore_permissions=True)
            cus_address.save()
        
        cus.save()
        frappe.msgprint(_("Customer created for email: {0}").format(order_data.get("email")))
    else:
        frappe.msgprint(_("Customer already exists for email: {0}").format(order_data.get("email")))