import frappe
import json
# from erpnext.controllers.accounts_controller import calculate_taxes_and_totals

# from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
import json


from erpnext.stock.get_item_details import get_item_tax_map
def before_validate(self, method = None):
    for row in self.items:
        var = get_item_tax_map(self.company, row.item_tax_template)
        if isinstance(var, str):
            var = json.loads(var)
        for row in var:
            print(row)
            if row in ["Input Tax SGST - K", "Input Tax CGST - K", "Input Tax IGST - K", "Input Tax SGST RCM - K", "Input Tax CGST RCM - K", "Input Tax IGST RCM - K"]:
                continue
            self.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": row,
                "rate": 0
            })
        self.calculate_taxes_and_totals()
