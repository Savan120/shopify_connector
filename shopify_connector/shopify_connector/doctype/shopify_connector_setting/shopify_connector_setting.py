# Copyright (c) 2024, Solufy and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import requests
from frappe import _
from typing import Dict, List
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils.nestedset import get_root_of
from frappe.utils import cstr
import datetime


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
			create_delete_custom_fields(self)
			get_order(self) 

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

def get_order(self):
	api_key = self.api_key
	password = self.access_token
	shopify_url = self.shop_url
	# Construct the endpoint URL
	endpoint = f"https://{shopify_url}/admin/api/2024-01/orders.json"

	# Set request headers
	headers = {
		"X-Shopify-Access-Token": password,
		"Content-Type": "application/json"
	}
	response = requests.get(endpoint, headers=headers, verify=False)
	orders = response.json()["orders"]
	if orders:
		shopify_connector_setting = frappe.get_doc("Shopify Connector Setting")
		sys_lang = frappe.get_single("System Settings").language or "en"
		for order_data in orders:
			order_id = order_data.get('order_number')

			shipping = order_data.get('shipping')

			line_items = order_data.get('line_items')
			items_list = line_items

			# Make a request to fetch product details
			images_src = []
			for image_item in line_items:
				idd = image_item.get('product_id')
				response = requests.get(f'https://{shopify_url}/admin/api/2021-10/products/{idd}.json', headers={'X-Shopify-Access-Token': password},verify=False)

				if response.status_code == 200:
					product_data = response.json()['product']
					# Extract image URLs
					images_src += [image['src'] for image in product_data['images']]
				else:
					print(f"Failed to fetch product details: {response.status_code} - {response.text}")
			img_link  = images_src[0] if len(images_src)>0 else ''

			billing = order_data.get('billing_address')
			raw_billing_data = billing

			shipping = order_data.get('shipping_address',False)
			raw_shipping_data = shipping

			contact_email = order_data.get('contact_email')
			if raw_shipping_data:
				customer_name = (raw_shipping_data.get("first_name") or "") + " " + (raw_shipping_data.get("last_name") or "")

			else: 
				customer_name = ""

			discount_info = order_data.get('discount_applications')
			disc_type = ''
			for dis_value in discount_info:
				disc_type = dis_value.get('value_type')
				dis_value.get('value')
				disc_type = dis_value.get('value_type')

			discount_per = 0
			if disc_type == 'percentage':
				if len(discount_info) > 0 :
					for line_price in discount_info:
						discount_per+= float(line_price.get('value'))
			

			discount_codes = order_data.get('discount_codes')
			discount_amount = 0
			if disc_type == 'fixed_amount':
				if len(discount_codes) > 0 :
					for line_price in discount_codes:
						discount_amount+= float(line_price.get('amount'))


			tax_lines = order_data.get('tax_lines')

			tax_lines_amount = 0
			for tl in tax_lines: 
				tax_lines_amount = tl.get('price')

			shipping_lines_data = order_data.get('shipping_lines')
		
			shipping_lines = 0
			if len(shipping_lines_data) > 0 :
				for line_price in shipping_lines_data:
					shipping_lines+= float(line_price.get('price'))

			date_created = order_data.get('created_at').split("T")
			date_created = date_created[0]

			if not customer_name:
				frappe.throw(_(f"Not Customer Available in Shopify Order !! Please check the order id {order_id}"))
			else:
				link_customer_and_address( raw_shipping_data, customer_name, contact_email)
				# link_items(items_list, sys_lang, shopify_connector_setting, shipping_lines, img_link)
				# create_sales_order(order_id, shopify_connector_setting, customer_name, sys_lang,line_items,shipping_lines, tax_lines_amount, discount_amount, discount_per, date_created)

	else:
		frappe.throw(_("Shopify Order is not available !!"))

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
		customer.shopify_email = customer_shopify_email
		customer.flags.ignore_mandatory = True
		customer.save()

# def link_items(items_list, sys_lang, shopify_connector_setting, shipping_lines, img_link):
# 	for item_data in items_list:
# 		item_shopify_com_id = cstr(item_data.get("product_id"))
# 		# image_src
# 		if not frappe.db.get_value("Item", {"shopify_id": item_shopify_com_id}, "name"):
# 			# Create Item
# 			item = frappe.new_doc("Item")
# 			item.item_code = _("Shopify - {0}", sys_lang).format(item_shopify_com_id)
# 			item.stock_uom = shopify_connector_setting.uom or _("Nos", sys_lang)
# 			item.item_group = _("Shopify Products", sys_lang)

# 			item.item_name = item_data.get("name")
# 			item.shopify_id = item_shopify_com_id

# 			#Upload image from image_src
# 			if img_link:
# 				file_doc = frappe.get_doc({
# 					"doctype": "File",
# 					"file_url": img_link,
# 					"is_private": 0  # Set to 0 to make it accessible to all users
# 				})
# 				file_doc.insert()
# 				item.image = file_doc.file_url
# 			item.flags.ignore_mandatory = True
# 			item.save()


# from shopify_connector.shopify_connector.customisation.api.webhook.product_creation
# @frappe.whitelist()
# def sync_all_products_from_shopify():
#     settings = frappe.get_doc("Shopify Connector Setting")
#     shop_url = settings.shop_url
#     access_token = settings.access_token

#     headers = {
#         "X-Shopify-Access-Token": access_token,
#         "Content-Type": "application/json"
#     }

#     page_info = None
#     base_url = f"https://{shop_url}/admin/api/2025-04/products.json?limit=250"
#     created = []
#     skipped = []

#     while True:
#         url = base_url
#         if page_info:
#             url += f"&page_info={page_info}"

#         response = requests.get(url, headers=headers)
#         if response.status_code != 200:
#             frappe.throw(f"Failed to fetch products from Shopify: {response.text}")

#         data = response.json()
#         products = data.get("products", [])

#         if not products:
#             break

#         for product in products:
#             if frappe.db.exists("Item", {"shopify_id": product.get("id")}):
#                 skipped.append(product.get("title"))
#                 continue

#             # Convert product data to JSON and simulate webhook-style POST
#             frappe.local.request._data = product
#             frappe.local.form_dict = product
#             try:
#                 product_creation()
#                 created.append(product.get("title"))
#             except Exception as e:
#                 frappe.log_error(str(e), f"Product Creation Failed - {product.get('title')}")

#         # Pagination - Get 'Link' header for next page
#         link_header = response.headers.get("Link", "")
#         if 'rel="next"' in link_header:
#             import re
#             match = re.search(r'<([^>]+)>; rel="next"', link_header)
#             if match:
#                 next_url = match.group(1)
#                 page_info_match = re.search(r'page_info=([^&]+)', next_url)
#                 page_info = page_info_match.group(1) if page_info_match else None
#             else:
#                 break
#         else:
#             break

#     return {
#         "created": created,
#         "skipped": skipped,
#         "message": f"{len(created)} products created, {len(skipped)} skipped (already exist)."
#     }




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



@frappe.whitelist(allow_guest=True,methods=["POST"])
def shopify_webhook():
    data = frappe.request.get_data(as_text=True)
    frappe.logger("shopify").info(f"Shopify Webhook Received: {data}")

    return {"message": "Shopify request received"}, 200
    
    
