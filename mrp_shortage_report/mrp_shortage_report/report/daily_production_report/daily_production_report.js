frappe.query_reports["Daily Production Report"] = {
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
            "reqd": 1
        },
        {
            "fieldname": "to_date",
            "label": __("To Date"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "workstation",
            "label": __("Workstation"),
            "fieldtype": "Link",
            "options": "Workstation"
        },
        {
            "fieldname": "employee",
            "label": __("Operator"),
            "fieldtype": "Link",
            "options": "Employee"
        },
        {
            "fieldname": "status",
            "label": __("Status"),
            "fieldtype": "Select",
            "options": "\nOpen\nWork In Progress\nCompleted\nCancelled\nOn Hold\nMaterial Transferred",
            "default": ""
        }
    ],
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        
        // Custom formatting for the Difference column
        if (column.fieldname == "difference" && data && data.difference !== undefined && data.difference !== null) {
            if (data.difference < 0) {
                // Negative difference (less scrap than BOM) is good -> Green
                value = "<span style='color:green; font-weight:bold'>" + value + "</span>";
            } else if (data.difference > 0) {
                // Positive difference (more scrap than BOM) is bad -> Red
                value = "<span style='color:red; font-weight:bold'>" + value + "</span>";
            }
        }
        
        return value;
    }
};
