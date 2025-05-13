import json
import os

import frappe


def after_migrate():
    create_custom_fields()



def create_custom_fields():
    CUSTOM_FIELDS = {}
    print("Creating/Updating Custom Fields....")
    path = os.path.join(os.path.dirname(file), "servisa/custom_fields")
    for file in os.listdir(path):
        with open(os.path.join(path, file), "r") as f:
            CUSTOM_FIELDS.update(json.load(f))
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(CUSTOM_FIELDS)