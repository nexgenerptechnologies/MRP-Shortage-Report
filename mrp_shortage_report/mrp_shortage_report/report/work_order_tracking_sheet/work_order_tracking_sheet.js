frappe.query_reports["Work Order Tracking Sheet"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company"),
            "reqd": 1
        },
        {
            "fieldname": "from_date",
            "label": __("From Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        },
        {
            "fieldname": "work_order",
            "label": __("Work Order"),
            "fieldtype": "MultiSelectList",
            "options": "Work Order",
            "get_data": function(txt) {
                return frappe.db.get_link_options('Work Order', txt);
            }
        },
        {
            "fieldname": "item_code",
            "label": __("Item Code"),
            "fieldtype": "MultiSelectList",
            "options": "Item",
            "get_data": function(txt) {
                return frappe.db.get_link_options('Item', txt);
            }
        },
        {
            "fieldname": "status",
            "label": __("Status"),
            "fieldtype": "Select",
            "options": "\nOpen\nWork In Progress\nCompleted\nMaterial Transferred\nOn Hold\nCancelled"
        }
    ]
};
