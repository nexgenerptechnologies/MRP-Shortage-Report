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
        {"fieldname": "operation", "label": _("Operation"), "fieldtype": "Data", "width": 120},
        {"fieldname": "operator_name", "label": _("Operator Name"), "fieldtype": "Data", "width": 120},
        {"fieldname": "workstation", "label": _("Workstation"), "fieldtype": "Data", "width": 120},
        {"fieldname": "operation_time_mints", "label": _("Operation Time (Mints)"), "fieldtype": "Data", "width": 160},
        {"fieldname": "shift", "label": _("Shift"), "fieldtype": "Data", "width": 100},
        {"fieldname": "production_qty_pcs", "label": _("Production Qty (Pcs)"), "fieldtype": "Data", "width": 160},
        {"fieldname": "production_qty_kgs", "label": _("Production Qty (Kgs)"), "fieldtype": "Data", "width": 160},
        {"fieldname": "scrap_kgs", "label": _("Scrap (Kgs)"), "fieldtype": "Data", "width": 120},
        {"fieldname": "total_required", "label": _("Total Required(Kgs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "total_required_pcs", "label": _("Total Required(Pcs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "total_received", "label": _("Total Received(Kgs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "total_received_pcs", "label": _("Total Received (Pcs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "pending_to_receive", "label": _("Pending to Receive(Kgs)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pending_to_receive_pcs", "label": _("Pending to Receive(Pcs)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "qty_consumed", "label": _("Qty Consumed(Kgs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "qty_consumed_pcs", "label": _("Qty Consumed(Pcs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "available_on_floor", "label": _("Available on Floor(Kgs)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "available_on_floor_pcs", "label": _("Available on Floor(Pcs)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "jc_completed", "label": _("JC Completed(Kgs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "jc_completed_pcs", "label": _("JC Completed(Pcs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "balance_to_complete_jc", "label": _("Balance to Complete JC(Kgs)"), "fieldtype": "Float", "width": 180},
        {"fieldname": "balance_to_complete_jc_pcs", "label": _("Balance to Complete JC(Pcs)"), "fieldtype": "Float", "width": 180}
    ]

def get_data(filters):
    conditions = []
    
    if filters.get("from_date"):
        conditions.append(f"wo.creation >= '{filters.get('from_date')}'")
    if filters.get("to_date"):
        conditions.append(f"wo.creation <= '{filters.get('to_date')}'")
    if filters.get("company"):
        conditions.append(f"wo.company = '{filters.get('company')}'")
    if filters.get("work_order"):
        work_orders = filters.get("work_order")
        if isinstance(work_orders, list):
            wo_list = ", ".join(f"'{w}'" for w in work_orders)
            conditions.append(f"wo.name IN ({wo_list})")
        else:
            conditions.append(f"wo.name IN ('{work_orders}')")
    if filters.get("item_code"):
        conditions.append(f"wo.production_item = '{filters.get('item_code')}'")
    if filters.get("status"):
        conditions.append(f"wo.status = '{filters.get('status')}'")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"""
        SELECT
            DATE(wo.creation) as date,
            wo.name as work_order,
            wo.status,
            wo.production_item as item_code,
            wo.item_name,
            '' as operation,
            '' as operator_name,
            '' as workstation,
            '' as operation_time_mints,
            '' as shift,
            '' as production_qty_pcs,
            '' as production_qty_kgs,
            '' as scrap_kgs,
            IFNULL(woi.total_required, 0) as total_required,
            IFNULL(woi.total_received, 0) as total_received,
            IFNULL(woi.qty_consumed, 0) as qty_consumed,
            
            IFNULL(last_op.completed_qty, wo.produced_qty) as _jc_completed_raw,
            wo.qty as _wo_qty_raw
        FROM
            `tabWork Order` wo
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
        LEFT JOIN
            (
                SELECT parent, completed_qty 
                FROM `tabWork Order Operation` op1
                WHERE idx = (
                    SELECT MAX(idx) FROM `tabWork Order Operation` op2 WHERE op2.parent = op1.parent
                )
            ) last_op ON last_op.parent = wo.name
        WHERE
            {where_clause}
            AND wo.docstatus < 2
        ORDER BY
            wo.creation DESC, wo.name ASC
    """

    data = frappe.db.sql(query, as_dict=1)
    
    for row in data:
        req_qty = row.get("total_required", 0.0) # Kgs
        rec_qty = row.get("total_received", 0.0) # Kgs
        qty_consumed = row.get("qty_consumed", 0.0) # Kgs
        
        jc_comp_raw = row.get("_jc_completed_raw", 0.0) # Pcs
        wo_qty_raw = row.get("_wo_qty_raw", 0.0) # Pcs
        
        # Calculate conversion factors based on BOM (Total Required Kgs / Work Order Qty Pcs)
        if req_qty > 0 and wo_qty_raw > 0:
            pcs_per_kg = wo_qty_raw / req_qty
            kg_per_pc = req_qty / wo_qty_raw
        else:
            pcs_per_kg = 0.0
            kg_per_pc = 0.0
            
        # Kgs calculations
        row["pending_to_receive"] = req_qty - rec_qty
        row["available_on_floor"] = rec_qty - qty_consumed
        row["jc_completed"] = jc_comp_raw * kg_per_pc
        
        # Pcs calculations
        row["total_required_pcs"] = wo_qty_raw
        row["total_received_pcs"] = rec_qty * pcs_per_kg
        row["pending_to_receive_pcs"] = row["pending_to_receive"] * pcs_per_kg
        row["qty_consumed_pcs"] = qty_consumed * pcs_per_kg
        row["available_on_floor_pcs"] = row["available_on_floor"] * pcs_per_kg
        
        row["jc_completed_pcs"] = jc_comp_raw
        
        bal_jc_pcs = row["total_received_pcs"] - jc_comp_raw
        if bal_jc_pcs < 0:
            bal_jc_pcs = 0.0
            
        row["balance_to_complete_jc_pcs"] = bal_jc_pcs
        row["balance_to_complete_jc"] = bal_jc_pcs * kg_per_pc

    return data
