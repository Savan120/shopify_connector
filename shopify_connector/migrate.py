# import json
# import os

# import frappe


# def after_migrate():
#     create_custom_fields()



# def create_custom_fields():
#     CUSTOM_FIELDS = {}
#     print("Creating/Updating Custom Fields....")
#     path = os.path.join(os.path.dirname(file), "shopify_connector/custom_fields")
#     for file in os.listdir(path):
#         with open(os.path.join(path, file), "r") as f:
#             CUSTOM_FIELDS.update(json.load(f))
#     from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

#     create_custom_fields(CUSTOM_FIELDS)





import json
import os
import frappe

def after_migrate():
    create_custom_fields()

def create_custom_fields():
    CUSTOM_FIELDS = {}
    print("Creating/Updating Custom Fields....")
    
    # Use __file__ to get the current file path
    path = os.path.join(os.path.dirname(__file__), "shopify_connector/custom_fields")
    
    # Loop through files in the directory
    for filename in os.listdir(path):
        full_path = os.path.join(path, filename)
        with open(full_path, "r") as f:
            CUSTOM_FIELDS.update(json.load(f))

    # Import create_custom_fields after loading the data
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields(CUSTOM_FIELDS)