import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "work_order", "label": _("Work Order"), "fieldtype": "Link", "options": "Work Order", "width": 150},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 120},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 150},
        {"fieldname": "operation", "label": _("Operation"), "fieldtype": "Link", "options": "Operation", "width": 120},
        {"fieldname": "operator_name", "label": _("Operator Name"), "fieldtype": "Data", "width": 120},
        {"fieldname": "workstation", "label": _("Workstation"), "fieldtype": "Data", "width": 120},
        {"fieldname": "operation_time_mints", "label": _("Operation Time (Mints)"), "fieldtype": "Data", "width": 160},
        {"fieldname": "shift", "label": _("Shift"), "fieldtype": "Data", "width": 100},
        {"fieldname": "production_qty_pcs", "label": _("Production Qty (Pcs)"), "fieldtype": "Data", "width": 160},
        {"fieldname": "production_qty_kgs", "label": _("Production Qty (Kgs)"), "fieldtype": "Data", "width": 160},
        {"fieldname": "scrap_kgs", "label": _("Scrap (Kgs)"), "fieldtype": "Data", "width": 120},
        {"fieldname": "total_required", "label": _("Total Required"), "fieldtype": "Float", "width": 120},
        {"fieldname": "total_received", "label": _("Total Received"), "fieldtype": "Float", "width": 120},
        {"fieldname": "pending_to_receive", "label": _("Pending to Receive"), "fieldtype": "Float", "width": 140},
        {"fieldname": "qty_consumed", "label": _("Qty Consumed"), "fieldtype": "Float", "width": 120},
        {"fieldname": "available_on_floor", "label": _("Available on Floor"), "fieldtype": "Float", "width": 140},
        {"fieldname": "jc_completed", "label": _("JC Completed"), "fieldtype": "Float", "width": 120},
        {"fieldname": "balance_to_complete_jc", "label": _("Balance to Complete JC"), "fieldtype": "Float", "width": 160}
    ]

def get_data(filters):
    conditions = []
    
    if filters.get("from_date"):
        conditions.append(f"jc.posting_date >= '{filters.get('from_date')}'")
    if filters.get("to_date"):
        conditions.append(f"jc.posting_date <= '{filters.get('to_date')}'")
    if filters.get("company"):
        conditions.append(f"jc.company = '{filters.get('company')}'")
    if filters.get("work_order"):
        work_orders = filters.get("work_order")
        if isinstance(work_orders, list):
            wo_list = ", ".join(f"'{wo}'" for wo in work_orders)
            conditions.append(f"jc.work_order IN ({wo_list})")
        else:
            conditions.append(f"jc.work_order IN ('{work_orders}')")
    if filters.get("item_code"):
        conditions.append(f"jc.production_item = '{filters.get('item_code')}'")
    if filters.get("operation"):
        conditions.append(f"jc.operation = '{filters.get('operation')}'")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            jc.posting_date as date,
            jc.work_order,
            jc.status,
            jc.production_item as item_code,
            jc.item_name,
            jc.operation,
            IFNULL(woi.total_required, 0) as total_required,
            IFNULL(woi.total_received, 0) as total_received,
            IFNULL(woi.total_required, 0) - IFNULL(woi.total_received, 0) as pending_to_receive,
            IFNULL(woi.qty_consumed, 0) as qty_consumed,
            IFNULL(woi.total_received, 0) - IFNULL(woi.qty_consumed, 0) as available_on_floor,
            jc.total_completed_qty as _jc_completed_raw,
            jc.for_quantity - jc.total_completed_qty as _balance_to_complete_jc_raw
        FROM
            `tabJob Card` jc
        INNER JOIN
            `tabWork Order` wo ON jc.work_order = wo.name
        LEFT JOIN
            (
                SELECT 
                    parent, 
                    SUM(required_qty) as total_required, 
                    SUM(transferred_qty) as total_received, 
                    SUM(consumed_qty) as qty_consumed 
                FROM `tabWork Order Item` 
                GROUP BY parent
            ) woi ON woi.parent = wo.name
        WHERE
            {where_clause}
            AND jc.docstatus < 2
        ORDER BY
            jc.posting_date DESC, jc.work_order ASC
    """

    data = frappe.db.sql(query, as_dict=1)
    
    # Conversion cache
    conversion_cache = {}
    
    for row in data:
        item_code = row.get("item_code")
        if not item_code:
            row["jc_completed"] = row.get("_jc_completed_raw", 0.0)
            row["balance_to_complete_jc"] = row.get("_balance_to_complete_jc_raw", 0.0)
            continue
            
        if item_code not in conversion_cache:
            item_doc = frappe.get_cached_doc("Item", item_code)
            stock_uom = item_doc.stock_uom and item_doc.stock_uom.strip().lower()
            
            kgs_factor = 1.0
            if stock_uom in ['pcs', 'nos', 'piece']:
                for uom in item_doc.uoms:
                    if uom.uom.strip().lower() in ['kg', 'kgs']:
                        kgs_factor = 1.0 / (uom.conversion_factor or 1.0)
                        break
                        
            conversion_cache[item_code] = {
                "stock_uom": stock_uom,
                "kgs_factor": kgs_factor
            }
            
        cache = conversion_cache[item_code]
        
        jc_comp_raw = row.get("_jc_completed_raw", 0.0)
        bal_comp_raw = row.get("_balance_to_complete_jc_raw", 0.0)
        
        if cache["stock_uom"] in ['pcs', 'nos', 'piece']:
            row["jc_completed"] = jc_comp_raw * cache["kgs_factor"]
            row["balance_to_complete_jc"] = bal_comp_raw * cache["kgs_factor"]
        else:
            row["jc_completed"] = jc_comp_raw
            row["balance_to_complete_jc"] = bal_comp_raw

    return data
