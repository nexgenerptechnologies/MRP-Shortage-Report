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
        {"fieldname": "id", "label": "ID", "fieldtype": "Data", "hidden": 1},
        {"fieldname": "parent_id", "label": "Parent ID", "fieldtype": "Data", "hidden": 1},
        {"fieldname": "indent", "label": "Indent", "fieldtype": "Int", "hidden": 1},
        
        {"fieldname": "sales_order", "label": _("Sales Order No"), "fieldtype": "Link", "options": "Sales Order", "width": 140},
        {"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data", "width": 140},
        {"fieldname": "so_date", "label": _("Sales Order Date"), "fieldtype": "Date", "width": 110},
        
        {"fieldname": "item_code", "label": _("Item Code"), "fieldtype": "Link", "options": "Item", "width": 200},
        {"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 160},
        {"fieldname": "order_qty", "label": _("Order Qty"), "fieldtype": "Float", "width": 100},
        {"fieldname": "stock_qty", "label": _("Stock Qty"), "fieldtype": "Float", "width": 100},
        
        {"fieldname": "production_plan", "label": _("Production Plan Number"), "fieldtype": "Data", "width": 160},
        {"fieldname": "pp_date", "label": _("Production Plan Date"), "fieldtype": "Data", "width": 110},
        {"fieldname": "pp_qty", "label": _("Total Production Plan Quantity in Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pp_bal", "label": _("Total Balance for production plan in Pcs"), "fieldtype": "Float", "width": 160},
        
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
        return qty 
        
    for so_row in so_items:
        # Fetch Sales Invoice data for root SO
        inv_items = frappe.db.sql("""
            SELECT sum(sii.qty)
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE sii.sales_order = %s AND sii.so_detail = %s AND si.docstatus = 1
        """, (so_row.so_name, so_row.soi_name))
        dispatch_qty = inv_items[0][0] if (inv_items and inv_items[0][0]) else 0.0
        dispatch_qty_pcs = get_qty_pcs(so_row.item_code, so_row.item_code, dispatch_qty)
        
        # Pre-fetch PP for this SO Item
        pp_items = frappe.db.sql("""
            SELECT pp.name as pp_name, pp.posting_date as pp_date,
                ppi.planned_qty, ppi.produced_qty as finished_qty
            FROM `tabProduction Plan Item` ppi
            INNER JOIN `tabProduction Plan` pp ON ppi.parent = pp.name
            WHERE ppi.sales_order = %s AND ppi.sales_order_item = %s AND pp.docstatus = 1
        """, (so_row.so_name, so_row.soi_name), as_dict=1)
        
        pp_names = [p.pp_name for p in pp_items]
        
        # Pre-fetch ALL WOs linked to these PPs OR directly to the SO
        valid_wos = []
        if pp_names:
            wo_query = f"""
                SELECT name as wo_name, production_item, qty as wo_qty
                FROM `tabWork Order`
                WHERE production_plan IN ({', '.join(['%s'] * len(pp_names))}) AND docstatus < 2
            """
            valid_wos = frappe.db.sql(wo_query, tuple(pp_names), as_dict=1)
            
        direct_wos = frappe.db.sql("""
            SELECT name as wo_name, production_item, qty as wo_qty
            FROM `tabWork Order`
            WHERE sales_order = %s AND docstatus < 2
        """, (so_row.so_name,), as_dict=1)
        
        # Merge WOs ensuring no duplicates
        wo_map = {wo.wo_name: wo for wo in valid_wos}
        for dwo in direct_wos:
            wo_map[dwo.wo_name] = dwo
        valid_wos = list(wo_map.values())
        
        fg_bom = frappe.db.get_value("Item", so_row.item_code, "default_bom")
        
        # Recursive function to build the tree nodes
        def process_bom_node(current_item, bom_no, parent_id, indent, required_qty, is_root=False):
            row_id = frappe.generate_hash(length=8)
            
            item_wos = [wo for wo in valid_wos if wo.production_item == current_item]
            total_wo_qty = sum([get_qty_pcs(so_row.item_code, current_item, wo.wo_qty) for wo in item_wos])
            
            cut_comp = 0.0
            vibro_comp = 0.0
            plate_comp = 0.0
            pack_comp = 0.0
            
            wo_names = [wo.wo_name for wo in item_wos]
            if wo_names:
                job_cards = frappe.db.sql(f"""
                    SELECT operation, total_completed_qty as comp_qty
                    FROM `tabJob Card`
                    WHERE work_order IN ({', '.join(['%s']*len(wo_names))}) AND docstatus = 1
                """, tuple(wo_names), as_dict=1)
                
                for jc in job_cards:
                    op = jc.operation or ""
                    comp = get_qty_pcs(so_row.item_code, current_item, jc.comp_qty)
                    if "Cutting & Bending" in op: cut_comp += comp
                    elif "Vibro Cleaning" in op: vibro_comp += comp
                    elif "Plating" in op: plate_comp += comp
                    elif "Packaging" in op: pack_comp += comp

            # Determine operations explicitly present in THIS BOM
            req_ops = set()
            if bom_no:
                bom_ops = frappe.db.sql("SELECT operation FROM `tabBOM Operation` WHERE parent = %s", bom_no, as_dict=1)
                req_ops = set([op.operation for op in bom_ops if op.operation])
                
            has_cut = any("Cutting & Bending" in o for o in req_ops)
            has_vibro = any("Vibro Cleaning" in o for o in req_ops)
            has_plate = any("Plating" in o for o in req_ops)
            has_pack = any("Packaging" in o for o in req_ops)
            
            prev_comp = total_wo_qty
            
            row = {
                "id": row_id,
                "parent_id": parent_id,
                "indent": indent,
                
                "item_code": current_item,
                "item_name": frappe.db.get_value("Item", current_item, "item_name") or current_item,
                "order_qty": required_qty,
                "wo_qty": total_wo_qty,
                "has_child": 0
            }
            
            if is_root:
                row.update({
                    "sales_order": so_row.so_name,
                    "customer_name": so_row.customer_name,
                    "so_date": so_row.so_date,
                    "stock_qty": so_row.stock_qty,
                    "production_plan": ", ".join(list(set(pp_names))),
                    "pp_date": ", ".join(list(set([str(p.pp_date) for p in pp_items]))),
                    "pp_qty": sum([get_qty_pcs(so_row.item_code, so_row.item_code, p.planned_qty) for p in pp_items]),
                    "pp_bal": sum([get_qty_pcs(so_row.item_code, so_row.item_code, p.planned_qty - p.finished_qty) for p in pp_items]),
                    "dispatch_qty": dispatch_qty_pcs,
                    "dispatch_bal": max(0, required_qty - dispatch_qty_pcs)
                })
            
            if has_cut:
                row["cut_comp"] = cut_comp
                row["cut_bal"] = max(0, total_wo_qty - cut_comp)
                prev_comp = cut_comp
                
            if has_vibro:
                row["vibro_avail"] = max(0, prev_comp - vibro_comp)
                row["vibro_comp"] = vibro_comp
                row["vibro_bal"] = max(0, total_wo_qty - vibro_comp)
                prev_comp = vibro_comp
                
            if has_plate:
                row["plate_avail"] = max(0, prev_comp - plate_comp)
                row["plate_comp"] = plate_comp
                row["plate_bal"] = max(0, total_wo_qty - plate_comp)
                prev_comp = plate_comp
                
            if has_pack:
                row["pack_comp"] = pack_comp
                row["pack_bal"] = max(0, total_wo_qty - pack_comp)
                prev_comp = pack_comp
                
            if is_root:
                fg_avail = pack_comp - dispatch_qty_pcs
                row["fg_avail"] = fg_avail if fg_avail > 0 else 0
                
            data.append(row)
            
            # Recurse for child items with BOMs
            if bom_no:
                bom_items = frappe.db.sql("SELECT item_code, bom_no, stock_qty FROM `tabBOM Item` WHERE parent = %s", bom_no, as_dict=1)
                bom_base_qty = frappe.db.get_value("BOM", bom_no, "quantity") or 1.0
                has_children = False
                for child in bom_items:
                    if child.bom_no: # Only process sub-assemblies (they have operations)
                        has_children = True
                        child_qty_per_parent = child.stock_qty / bom_base_qty
                        child_required_qty = required_qty * child_qty_per_parent
                        process_bom_node(child.item_code, child.bom_no, row_id, indent + 1, child_required_qty)
                row["has_child"] = 1 if has_children else 0
                        
        process_bom_node(so_row.item_code, fg_bom, "", 0, get_qty_pcs(so_row.item_code, so_row.item_code, so_row.so_qty), is_root=True)

    return data
