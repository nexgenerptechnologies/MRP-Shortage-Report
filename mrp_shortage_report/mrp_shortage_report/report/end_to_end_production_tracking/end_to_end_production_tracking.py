import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = {}
        
    columns = get_columns()
    data = get_data(filters)
    
    return columns, data

def get_columns():
    return [
        {"fieldname": "sales_order", "label": _("Sales Order No."), "fieldtype": "Link", "options": "Sales Order", "width": 140},
        {"fieldname": "so_date", "label": _("SO Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 140},
        {"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 150},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 150},
        
        {"fieldname": "so_qty", "label": _("SO Qty"), "fieldtype": "Float", "width": 100},
        {"fieldname": "pending_for_planning", "label": _("Pending for Planning"), "fieldtype": "Float", "width": 150},
        
        {"fieldname": "production_plan", "label": _("Production Plan No."), "fieldtype": "Link", "options": "Production Plan", "width": 160},
        {"fieldname": "pp_date", "label": _("PP Date"), "fieldtype": "Date", "width": 100},
        {"fieldname": "pp_status", "label": _("PP Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "planned_qty", "label": _("Planned Qty"), "fieldtype": "Float", "width": 110},
        {"fieldname": "finished_qty", "label": _("Finished Qty"), "fieldtype": "Float", "width": 110},
        
        {"fieldname": "work_order", "label": _("Work Order No."), "fieldtype": "Link", "options": "Work Order", "width": 150},
        {"fieldname": "wo_status", "label": _("WO Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "wo_qty_kgs", "label": _("WO Qty (Kgs)"), "fieldtype": "Float", "width": 120},
        {"fieldname": "wo_qty_pcs", "label": _("WO Qty (Pcs)"), "fieldtype": "Float", "width": 120},
        {"fieldname": "wo_comp_kgs", "label": _("WO Completed (Kgs)"), "fieldtype": "Float", "width": 150},
        {"fieldname": "wo_comp_pcs", "label": _("WO Completed (Pcs)"), "fieldtype": "Float", "width": 150},
        {"fieldname": "wo_pending_kgs", "label": _("WO Pending (Kgs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "wo_pending_pcs", "label": _("WO Pending (Pcs)"), "fieldtype": "Float", "width": 140},
        
        {"fieldname": "operation", "label": _("Operation Name"), "fieldtype": "Link", "options": "Operation", "width": 140},
        {"fieldname": "job_card", "label": _("Job Card No."), "fieldtype": "Link", "options": "Job Card", "width": 150},
        {"fieldname": "jc_status", "label": _("JC Status"), "fieldtype": "Data", "width": 100},
        {"fieldname": "jc_qty_kgs", "label": _("JC Qty (Kgs)"), "fieldtype": "Float", "width": 120},
        {"fieldname": "jc_qty_pcs", "label": _("JC Qty (Pcs)"), "fieldtype": "Float", "width": 120},
        {"fieldname": "jc_comp_kgs", "label": _("JC Completed (Kgs)"), "fieldtype": "Float", "width": 150},
        {"fieldname": "jc_comp_pcs", "label": _("JC Completed (Pcs)"), "fieldtype": "Float", "width": 150},
        {"fieldname": "jc_pending_kgs", "label": _("JC Pending (Kgs)"), "fieldtype": "Float", "width": 140},
        {"fieldname": "jc_pending_pcs", "label": _("JC Pending (Pcs)"), "fieldtype": "Float", "width": 140},
    ]

def get_data(filters):
    data = []
    
    # --- 1. Fetch Sales Orders ---
    so_conditions = ["so.docstatus = 1", "so.status NOT IN ('Closed', 'Completed')"]
    so_values = {}
    
    if filters.get("company"):
        so_conditions.append("so.company = %(company)s")
        so_values["company"] = filters.get("company")
    if filters.get("sales_order"):
        so_conditions.append("so.name = %(sales_order)s")
        so_values["sales_order"] = filters.get("sales_order")
    if filters.get("customer"):
        so_conditions.append("so.customer = %(customer)s")
        so_values["customer"] = filters.get("customer")
    if filters.get("item_code"):
        so_conditions.append("soi.item_code = %(item_code)s")
        so_values["item_code"] = filters.get("item_code")
        
    so_query = f"""
        SELECT
            soi.name as soi_name, soi.parent as so_name, so.transaction_date as so_date, so.customer,
            soi.item_code, soi.item_name, soi.qty as so_qty
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON soi.parent = so.name
        WHERE {" AND ".join(so_conditions)}
        ORDER BY so.transaction_date DESC
    """
    
    so_items = frappe.db.sql(so_query, so_values, as_dict=1)
    
    # Caches for conversions
    conversion_cache = {}
    
    def get_yield_pcs(fg_item_code, component_item_code, component_qty):
        if fg_item_code == component_item_code:
            return component_qty
            
        fg_bom = frappe.db.get_value("Item", fg_item_code, "default_bom")
        if not fg_bom:
            return component_qty
            
        bom_base_qty = frappe.db.get_value("BOM", fg_bom, "quantity") or 1.0
        
        exploded_qty = frappe.db.get_value("BOM Exploded Item", {"parent": fg_bom, "item_code": component_item_code}, "stock_qty")
        if exploded_qty:
            qty_per_fg = exploded_qty / bom_base_qty
            if qty_per_fg > 0:
                return component_qty / qty_per_fg
                
        # Fallback to direct BOM Items if not fully exploded
        bom_item_qty = frappe.db.get_value("BOM Item", {"parent": fg_bom, "item_code": component_item_code}, "stock_qty")
        if bom_item_qty:
            qty_per_fg = bom_item_qty / bom_base_qty
            if qty_per_fg > 0:
                return component_qty / qty_per_fg
                
        return component_qty
        
    def get_qty_in_kgs_and_pcs(so_item_code, item_code, qty):
        if not qty: return 0.0, 0.0
        
        if item_code not in conversion_cache:
            item_doc = frappe.get_cached_doc("Item", item_code)
            stock_uom = item_doc.stock_uom and item_doc.stock_uom.strip().lower()
            
            pcs_factor = 1.0
            kgs_factor = 1.0
            
            if stock_uom in ['kg', 'kgs']:
                for uom in item_doc.uoms:
                    if uom.uom.strip().lower() in ['pcs', 'nos', 'piece']:
                        pcs_factor = 1.0 / (uom.conversion_factor or 1.0)
                        break
            elif stock_uom in ['pcs', 'nos', 'piece']:
                for uom in item_doc.uoms:
                    if uom.uom.strip().lower() in ['kg', 'kgs']:
                        kgs_factor = 1.0 / (uom.conversion_factor or 1.0)
                        break
                        
            conversion_cache[item_code] = {
                "stock_uom": stock_uom,
                "pcs_factor": pcs_factor,
                "kgs_factor": kgs_factor
            }
            
        cache = conversion_cache[item_code]
        stock_uom = cache["stock_uom"]
        
        qty_kgs = 0.0
        qty_pcs = 0.0
        
        if stock_uom in ['kg', 'kgs']:
            qty_kgs = qty
            qty_pcs = get_yield_pcs(so_item_code, item_code, qty)
        elif stock_uom in ['pcs', 'nos', 'piece']:
            qty_pcs = qty
            qty_kgs = qty * cache["kgs_factor"]
        else:
            qty_pcs = qty
            qty_kgs = qty * cache["kgs_factor"]
            
        return qty_kgs, qty_pcs
        
    for so_row in so_items:
        # Fetch Production Plans for this SO Item
        pp_query = """
            SELECT 
                ppi.name as ppi_name, ppi.parent as pp_name, pp.posting_date as pp_date, pp.status as pp_status,
                ppi.planned_qty, ppi.produced_qty as finished_qty
            FROM `tabProduction Plan Item` ppi
            INNER JOIN `tabProduction Plan` pp ON ppi.parent = pp.name
            WHERE ppi.sales_order = %s AND ppi.sales_order_item = %s AND pp.docstatus = 1
        """
        
        pp_filter_vals = [so_row.so_name, so_row.soi_name]
        
        if filters.get("production_plan"):
            pp_query += " AND pp.name = %s"
            pp_filter_vals.append(filters.get("production_plan"))
            
        pp_items = frappe.db.sql(pp_query, tuple(pp_filter_vals), as_dict=1)
        
        total_planned_for_so = sum([p.planned_qty for p in pp_items]) if pp_items else 0.0
        pending_for_planning = so_row.so_qty - total_planned_for_so
        
        base_row = {
            "sales_order": so_row.so_name,
            "so_date": so_row.so_date,
            "customer": so_row.customer,
            "item_code": so_row.item_code,
            "item_name": so_row.item_name,
            "so_qty": so_row.so_qty,
            "pending_for_planning": pending_for_planning if pending_for_planning > 0 else 0.0
        }
        
        if not pp_items:
            # No Production Plan yet
            data.append(base_row)
            continue
            
        for pp_row in pp_items:
            pp_base_row = base_row.copy()
            pp_base_row.update({
                "production_plan": pp_row.pp_name,
                "pp_date": pp_row.pp_date,
                "pp_status": pp_row.pp_status,
                "planned_qty": pp_row.planned_qty,
                "finished_qty": pp_row.finished_qty
            })
            
            # Fetch ALL Work Orders for this PP that belong to this Sales Order (including sub-assemblies)
            wo_query = """
                SELECT 
                    name as wo_name, status as wo_status, production_item, sales_order,
                    qty as wo_qty, produced_qty as wo_completed_qty
                FROM `tabWork Order`
                WHERE production_plan = %s AND docstatus < 2
            """
            wo_filter_vals = [pp_row.pp_name]
            
            if filters.get("work_order"):
                wo_query += " AND name = %s"
                wo_filter_vals.append(filters.get("work_order"))
                
            work_orders = frappe.db.sql(wo_query, tuple(wo_filter_vals), as_dict=1)
            
            # Filter Work Orders to only those relevant to this Sales Order row
            valid_work_orders = []
            for wo in work_orders:
                if wo.sales_order == so_row.so_name or wo.production_item == so_row.item_code or not wo.sales_order:
                    valid_work_orders.append(wo)
            
            if not valid_work_orders:
                data.append(pp_base_row)
                continue
                
            for wo_row in valid_work_orders:
                wo_base_row = pp_base_row.copy()
                
                wo_item_code = wo_row.production_item
                wo_item_name = frappe.db.get_value("Item", wo_item_code, "item_name")
                
                wo_qty_kgs, wo_qty_pcs = get_qty_in_kgs_and_pcs(so_row.item_code, wo_item_code, wo_row.wo_qty)
                wo_comp_kgs, wo_comp_pcs = get_qty_in_kgs_and_pcs(so_row.item_code, wo_item_code, wo_row.wo_completed_qty)
                
                wo_base_row.update({
                    "item_code": wo_item_code,  # Override to show the actual sub-assembly being built
                    "item_name": wo_item_name,
                    "work_order": wo_row.wo_name,
                    "wo_status": wo_row.wo_status,
                    "wo_qty_kgs": wo_qty_kgs,
                    "wo_qty_pcs": wo_qty_pcs,
                    "wo_comp_kgs": wo_comp_kgs,
                    "wo_comp_pcs": wo_comp_pcs,
                    "wo_pending_kgs": wo_qty_kgs - wo_comp_kgs,
                    "wo_pending_pcs": wo_qty_pcs - wo_comp_pcs
                })
                
                # Fetch Job Cards for this Work Order
                job_cards = frappe.db.sql("""
                    SELECT 
                        name as jc_name, status as jc_status, operation,
                        for_quantity as jc_qty, total_completed_qty as jc_completed_qty
                    FROM `tabJob Card`
                    WHERE work_order = %s AND docstatus = 1
                    ORDER BY creation ASC
                """, (wo_row.wo_name,), as_dict=1)
                
                if not job_cards:
                    data.append(wo_base_row)
                    continue
                    
                for jc_row in job_cards:
                    jc_base_row = wo_base_row.copy()
                    
                    jc_qty_kgs, jc_qty_pcs = get_qty_in_kgs_and_pcs(so_row.item_code, wo_item_code, jc_row.jc_qty)
                    jc_comp_kgs, jc_comp_pcs = get_qty_in_kgs_and_pcs(so_row.item_code, wo_item_code, jc_row.jc_completed_qty)
                    
                    jc_base_row.update({
                        "job_card": jc_row.jc_name,
                        "operation": jc_row.operation,
                        "jc_status": jc_row.jc_status,
                        "jc_qty_kgs": jc_qty_kgs,
                        "jc_qty_pcs": jc_qty_pcs,
                        "jc_comp_kgs": jc_comp_kgs,
                        "jc_comp_pcs": jc_comp_pcs,
                        "jc_pending_kgs": jc_qty_kgs - jc_comp_kgs,
                        "jc_pending_pcs": jc_qty_pcs - jc_comp_pcs
                    })
                    
                    data.append(jc_base_row)
                    
    return data
