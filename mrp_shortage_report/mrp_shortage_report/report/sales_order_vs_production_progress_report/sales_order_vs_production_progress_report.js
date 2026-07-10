// Copyright (c) 2024, Nexgen ERP Technologies and contributors
// For license information, please see license.txt

frappe.query_reports["Sales order Vs Production Progress Report"] = {
	"tree": true,
	"name_field": "id",
	"parent_field": "parent_id",
	"initial_depth": 1,
	"add_total_row": 1,
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
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
        {
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
            "default": frappe.datetime.get_today()
		},
		{
			"fieldname": "sales_order",
			"label": __("Sales Order"),
			"fieldtype": "Link",
			"options": "Sales Order"
		},
        {
			"fieldname": "production_plan",
			"label": __("Production Plan"),
			"fieldtype": "Link",
			"options": "Production Plan"
		},
        {
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer"
		},
        {
			"fieldname": "item_code",
			"label": __("Item Code"),
			"fieldtype": "Link",
			"options": "Item"
		},
        {
			"fieldname": "pp_status",
			"label": __("Production Plan Status"),
			"fieldtype": "Select",
			"options": "\nDraft\nSubmitted\nNot Started\nIn Process\nCompleted\nStopped\nClosed\nMaterial Requested",
		}
	]
};
