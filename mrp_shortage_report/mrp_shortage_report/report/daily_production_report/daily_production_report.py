import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "job_card", "label": _("Job Card"), "fieldtype": "Link", "options": "Job Card", "width": 140},
        {"fieldname": "work_order", "label": _("Work Order"), "fieldtype": "Link", "options": "Work Order", "width": 140},
        {"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 140},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "workstation", "label": _("Workstation"), "fieldtype": "Link", "options": "Workstation", "width": 140},
        {"fieldname": "operation", "label": _("Operation"), "fieldtype": "Link", "options": "Operation", "width": 120},
        {"fieldname": "operation_time", "label": _("Operation Time (Mints)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "operator_name", "label": _("Operator Name"), "fieldtype": "Data", "width": 140},
        {"fieldname": "stock_entry_qty", "label": _("Stock Entry (Manufacture)"), "fieldtype": "Float", "width": 180},
        {"fieldname": "production_qty_pcs", "label": _("Production Qty (Pcs)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "production_qty_kgs", "label": _("Production Qty (Kgs)"), "fieldtype": "Float", "width": 160},
        {"fieldname": "scrap_as_per_bom", "label": _("Scrap as per BOM"), "fieldtype": "Float", "width": 140},
        {"fieldname": "actual_scrap", "label": _("Actual Scrap"), "fieldtype": "Float", "width": 120},
        {"fieldname": "difference", "label": _("Difference"), "fieldtype": "Float", "width": 100}
    ]

def get_data(filters):
    conditions = get_conditions(filters)
    
    # Fetch Job Cards
    job_cards = frappe.db.sql(f"""
        SELECT
            name as job_card, posting_date, work_order, production_item as item_code,
            item_name, status, workstation, operation, total_time_in_mins as operation_time,
            total_completed_qty as production_qty_pcs, bom_no
        FROM `tabJob Card`
        WHERE docstatus < 2 {{conditions}}
        ORDER BY posting_date DESC
    """.format(conditions=conditions), filters, as_dict=1)
    
    data = []
    if not job_cards:
        return data
        
    # Forcefully map Work Order BOMs to ensure we always use the active BOM
    wo_names = list(set([jc.work_order for jc in job_cards if jc.work_order]))
    if wo_names:
        wo_bom_data = frappe.db.sql("""
            SELECT name, bom_no FROM `tabWork Order` WHERE name IN %s
        """, (tuple(wo_names),), as_dict=1)
        wo_bom_map = {w.name: w.bom_no for w in wo_bom_data if w.bom_no}
        for jc in job_cards:
            if jc.work_order and wo_bom_map.get(jc.work_order):
                jc.bom_no = wo_bom_map.get(jc.work_order)
    
    # Pre-fetch Item UOMs
    item_uoms = {}
    items = set([jc.item_code for jc in job_cards if jc.item_code])
    if items:
        uom_data = frappe.db.sql("SELECT name, stock_uom, weight_per_unit FROM `tabItem` WHERE name IN %s", (tuple(items),), as_dict=1)
        for u in uom_data:
            item_uoms[u.name] = {
                "stock_uom": (u.stock_uom or "").strip().lower(),
                "weight_per_unit": u.weight_per_unit or 0.0
            }

    # Memoize BOM conversion factors
    bom_conversion_cache = {}

    def get_kg_to_pc_factor(current_item):
        if current_item in bom_conversion_cache:
            return bom_conversion_cache[current_item]
            
        uom = frappe.db.get_value("Item", current_item, "stock_uom")
        if uom and uom.lower() in ["nos", "pcs", "pieces"]:
            bom_conversion_cache[current_item] = 1.0
            return 1.0
            
        parent_link = frappe.db.sql("""
            SELECT bi.parent, bi.stock_qty, b.item as parent_item, b.quantity as base_qty
            FROM `tabBOM Item` bi
            JOIN `tabBOM` b ON bi.parent = b.name
            WHERE bi.item_code = %s AND b.is_active = 1
            LIMIT 1
        """, (current_item,), as_dict=1)
        
        if not parent_link:
            bom_conversion_cache[current_item] = 1.0
            return 1.0
            
        link = parent_link[0]
        qty_required = link.stock_qty / (link.base_qty or 1.0)
        
        parent_factor = get_kg_to_pc_factor(link.parent_item)
        final_factor = qty_required * parent_factor
        bom_conversion_cache[current_item] = final_factor
        return final_factor
        
    # Pre-fetch BOM Scrap logic
    bom_scrap_ratios = {}
    boms = set([jc.bom_no for jc in job_cards if jc.bom_no])
    if boms:
        bom_details = frappe.db.sql("""
            SELECT name, quantity FROM `tabBOM` WHERE name IN %s
        """, (tuple(boms),), as_dict=1)
        
        bom_scrap_details = frappe.db.sql("""
            SELECT parent, sum(stock_qty) as total_scrap 
            FROM `tabBOM Scrap Item` 
            WHERE parent IN %s 
            GROUP BY parent
        """, (tuple(boms),), as_dict=1)
        
        scrap_map = {s.parent: s.total_scrap for s in bom_scrap_details}
        
        for b in bom_details:
            total_scrap = scrap_map.get(b.name, 0.0)
            if b.quantity:
                bom_scrap_ratios[b.name] = total_scrap / b.quantity
            else:
                bom_scrap_ratios[b.name] = 0.0
                
    # Pre-fetch Stock Entry (Manufacture) Production quantities linked to Work Order & Date
    work_orders = set([jc.work_order for jc in job_cards if jc.work_order])
    se_production_map = {}
    
    if work_orders:
        se_data = frappe.db.sql("""
            SELECT work_order, posting_date, sum(fg_completed_qty) as total_produced
            FROM `tabStock Entry`
            WHERE work_order IN %s AND purpose = 'Manufacture' AND docstatus = 1
            GROUP BY work_order, posting_date
        """, (tuple(work_orders),), as_dict=1)
        
        for se in se_data:
            if se.work_order and se.posting_date:
                se_production_map[(se.work_order, se.posting_date)] = se.total_produced
                
    # Filter by Employee (Operator) if specified in filters
    filter_employee = filters.get("employee")

    for jc in job_cards:
        # Get Operator Name from Time Logs
        operator_name = ""
        employee_match = True
        
        time_logs = frappe.db.sql("""
            SELECT GROUP_CONCAT(DISTINCT e.employee_name SEPARATOR ', ') as emp_names,
                   GROUP_CONCAT(DISTINCT tl.employee SEPARATOR ', ') as emp_ids
            FROM `tabJob Card Time Log` tl
            LEFT JOIN `tabEmployee` e ON e.name = tl.employee
            WHERE tl.parent = %s
        """, (jc.job_card,), as_dict=1)
        
        if time_logs and time_logs[0]:
            operator_name = time_logs[0].get("emp_names") or ""
            emp_ids = time_logs[0].get("emp_ids") or ""
            if filter_employee and filter_employee not in emp_ids:
                employee_match = False
                
        if not employee_match:
            continue
            
        # Determine UOM and calculate Pcs vs Kgs
        item_info = item_uoms.get(jc.item_code, {})
        uom = item_info.get("stock_uom", "")
        weight = item_info.get("weight_per_unit", 0.0)
        
        raw_qty = jc.production_qty_pcs or 0.0
        
        if uom in ["kg", "kgs"]:
            production_qty_kgs = raw_qty
            factor = get_kg_to_pc_factor(jc.item_code)
            production_qty_pcs = raw_qty / factor if factor > 0 else raw_qty
        else:
            production_qty_pcs = raw_qty
            production_qty_kgs = raw_qty * weight
        
        # Scrap as per BOM (based on the Job Card's base QTY which is raw_qty)
        ratio = bom_scrap_ratios.get(jc.bom_no, 0.0)
        scrap_as_per_bom = raw_qty * ratio
        
        # Actual Scrap from Job Card Scrap Items (Secondary Items tab)
        actual_scrap = 0.0
        
        scrap_items = frappe.db.sql("""
            SELECT sum(stock_qty) FROM `tabJob Card Scrap Item` WHERE parent = %s
        """, (jc.job_card,))
        
        if scrap_items and scrap_items[0][0]:
            actual_scrap = scrap_items[0][0]
            
        difference = actual_scrap - scrap_as_per_bom
        
        row = {
            "posting_date": jc.posting_date,
            "job_card": jc.job_card,
            "work_order": jc.work_order,
            "item_code": jc.item_code,
            "item_name": jc.item_name,
            "status": jc.status,
            "workstation": jc.workstation,
            "operation": jc.operation,
            "operation_time": jc.operation_time,
            "operator_name": operator_name,
            "stock_entry_qty": se_production_map.get((jc.work_order, jc.posting_date), 0.0),
            "production_qty_pcs": production_qty_pcs,
            "production_qty_kgs": production_qty_kgs,
            "scrap_as_per_bom": scrap_as_per_bom,
            "actual_scrap": actual_scrap,
            "difference": difference
        }
        data.append(row)
        
    return data

def get_conditions(filters):
    conditions = ""
    if filters.get("company"):
        conditions += " AND company = %(company)s"
    if filters.get("from_date"):
        conditions += " AND posting_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND posting_date <= %(to_date)s"
    if filters.get("workstation"):
        conditions += " AND workstation = %(workstation)s"
    if filters.get("status"):
        conditions += " AND status = %(status)s"
        
    if filters.get("item_code"):
        items = filters.get("item_code")
        if isinstance(items, list):
            item_list = ", ".join(f"'{i}'" for i in items)
            conditions += f" AND production_item IN ({item_list})"
        else:
            conditions += f" AND production_item = '{items}'"
            
    if filters.get("operation"):
        ops = filters.get("operation")
        if isinstance(ops, list):
            op_list = ", ".join(f"'{o}'" for o in ops)
            conditions += f" AND operation IN ({op_list})"
        else:
            conditions += f" AND operation = '{ops}'"
            
    return conditions
