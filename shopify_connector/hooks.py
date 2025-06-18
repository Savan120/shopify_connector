app_name = "shopify_connector"
app_title = "Shopify Connector"
app_publisher = "Solufy"
app_description = "Shopify Integration with ERPNext"
app_email = "contact@solufy.in"
app_license = "mit"
# required_apps = []

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/shopify_connector/css/shopify_connector.css"
# app_include_js = "/assets/shopify_connector/js/shopify_connector.js"

# include js, css files in header of web template
# web_include_css = "/assets/shopify_connector/css/shopify_connector.css"
# web_include_js = "/assets/shopify_connector/js/shopify_connector.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "shopify_connector/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Address" : "shopify_connector/customisation/address/address.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "shopify_connector/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
#	"methods": "shopify_connector.utils.jinja_methods",
#	"filters": "shopify_connector.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "shopify_connector.install.before_install"
# after_install = "shopify_connector.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "shopify_connector.uninstall.before_uninstall"
# after_uninstall = "shopify_connector.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "shopify_connector.utils.before_app_install"
# after_app_install = "shopify_connector.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "shopify_connector.utils.before_app_uninstall"
# after_app_uninstall = "shopify_connector.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "shopify_connector.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
#	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
#	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
#	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Customer": {
        "validate":"shopify_connector.shopify_connector.customisation.api.sync_to_shoify.enqueue_send_customer_to_shopify",
        "after_insert": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.enqueue_send_customer_to_shopify",
        "on_update": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_customer_to_shopify_hook",
        "on_trash": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.delete_customer_from_shopify",
    },
    "Address": {
        "validate": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.on_address_update",
        # "on_trash": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.delete_address_from_shopify",
    },
    "Contact": {
        "on_update": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_contact_to_shopify",
        # "on_trash": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.delete_address_from_shopify",
    },
    "Item": {
        "after_insert": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_item_to_shopify",
        "on_update": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.send_item_to_shopify",
    },
    "Sales Order":{
        "before_validate": "shopify_connector.shopify_connector.customisation.sales_order.sales_order.before_validate"
    },
    "Sales Order":{
        "after_insert":"shopify_connector.shopify_connector.customisation.api.sync_to_shoify.create_shopify_draft_order"
    },
    # "Bin": {
    #     "on_update": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.sync_inventory_to_shopify",
    #     "after_insert": "shopify_connector.shopify_connector.customisation.api.sync_to_shoify.sync_inventory_to_shopify"
    # }
}



# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"* * * * *": [
# 		"shopify_connector.shopify_connector.customisation.api.sync_to_shoify.get_shopify_location"
# 	],
#	"daily": [
#		"shopify_connector.tasks.daily"
#	],
#	"hourly": [
#		"shopify_connector.tasks.hourly"
#	],
#	"weekly": [
#		"shopify_connector.tasks.weekly"
#	],
#	"monthly": [
#		"shopify_connector.tasks.monthly"
#	],
# }

# Testing
# -------

# before_tests = "shopify_connector.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
#	"frappe.desk.doctype.event.event.get_events": "shopify_connector.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
#	"Task": "shopify_connector.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["shopify_connector.utils.before_request"]
# after_request = ["shopify_connector.utils.after_request"]

# Job Events
# ----------
# before_job = ["shopify_connector.utils.before_job"]
# after_job = ["shopify_connector.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
#	{
#		"doctype": "{doctype_1}",
#		"filter_by": "{filter_by}",
#		"redact_fields": ["{field_1}", "{field_2}"],
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_2}",
#		"filter_by": "{filter_by}",
#		"partial": 1,
#	},
#	{
#		"doctype": "{doctype_3}",
#		"strict": False,
#	},
#	{
#		"doctype": "{doctype_4}"
#	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
#	"shopify_connector.auth.validate"
# ]
after_migrate = "shopify_connector.migrate.after_migrate"  