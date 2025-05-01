frappe.ui.form.on('Address', {
    onload: function(frm) {
        if (!frm.doc.country) {
            frm.set_value('country', 'India');
        }
    },
    onchange: function(frm) {
        if (frm.doc.phone) {
            

        }
    }
});


frappe.ui.form.on('Address', {
    phone: function(frm) {
        const country = frm.doc.country;
        const phone = frm.doc.phone;
        if (country === 'India') {
            const digits = (phone || '').replace(/\D/g, '');
            if (digits.length !== 10) {
                frappe.show_alert({message: 'Phone number should be exactly 10 digits for India.', indicator: 'orange'});
            }
        }
    }
});

