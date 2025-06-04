import frappe
from frappe.geo.country_info import get_country_info
from frappe import whitelist

@whitelist()
def get_states_by_country(country):
    try:
        country_info = get_country_info(country)
        return list(country_info.get("states", {}).keys())
    except Exception as e:
        frappe.log_error(f"Failed to fetch states: {str(e)}", "State Fetch Error")
        return []


