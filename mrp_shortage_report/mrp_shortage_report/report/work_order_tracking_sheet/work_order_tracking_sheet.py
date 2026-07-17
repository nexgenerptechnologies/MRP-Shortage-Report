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
            
            IFNULL(last_op.completed_qty, wo.produced_qty) as _jc_completed_raw,
            wo.qty as _wo_qty_raw
        FROM
            `tabWork Order` wo
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
    
    if not data:
        return []
        
    wo_names = [d["work_order"] for d in data]
    
    wo_items = frappe.db.sql(f"""
        SELECT parent, item_code, required_qty, transferred_qty, consumed_qty
        FROM `tabWork Order Item`
        WHERE parent IN ({", ".join(["%s"] * len(wo_names))})
    """, tuple(wo_names), as_dict=1)
    
    wo_item_map = {}
    for item in wo_items:
        if item.parent not in wo_item_map:
            wo_item_map[item.parent] = []
        wo_item_map[item.parent].append(item)
        
    def get_pcs(qty, weight, uom):
        if not qty: return 0.0
        u = (uom or "").lower()
        if 'pc' in u or 'nos' in u:
            return qty
        if not weight or weight == 0:
            return qty # Fallback to avoid division by zero
        return qty / weight
        
    for row in data:
        wo_name = row["work_order"]
        bom_no = frappe.db.get_value("Work Order", wo_name, "bom_no")
        
        item_weights = {}
        fg_wt = 0.0
        
        if bom_no:
            bom_doc = frappe.get_cached_doc("BOM", bom_no)
            fg_wt = getattr(bom_doc, "quantity", 0.0)
            for b_item in getattr(bom_doc, "items", []):
                item_weights[b_item.item_code] = b_item.qty
                
        items = wo_item_map.get(wo_name, [])
        
        tot_req_kgs = 0.0; tot_req_pcs = 0.0
        tot_rec_kgs = 0.0; tot_rec_pcs = 0.0
        tot_cons_kgs = 0.0; tot_cons_pcs = 0.0
        
        for itm in items:
            req_k = itm.required_qty or 0.0
            rec_k = itm.transferred_qty or 0.0
            con_k = itm.consumed_qty or 0.0
            
            wt = item_weights.get(itm.item_code)
            if not wt:
                wt = frappe.db.get_value("Item", itm.item_code, "weight_per_unit") or 1.0
                
            itm_uom = frappe.db.get_value("Item", itm.item_code, "stock_uom") or ""
            
            req_p = get_pcs(req_k, wt, itm_uom)
            rec_p = get_pcs(rec_k, wt, itm_uom)
            con_p = get_pcs(con_k, wt, itm_uom)
            
            tot_req_kgs += req_k; tot_req_pcs += req_p
            tot_rec_kgs += rec_k; tot_rec_pcs += rec_p
            tot_cons_kgs += con_k; tot_cons_pcs += con_p
            
        row["total_required"] = tot_req_kgs
        row["total_required_pcs"] = tot_req_pcs
        
        row["total_received"] = tot_rec_kgs
        row["total_received_pcs"] = tot_rec_pcs
        
        row["pending_to_receive"] = tot_req_kgs - tot_rec_kgs
        row["pending_to_receive_pcs"] = tot_req_pcs - tot_rec_pcs
        
        row["qty_consumed"] = tot_cons_kgs
        row["qty_consumed_pcs"] = tot_cons_pcs
        
        row["available_on_floor"] = tot_rec_kgs - tot_cons_kgs
        row["available_on_floor_pcs"] = tot_rec_pcs - tot_cons_pcs
        
        # Finished Good logic exactly as per UI Script
        fg_item = row["item_code"]
        jc_comp_raw = row.get("_jc_completed_raw", 0.0)
        wo_qty_raw = row.get("_wo_qty_raw", 0.0)
        
        max_fg = 0.0
        if tot_req_kgs > 0:
            max_fg = (tot_rec_kgs / tot_req_kgs) * wo_qty_raw
            
        bal_jc = max_fg - jc_comp_raw
        if bal_jc < 0: bal_jc = 0.0
        
        fg_uom = frappe.db.get_value("Item", fg_item, "stock_uom") or ""
        
        row["jc_completed"] = jc_comp_raw
        row["balance_to_complete_jc"] = bal_jc
        
        row["jc_completed_pcs"] = get_pcs(jc_comp_raw, fg_wt, fg_uom)
        row["balance_to_complete_jc_pcs"] = get_pcs(bal_jc, fg_wt, fg_uom)

    return data
