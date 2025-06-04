
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.document import Document
from frappe.utils.nestedset import get_root_of
from frappe.utils import cstr
from crypt import crypt as _crypt

import datetime
import json
from frappe.model.document import Document
from shopify_connector.shopify_connector.doctype.shopify_connector_setting.shopify_connector_setting import get_order 



# Create an instance of ShopifyConnectorSetting
shopify_setting = ShopifyConnectorSetting()

# Call the validate method on the instance
shopify_setting.validate()
print("::::::::::::::::::callllllllllllllllllll",shopify_setting.validate())

def get_order():
	get_order()
	print(":::::::::::sssssssssssssssss:::::::::::::::::")

# def order():
# 	woocommerce_settings = frappe.get_doc("Woocommerce Settings")
# 	api_key = woocommerce_settings.api_consumer_key
# 	secret_key = woocommerce_settings.api_consumer_secret
# 	url = woocommerce_settings.woocommerce_server_url
# 	wcapi = API(
# 	    url= url,
# 	    consumer_key= api_key,
# 	    consumer_secret= secret_key,
# 	    version="wc/v3"
# 	)
# 	wc_so_data = wcapi.get("Orders")
# 	wc_so_data_json = wc_so_data.json()
# 	if wc_so_data_json:
# 		sys_lang = frappe.get_single("System Settings").language or "en"
# 		for order_data in wc_so_data_json:
# 			billing = order_data.get('billing')
# 			order_id = order_data.get('id')
# 			shipping = order_data.get('shipping')
# 			line_items = order_data.get('line_items')
# 			items_list = line_items
# 			image_src = order_data['line_items'][0]['image']['src']
# 			raw_billing_data = billing
# 			raw_shipping_data = shipping
# 			customer_name = raw_billing_data.get("first_name") + " " + raw_billing_data.get("last_name")
# 			shipping_tax = order_data.get('shipping_tax')
# 			shipping_total = order_data.get('shipping_total')
# 			date_created = order_data.get('date_created').split("T")
# 			if customer_name == " ":
# 				print ("Not Customer Available::::::::::;")
# 			else:
# 				link_customer_and_address(raw_billing_data, raw_shipping_data, customer_name)
# 				link_items(items_list, woocommerce_settings, sys_lang,shipping_tax,shipping_total,image_src)
# 				create_sales_order(order_id, woocommerce_settings, customer_name, sys_lang,line_items,shipping_tax,shipping_total)

# 	else:
# 		frappe.throw(_("Woocommerce Order is not available !!"))

# def link_customer_and_address(raw_billing_data, raw_shipping_data, customer_name):
# 	customer_woo_com_email = raw_billing_data.get("email")
# 	customer_exists = frappe.get_value("Customer", {"woocommerce_email": customer_woo_com_email})
# 	if not customer_exists:
# 		# Create Customer
# 		customer = frappe.new_doc("Customer")
# 	else:
# 		# Edit Customer
# 		customer = frappe.get_doc("Customer", {"woocommerce_email": customer_woo_com_email})
# 		old_name = customer.customer_name

# 	customer.customer_name = customer_name
# 	customer.woocommerce_email = customer_woo_com_email
# 	customer.flags.ignore_mandatory = True
# 	customer.save()

# def create_contact(data, customer):
# 	email = data.get("email", None)
# 	phone = data.get("phone", None)

# 	if not email and not phone:
# 		return
# 	contact = frappe.new_doc("Contact")
# 	contact.first_name = data.get("first_name")
# 	contact.last_name = data.get("last_name")
# 	contact.is_primary_contact = 1
# 	contact.is_billing_contact = 1

# 	if phone:
# 		contact.add_phone(phone, is_primary_mobile_no=1, is_primary_phone=1)

# 	if email:
# 		contact.add_email(email, is_primary=1)

# 	contact.append("links", {"link_doctype": "Customer", "link_name": customer.name})
# 	contact.flags.ignore_mandatory = True
# 	contact.save()


# def create_address(raw_data, customer, address_type):
# 	address = frappe.new_doc("Address")
# 	address.address_title = customer.customer_name
# 	address.address_line1 = raw_data.get("address_1", "Not Provided")
# 	address.address_line2 = raw_data.get("address_2", "Not Provided")
# 	address.city = raw_data.get("city", "Not Provided")
# 	address.woocommerce_email = customer.woocommerce_email
# 	address.address_type = address_type
# 	address.country = frappe.get_value("Country", {"code": raw_data.get("country", "IN").lower()})
# 	address.state = raw_data.get("state")
# 	address.pincode = raw_data.get("postcode")
# 	address.phone = raw_data.get("phone")
# 	address.email_id = customer.woocommerce_email
# 	address.append("links", {"link_doctype": "Customer", "link_name": customer.name})

# 	address.flags.ignore_mandatory = True
# 	address.save()


# def rename_address(address, customer):
# 	old_address_title = address.name
# 	new_address_title = customer.name + "-" + address.address_type
# 	address.address_title = customer.customer_name
# 	address.save()

# 	frappe.rename_doc("Address", old_address_title, new_address_title)


# def link_items(items_list, woocommerce_settings, sys_lang,shipping_tax,shipping_total,image_src):
# 	for item_data in items_list:
# 		item_woo_com_id = cstr(item_data.get("product_id"))
# 		image_src
# 		if not frappe.db.get_value("Item", {"woocommerce_id": item_woo_com_id}, "name"):
# 			# Create Item
# 			item = frappe.new_doc("Item")
# 			item.item_code = _("woocommerce - {0}", sys_lang).format(item_woo_com_id)
# 			item.stock_uom = woocommerce_settings.uom or _("Nos", sys_lang)
# 			item.item_group = _("WooCommerce Products", sys_lang)

# 			item.item_name = item_data.get("name")
# 			item.woocommerce_id = item_woo_com_id

# 			# Upload image from image_src
# 			if image_src:
# 			    file_doc = frappe.get_doc({
# 			        "doctype": "File",
# 			        "file_url": image_src,
# 			        "is_private": 0  # Set to 0 to make it accessible to all users
# 			    })
# 			    file_doc.insert()
# 			    item.image = file_doc.file_url
# 			item.flags.ignore_mandatory = True
# 			item.save()
	
# def create_sales_order(order_id, woocommerce_settings, customer_name, sys_lang,line_items,shipping_tax,shipping_total,date_created=None):

# 	already_synched_ids = frappe.db.get_list('Sales Order', filters=[('woocommerce_id', '=', order_id)], fields=['name'], as_list=True, ignore_permissions=True)

# 	print ("\n already_synched_ids ::::::::::::::", already_synched_ids)
# 	if not already_synched_ids:
# 		new_sales_order = frappe.new_doc("Sales Order")
# 		new_sales_order.customer = customer_name

# 		new_sales_order.po_no = order_id
# 		new_sales_order.woocommerce_id = order_id
# 		new_sales_order.naming_series = woocommerce_settings.sales_order_series or "SO-WOO-"

# 		created_date = date_created
# 		new_sales_order.transaction_date = created_date
# 		delivery_after = woocommerce_settings.delivery_after_days or 7
# 		new_sales_order.delivery_date = frappe.utils.add_days(created_date, delivery_after)
# 		new_delivery_date = new_sales_order.delivery_date
# 		new_formmat_delivery_date = new_delivery_date.date()
# 		final_delivery_date = datetime.datetime.strptime(str(new_formmat_delivery_date), "%Y-%m-%d")

# 		new_sales_order.company = woocommerce_settings.company
# 		set_items_in_sales_order(new_sales_order, woocommerce_settings, order_id, sys_lang,line_items,shipping_tax,shipping_total,final_delivery_date)
# 		new_sales_order.flags.ignore_mandatory = True
# 		new_sales_order.insert()
# 		new_sales_order.submit()

# 		frappe.db.commit()


# def set_items_in_sales_order(new_sales_order, woocommerce_settings, order_id, sys_lang,line_items,shipping_tax,shipping_total,final_delivery_date):
# 	company_abbr = frappe.db.get_value("Company", woocommerce_settings.company, "abbr")

# 	default_warehouse = _("Stores - {0}", sys_lang).format(company_abbr)
# 	if not frappe.db.exists("Warehouse", default_warehouse) and not woocommerce_settings.warehouse:
# 		frappe.throw(_("Please set Warehouse in Woocommerce Settings"))

# 	for item in line_items:
# 		woocomm_item_id = item.get("product_id")
# 		found_item = frappe.get_doc("Item", {"woocommerce_id": cstr(woocomm_item_id)})		
	
# 		ordered_items_tax = item.get("total_tax")

# 		new_sales_order.append(
# 			"items",
# 			{
# 				"item_code": found_item.name,
# 				"item_name": found_item.item_name,
# 				"description": found_item.item_name,
# 				"delivery_date": final_delivery_date,
# 				"uom": woocommerce_settings.uom or _("Nos", sys_lang),
# 				"qty": item.get("quantity"),
# 				"rate": item.get("price"),
# 				"warehouse": woocommerce_settings.warehouse or default_warehouse,
# 			},
# 		)
# 		add_tax_details(
# 			new_sales_order, ordered_items_tax, "Ordered Item tax", woocommerce_settings.tax_account
# 		)
		
# 	# shipping_details = order.get("shipping_lines") # used for detailed order

# 	add_tax_details(
# 		new_sales_order, shipping_tax, "Shipping Tax", woocommerce_settings.f_n_f_account
# 	)
# 	add_tax_details(
# 		new_sales_order,
# 		shipping_total,
# 		woocommerce_settings.f_n_f_account,
# 	)

# def add_tax_details(sales_order, price, desc, tax_account_head=None):
# 	sales_order.append(
# 		"taxes",
# 		{
# 			"charge_type": "Actual",
# 			"account_head": tax_account_head,
# 			"tax_amount": price,
# 			"description": desc,
# 		},
# 	)

