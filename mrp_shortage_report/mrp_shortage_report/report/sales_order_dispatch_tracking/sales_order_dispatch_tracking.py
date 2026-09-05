import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "so_date", "label": _("SO Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "sales_order", "label": _("Sales Order"), "fieldtype": "Link", "options": "Sales Order", "width": 140},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 140},
        {"fieldname": "po_no", "label": _("Customer PO No."), "fieldtype": "Data", "width": 140},
        {"fieldname": "po_date", "label": _("Customer PO Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 140},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 200},
        {"fieldname": "so_qty", "label": _("SO Qty"), "fieldtype": "Float", "width": 100},
        {"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 100},
        {"fieldname": "dispatch_date", "label": _("Dispatch Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "dispatch_reference", "label": _("Dispatch Reference"), "fieldtype": "Dynamic Link", "options": "reference_type", "width": 150},
        {"fieldname": "reference_type", "label": _("Reference Type"), "fieldtype": "Data", "hidden": 1},
        {"fieldname": "dispatched_qty", "label": _("Dispatched Qty"), "fieldtype": "Float", "width": 120},
        {"fieldname": "cumulative_dispatched", "label": _("Cumulative Dispatched"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pending_qty", "label": _("Pending Qty"), "fieldtype": "Float", "width": 120},
    ]

def get_data(filters):
    if not filters:
        filters = {}
        
    # We want to pull ALL dispatches first, calculate cumulatives PER SO Item, 
    # and then filter the final list. Otherwise, cumulative totals will be wrong if we filter by date!
    
    so_items_sql = """
        SELECT 
            i.parent as sales_order,
            i.item_code,
            i.item_name,
            i.description,
            i.qty as so_qty,
            i.rate,
            i.name as so_item_name,
            so.transaction_date as so_date,
            so.po_no,
            so.po_date
        FROM `tabSales Order Item` i
        JOIN `tabSales Order` so ON i.parent = so.name
        WHERE so.docstatus = 1
    """
    so_items = frappe.db.sql(so_items_sql, as_dict=1)
    
    so_item_map = {}
    for item in so_items:
        so_item_map[item.so_item_name] = item
        so_item_map[(item.sales_order, item.item_code)] = item
        
    dn_sql = """
        SELECT 
            dn.name as dispatch_reference,
            'Delivery Note' as reference_type,
            dn.posting_date as dispatch_date,
            dn.customer,
            dni.against_sales_order as sales_order,
            dni.item_code,
            dni.qty as dispatched_qty,
            dni.so_detail
        FROM `tabDelivery Note` dn
        INNER JOIN `tabDelivery Note Item` dni ON dn.name = dni.parent
        WHERE dn.docstatus = 1 AND dni.against_sales_order IS NOT NULL AND dni.against_sales_order != ''
    """
    
    si_sql = """
        SELECT 
            si.name as dispatch_reference,
            'Sales Invoice' as reference_type,
            si.posting_date as dispatch_date,
            si.customer,
            sii.sales_order as sales_order,
            sii.item_code,
            sii.qty as dispatched_qty,
            sii.so_detail
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii ON si.name = sii.parent
        WHERE si.docstatus = 1 AND si.update_stock = 1 AND sii.sales_order IS NOT NULL AND sii.sales_order != ''
    """
    
    dispatches = frappe.db.sql(f"{dn_sql} UNION ALL {si_sql} ORDER BY dispatch_date ASC", as_dict=1)
    
    cumulative_map = {} 
    all_rows = []
    
    for d in dispatches:
        key = (d.sales_order, d.item_code)
        
        so_info = so_item_map.get(d.so_detail)
        if not so_info:
            so_info = so_item_map.get(key)
            
        if not so_info:
            continue
            
        cum_qty = cumulative_map.get(key, 0.0) + d.dispatched_qty
        cumulative_map[key] = cum_qty
        
        row = frappe._dict({
            "so_date": so_info.so_date,
            "sales_order": d.sales_order,
            "customer": d.customer,
            "po_no": so_info.po_no,
            "po_date": so_info.po_date,
            "item_code": d.item_code,
            "item_name": so_info.item_name,
            "description": so_info.description,
            "so_qty": so_info.so_qty,
            "rate": so_info.rate,
            "dispatch_date": d.dispatch_date,
            "dispatch_reference": d.dispatch_reference,
            "reference_type": d.reference_type,
            "dispatched_qty": d.dispatched_qty,
            "cumulative_dispatched": cum_qty,
            "pending_qty": so_info.so_qty - cum_qty
        })
        all_rows.append(row)
        
    filtered_rows = []
    
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    
    def parse_multi(val):
        if not val: return []
        if isinstance(val, str): return [val]
        return val
        
    f_so = parse_multi(filters.get("sales_order"))
    f_cust = parse_multi(filters.get("customer"))
    f_item = parse_multi(filters.get("item_code"))
    f_si = parse_multi(filters.get("sales_invoice"))
    f_dn = parse_multi(filters.get("delivery_note"))
    f_refs = f_si + f_dn
    
    for row in all_rows:
        if from_date and frappe.utils.getdate(row.dispatch_date) < frappe.utils.getdate(from_date):
            continue
        if to_date and frappe.utils.getdate(row.dispatch_date) > frappe.utils.getdate(to_date):
            continue
        if f_so and row.sales_order not in f_so:
            continue
        if f_cust and row.customer not in f_cust:
            continue
        if f_item and row.item_code not in f_item:
            continue
        if f_refs and row.dispatch_reference not in f_refs:
            continue
            
        filtered_rows.append(row)
        
    filtered_rows.sort(key=lambda x: x.dispatch_date, reverse=True)
    
    return filtered_rows
