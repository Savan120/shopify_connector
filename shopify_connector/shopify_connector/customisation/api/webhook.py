import frappe
import requests
from frappe import _

@frappe.whitelist(allow_guest=True)
def receive_shopify_order():
    order_data = frappe.local.request.get_json()
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
    shipping_lines = sum(float(line.get('price', 0)) for line in order_data.get('shipping_lines', []))
    total_tax = sum(float(tax.get("price", 0)) for tax in order_data.get("tax_lines", []))
    billing = order_data.get('billing_address')
    raw_billing_data = billing

    shipping = order_data.get('shipping_address',False)
    raw_shipping_data = shipping
    
    discount_info = order_data.get("discount_applications", [])
    discount_percentage = sum(float(dis.get("value", 0)) for dis in discount_info if dis.get("value_type") == "percentage")
    discount_fixed = sum(float(dis.get("value", 0)) for dis in discount_info if dis.get("value_type") == "fixed_amount")
    
    if frappe.db.exists("Sales Order", {"shopify_id": order_number}):
        return "Order already exists."
    
    if not customer_name:
        frappe.throw(_(f"Customer name is missing in the order id {order_number}."))
        
    get_customer = frappe.db.get_value("Customer", {"shopify_email": customer.get("email")})
    if not get_customer:
        link_customer_and_address(raw_shipping_data, customer_name, contact_email)
       
    
    sales_order = frappe.new_doc("Sales Order")
    sales_order.customer = customer_name.strip() or "Guest"
    sales_order.shopify_id = order_number
    sales_order.company = settings.company
    sales_order.naming_series = settings.sales_order_series or "SO-SPF-"
    sales_order.transaction_date = created_date
    sales_order.additional_discount_percentage = discount_percentage or ""
    sales_order.discount_amount = discount_fixed or ""
    sales_order.delivery_date = frappe.utils.add_days(created_date, settings.delivery_after_days or 7)
    
    images_src = []
    for item in items:
        product_id = item.get("product_id")
        item_name = item.get("name")
            
            
        if not frappe.db.get_value("Item", {"shopify_id": product_id}):
            new_item = frappe.new_doc("Item")
            new_item.item_code = f"Shopify-{product_id}"
            new_item.item_name = item_name
            new_item.stock_uom = settings.uom or _( "Nos", sys_lang)
            new_item.item_group = _( "Shopify Products", sys_lang)
            new_item.shopify_id = product_id
            new_item.shopify_selling_rate = item.get("price", 0)
            
            response = requests.get(f'https://{shopify_url}/admin/api/2021-10/products/{product_id}.json', headers={'X-Shopify-Access-Token': password})
            if response.status_code == 200:
                product_data = response.json()['product']
                images_src += [image['src'] for image in product_data['images']]
            else:
                print(f"Failed to fetch product details: {response.status_code} - {response.text}")
            img_link  = images_src[0] if len(images_src)>0 else ''
            
            file_doc = frappe.new_doc("File")
            file_doc.file_url = img_link
            file_doc.is_private = 0
            file_doc.flags.ignore_permissions = True
            file_doc.insert(ignore_permissions=True)
            file_doc.save()
            new_item.image = file_doc.file_url if file_doc else '' 
                
            new_item.flags.ignore_permissions = 1
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
    
    if order_data.get("tax_lines"):
        for tax in order_data.get("tax_lines", []):
            sales_order.append("taxes", {
                "charge_type": "Actual",
                "account_head": "",
                "rate": (tax.get("rate") or 0) * 100,
                "tax_amount": tax.get("price")
            })
        
    
    sales_order.flags.ignore_permissions = True
    sales_order.insert(ignore_mandatory=True)
    sales_order.submit()
    
    frappe.msgprint(_("Sales Order created for order number: {0}").format(order_number))
    return "Success"

def link_customer_and_address( raw_shipping_data, customer_name, contact_email):
    if raw_shipping_data:
        customer_shopify_email = contact_email
        customer_exists = frappe.get_value("Customer", {"shopify_email": customer_shopify_email})
        if not customer_exists:
            customer = frappe.new_doc("Customer")
        else:
            customer = frappe.get_doc("Customer", {"shopify_email": customer_shopify_email})
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
            cus_address.flags.ignore_permissions = 1
            cus_address.insert(ignore_permissions=True)
            cus_address.save()
        
        cus.save()
        frappe.msgprint(_("Customer created for email: {0}").format(order_data.get("email")))
    else:
        frappe.msgprint(_("Customer already exists for email: {0}").format(order_data.get("email")))
        

@frappe.whitelist(allow_guest=True)
def product_creation():
    order_data = frappe.local.request.get_json()
    product_id = order_data.get("id")
    sys_lang = frappe.get_single("System Settings").language or "en"
    status = False
    images_src = []
    settings = frappe.get_doc("Shopify Connector Setting")
    price = 0
    for prices in order_data.get("variants"):
       price =  prices.get("price")

    
    if order_data.get("status") == "draft":
        status = True

    if frappe.db.get_value("Item", {"shopify_id": product_id}):
        return "Order already exists."

    
    item = frappe.new_doc("Item")
    item.item_code = f"Shopify-{product_id}"
    item.item_name= order_data.get("title")
    item.item_group =  _( "Shopify Products", sys_lang)
    item.stock_uom= settings.uom
    item.shopify_id=order_data.get("product_id")
    item.shopify_selling_rate = price
    item.disabled = status
    response = requests.get(f'https://{settings.shop_url}/admin/api/2021-10/products/{product_id}.json', headers={'X-Shopify-Access-Token': settings.access_token})
    if response.status_code == 200:
        product_data = response.json()['product']
        images_src += [image['src'] for image in product_data['images']]
    else:
        print(f"Failed to fetch product details: {response.status_code} - {response.text}")
    img_link  = images_src[0] if len(images_src)>0 else ''
    
    file_doc = frappe.new_doc("File")
    file_doc.file_url = img_link
    file_doc.is_private = 0
    file_doc.flags.ignore_permissions = True
    file_doc.insert(ignore_permissions=True)
    file_doc.save()
    item.image = file_doc.file_url if file_doc else '' 
                
    item.flags.ignore_permission = True
    item.insert(ignore_permissions=True)
    item.save()
        

