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
        {"fieldname": "sales_order", "label": _("Sales Order No"), "fieldtype": "Link", "options": "Sales Order", "width": 140},
        {"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 140},
        {"fieldname": "so_date", "label": _("Sales Order Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 130},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 130},
        {"fieldname": "order_qty", "label": _("Order Qty"), "fieldtype": "Float", "width": 100},
        {"fieldname": "stock_qty", "label": _("Stock Qty"), "fieldtype": "Float", "width": 100},
        
        {"fieldname": "production_plan", "label": _("Production Plan Number"), "fieldtype": "Link", "options": "Production Plan", "width": 160},
        {"fieldname": "pp_date", "label": _("Production Plan Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "pp_qty", "label": _("Total Production Plan Quantity in Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pp_bal", "label": _("Total Balance for production plan in Pcs"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "work_order", "label": _("Work order Number"), "fieldtype": "Link", "options": "Work Order", "width": 140},
        {"fieldname": "wo_date", "label": _("Work order date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "wo_qty", "label": _("Total Work order Quantity Against Production Plan Quantity in Pcs"), "fieldtype": "Float", "width": 190},
        
        # Cutting/Bending
        {"fieldname": "cut_comp", "label": _("Total Cutting/Bending Quantity completed against work order (in Pcs)"), "fieldtype": "Float", "width": 180},
        {"fieldname": "cut_bal", "label": _("Total Cutting/Bending balance against work order (in Pcs)"), "fieldtype": "Float", "width": 180},
        
        # Vibro Cleaning
        {"fieldname": "vibro_avail", "label": _("Total Vibro Cleaning Quantity available for vibro cleaning in pcs"), "fieldtype": "Float", "width": 180},
        {"fieldname": "vibro_comp", "label": _("Total Vibro Cleaning Completed Against work order completed (in pcs)"), "fieldtype": "Float", "width": 180},
        {"fieldname": "vibro_bal", "label": _("Total Vibro Cleaning balance against work order completed (in pcs)"), "fieldtype": "Float", "width": 180},
        
        # Plating
        {"fieldname": "plate_avail", "label": _("Total ready Quantity available for plating in pcs"), "fieldtype": "Float", "width": 180},
        {"fieldname": "plate_comp", "label": _("Total Plating Completed against work order completed (in Pcs)"), "fieldtype": "Float", "width": 180},
        {"fieldname": "plate_bal", "label": _("Total Plating balance against work order completed (in Pcs)"), "fieldtype": "Float", "width": 180},
        
        # Packaging
        {"fieldname": "pack_comp", "label": _("Packaging Completed against work order completed (in Pcs)"), "fieldtype": "Float", "width": 180},
        {"fieldname": "pack_bal", "label": _("Packaging balance against work order completed (in Pcs)"), "fieldtype": "Float", "width": 180},
        
        # Fulfillment
        {"fieldname": "fg_avail", "label": _("FG Available Quantity (in Pcs)"), "fieldtype": "Float", "width": 150},
        {"fieldname": "dispatch_qty", "label": _("Dispatched Quantity (in Pcs)"), "fieldtype": "Float", "width": 150},
        {"fieldname": "dispatch_bal", "label": _("Pending for Dispatch (in Pcs)"), "fieldtype": "Float", "width": 150},
    ]

def get_data(filters):
    data = []
    
    # --- 1. Fetch Sales Orders ---
    so_conditions = ["so.docstatus = 1"]
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
    if filters.get("from_date"):
        so_conditions.append("so.transaction_date >= %(from_date)s")
        so_values["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        so_conditions.append("so.transaction_date <= %(to_date)s")
        so_values["to_date"] = filters.get("to_date")
        
    so_query = f"""
        SELECT
            soi.name as soi_name, soi.parent as so_name, so.transaction_date as so_date, so.customer_name,
            soi.item_code, soi.item_name, soi.qty as so_qty, soi.stock_qty
        FROM `tabSales Order Item` soi
        INNER JOIN `tabSales Order` so ON soi.parent = so.name
        WHERE {" AND ".join(so_conditions)}
        ORDER BY so.transaction_date DESC
    """
    
    so_items = frappe.db.sql(so_query, so_values, as_dict=1)
    
    # --- Caches and Converters ---
    bom_yield_cache = {}
    conversion_cache = {}
    
    def get_qty_per_fg_recursive(bom_no, target_item, current_qty=1.0):
        if not bom_no: return 0.0
        bom_items = frappe.db.sql("SELECT item_code, bom_no, stock_qty FROM `tabBOM Item` WHERE parent = %s", (bom_no,), as_dict=1)
        bom_base_qty = frappe.db.get_value("BOM", bom_no, "quantity") or 1.0
        total_found = 0.0
        for item in bom_items:
            qty_per_parent = item.stock_qty / bom_base_qty
            required_qty = current_qty * qty_per_parent
            if item.item_code == target_item:
                total_found += required_qty
            if item.bom_no:
                total_found += get_qty_per_fg_recursive(item.bom_no, target_item, required_qty)
        return total_found

    def get_yield_pcs(fg_item_code, component_item_code, component_qty):
        if fg_item_code == component_item_code: return component_qty
        fg_bom = frappe.db.get_value("Item", fg_item_code, "default_bom")
        if not fg_bom: return component_qty
        cache_key = f"{fg_bom}_{component_item_code}"
        if cache_key not in bom_yield_cache:
            bom_yield_cache[cache_key] = get_qty_per_fg_recursive(fg_bom, component_item_code, 1.0)
        qty_per_fg = bom_yield_cache[cache_key]
        if qty_per_fg and qty_per_fg > 0:
            return component_qty / qty_per_fg
        return component_qty
        
    def get_qty_pcs(so_item_code, item_code, qty):
        if not qty: return 0.0
        if item_code not in conversion_cache:
            item_doc = frappe.get_cached_doc("Item", item_code)
            stock_uom = item_doc.stock_uom and item_doc.stock_uom.strip().lower()
            conversion_cache[item_code] = {"stock_uom": stock_uom}
        cache = conversion_cache[item_code]
        if cache["stock_uom"] in ['kg', 'kgs']:
            return get_yield_pcs(so_item_code, item_code, qty)
        return qty # Assume already in pieces if not Kg
        
    # --- Processing Loop ---
    for so_row in so_items:
        # Fetch Dispatched Qty from Sales Invoice
        inv_items = frappe.db.sql("""
            SELECT sum(sii.qty)
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE sii.sales_order = %s AND sii.so_detail = %s AND si.docstatus = 1
        """, (so_row.so_name, so_row.soi_name))
        dispatch_qty = inv_items[0][0] if (inv_items and inv_items[0][0]) else 0.0
        dispatch_qty_pcs = get_qty_pcs(so_row.item_code, so_row.item_code, dispatch_qty)
        
        base_row = {
            "sales_order": so_row.so_name,
            "customer_name": so_row.customer_name,
            "so_date": so_row.so_date,
            "item_code": so_row.item_code,
            "item_name": so_row.item_name,
            "order_qty": get_qty_pcs(so_row.item_code, so_row.item_code, so_row.so_qty),
            "stock_qty": so_row.stock_qty,
            "dispatch_qty": dispatch_qty_pcs,
            "dispatch_bal": get_qty_pcs(so_row.item_code, so_row.item_code, so_row.so_qty) - dispatch_qty_pcs
        }
        
        # Fetch Production Plans
        pp_query = """
            SELECT ppi.name as ppi_name, ppi.parent as pp_name, pp.posting_date as pp_date,
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
        
        if not pp_items:
            data.append(base_row)
            continue
            
        for pp_row in pp_items:
            pp_base_row = base_row.copy()
            pp_qty_pcs = get_qty_pcs(so_row.item_code, so_row.item_code, pp_row.planned_qty)
            pp_finish_pcs = get_qty_pcs(so_row.item_code, so_row.item_code, pp_row.finished_qty)
            
            pp_base_row.update({
                "production_plan": pp_row.pp_name,
                "pp_date": pp_row.pp_date,
                "pp_qty": pp_qty_pcs,
                "pp_bal": pp_qty_pcs - pp_finish_pcs
            })
            
            # Fetch ALL Work Orders for this PP
            work_orders = frappe.db.sql("""
                SELECT name as wo_name, creation as wo_date, production_item, sales_order,
                    qty as wo_qty, produced_qty as wo_completed_qty
                FROM `tabWork Order`
                WHERE production_plan = %s AND docstatus < 2
            """, (pp_row.pp_name,), as_dict=1)
            
            valid_work_orders = [wo for wo in work_orders if wo.sales_order == so_row.so_name or wo.production_item == so_row.item_code or not wo.sales_order]
            
            if not valid_work_orders:
                data.append(pp_base_row)
                continue
                
            for wo_row in valid_work_orders:
                wo_base_row = pp_base_row.copy()
                wo_item = wo_row.production_item
                
                wo_qty_pcs = get_qty_pcs(so_row.item_code, wo_item, wo_row.wo_qty)
                wo_base_row.update({
                    "item_code": wo_item, # Override item code for sub-assemblies
                    "item_name": frappe.db.get_value("Item", wo_item, "item_name"),
                    "work_order": wo_row.wo_name,
                    "wo_date": wo_row.wo_date.date() if wo_row.wo_date else None,
                    "wo_qty": wo_qty_pcs
                })
                
                # Fetch Job Cards
                job_cards = frappe.db.sql("""
                    SELECT operation, for_quantity as jc_qty, total_completed_qty as comp_qty
                    FROM `tabJob Card`
                    WHERE work_order = %s AND docstatus = 1
                """, (wo_row.wo_name,), as_dict=1)
                
                # Pivot variables
                cut_comp = 0.0
                vibro_comp = 0.0
                plate_comp = 0.0
                pack_comp = 0.0
                
                for jc in job_cards:
                    op = jc.operation or ""
                    comp = get_qty_pcs(so_row.item_code, wo_item, jc.comp_qty)
                    
                    if "Cutting & Bending" in op:
                        cut_comp += comp
                    elif "Vibro Cleaning" in op:
                        vibro_comp += comp
                    elif "Plating" in op:
                        plate_comp += comp
                    elif "Packaging" in op:
                        pack_comp += comp
                        
                # Calculations
                cut_bal = wo_qty_pcs - cut_comp
                
                vibro_avail = cut_comp - vibro_comp
                vibro_bal = wo_qty_pcs - vibro_comp
                
                plate_avail = vibro_comp - plate_comp
                plate_bal = wo_qty_pcs - plate_comp
                
                pack_bal = wo_qty_pcs - pack_comp
                
                fg_avail = pack_comp - dispatch_qty_pcs
                
                wo_base_row.update({
                    "cut_comp": cut_comp,
                    "cut_bal": cut_bal if cut_bal > 0 else 0,
                    
                    "vibro_avail": vibro_avail if vibro_avail > 0 else 0,
                    "vibro_comp": vibro_comp,
                    "vibro_bal": vibro_bal if vibro_bal > 0 else 0,
                    
                    "plate_avail": plate_avail if plate_avail > 0 else 0,
                    "plate_comp": plate_comp,
                    "plate_bal": plate_bal if plate_bal > 0 else 0,
                    
                    "pack_comp": pack_comp,
                    "pack_bal": pack_bal if pack_bal > 0 else 0,
                    
                    "fg_avail": fg_avail if fg_avail > 0 else 0
                })
                
                data.append(wo_base_row)
                
    return data
