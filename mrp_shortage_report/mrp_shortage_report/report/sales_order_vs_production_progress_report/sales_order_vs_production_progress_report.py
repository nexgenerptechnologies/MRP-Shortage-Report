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
        inv_items = frappe.db.sql("""
            SELECT sum(sii.qty)
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE sii.sales_order = %s AND sii.so_detail = %s AND si.docstatus = 1
        """, (so_row.so_name, so_row.soi_name))
        dispatch_qty = inv_items[0][0] if (inv_items and inv_items[0][0]) else 0.0
        dispatch_qty_pcs = get_qty_pcs(so_row.item_code, so_row.item_code, dispatch_qty)
        
        pp_items = frappe.db.sql("""
            SELECT pp.name as pp_name, pp.posting_date as pp_date,
                ppi.planned_qty, ppi.produced_qty as finished_qty
            FROM `tabProduction Plan Item` ppi
            INNER JOIN `tabProduction Plan` pp ON ppi.parent = pp.name
            WHERE ppi.sales_order = %s AND ppi.sales_order_item = %s AND pp.docstatus = 1
        """, (so_row.so_name, so_row.soi_name), as_dict=1)
        
        pp_names = [p.pp_name for p in pp_items]
        
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
        
        wo_map = {wo.wo_name: wo for wo in valid_wos}
        for dwo in direct_wos:
            wo_map[dwo.wo_name] = dwo
        valid_wos = list(wo_map.values())
        
        fg_bom = frappe.db.get_value("Item", so_row.item_code, "default_bom")
        
        def process_branch(branch_item, branch_bom, parent_id, indent, branch_req_qty, is_root=False):
            row_id = frappe.generate_hash(length=8)
            
            # State to accumulate WIP operations into this branch row
            state = {
                "max_wo_qty": 0.0,
                "cut_comp": 0.0,
                "vibro_comp": 0.0,
                "plate_comp": 0.0,
                "pack_comp": 0.0,
                "req_ops": set(),
                "has_child": 0
            }
            
            def traverse_wip(current_item, bom_no, req_qty):
                # 1. Accumulate Work Order Qtys (take MAX to avoid duplicating qty in a chain)
                item_wos = [wo for wo in valid_wos if wo.production_item == current_item]
                for wo in item_wos:
                    wo_qty = get_qty_pcs(so_row.item_code, current_item, wo.wo_qty)
                    if wo_qty > state["max_wo_qty"]:
                        state["max_wo_qty"] = wo_qty
                        
                # 2. Accumulate Job Cards
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
                        if "Cutting & Bending" in op: state["cut_comp"] += comp
                        elif "Vibro Cleaning" in op: state["vibro_comp"] += comp
                        elif "Plating" in op: state["plate_comp"] += comp
                        elif "Packaging" in op: state["pack_comp"] += comp
                        
                # 3. Accumulate Operations & Recurse Children
                if bom_no:
                    bom_ops = frappe.db.sql("SELECT operation FROM `tabBOM Operation` WHERE parent = %s", bom_no, as_dict=1)
                    state["req_ops"].update([op.operation for op in bom_ops if op.operation])
                    
                    bom_items = frappe.db.sql("SELECT item_code, bom_no, stock_qty FROM `tabBOM Item` WHERE parent = %s", bom_no, as_dict=1)
                    bom_base_qty = frappe.db.get_value("BOM", bom_no, "quantity") or 1.0
                    
                    for child in bom_items:
                        if child.bom_no: # Process sub-assemblies
                            child_req_qty = req_qty * (child.stock_qty / bom_base_qty)
                            if child.item_code.startswith("FGD"):
                                # If it's an FGD, Branch it into a new row!
                                state["has_child"] = 1
                                process_branch(child.item_code, child.bom_no, row_id, indent + 1, child_req_qty)
                            else:
                                # If it's a WIP, traverse and Roll it up into THIS state!
                                traverse_wip(child.item_code, child.bom_no, child_req_qty)

            # Start traversing this branch
            traverse_wip(branch_item, branch_bom, branch_req_qty)
            
            has_cut = any("Cutting & Bending" in o for o in state["req_ops"])
            has_vibro = any("Vibro Cleaning" in o for o in state["req_ops"])
            has_plate = any("Plating" in o for o in state["req_ops"])
            has_pack = any("Packaging" in o for o in state["req_ops"])
            
            total_wo_qty = state["max_wo_qty"]
            prev_comp = total_wo_qty
            
            row = {
                "id": row_id,
                "parent_id": parent_id,
                "indent": indent,
                
                "item_code": branch_item,
                "item_name": frappe.db.get_value("Item", branch_item, "item_name") or branch_item,
                "order_qty": branch_req_qty,
                "wo_qty": total_wo_qty,
                "has_child": state["has_child"]
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
                    "dispatch_bal": max(0, branch_req_qty - dispatch_qty_pcs)
                })
            
            if has_cut:
                row["cut_comp"] = state["cut_comp"]
                row["cut_bal"] = max(0, total_wo_qty - state["cut_comp"])
                prev_comp = state["cut_comp"]
            else:
                row["cut_comp"] = 0
                row["cut_bal"] = 0
                
            if has_vibro:
                row["vibro_avail"] = max(0, prev_comp - state["vibro_comp"])
                row["vibro_comp"] = state["vibro_comp"]
                row["vibro_bal"] = max(0, total_wo_qty - state["vibro_comp"])
                prev_comp = state["vibro_comp"]
            else:
                row["vibro_avail"] = 0
                row["vibro_comp"] = 0
                row["vibro_bal"] = 0
                
            if has_plate:
                row["plate_avail"] = max(0, prev_comp - state["plate_comp"])
                row["plate_comp"] = state["plate_comp"]
                row["plate_bal"] = max(0, total_wo_qty - state["plate_comp"])
                prev_comp = state["plate_comp"]
            else:
                row["plate_avail"] = 0
                row["plate_comp"] = 0
                row["plate_bal"] = 0
                
            if has_pack:
                row["pack_comp"] = state["pack_comp"]
                row["pack_bal"] = max(0, total_wo_qty - state["pack_comp"])
                prev_comp = state["pack_comp"]
            else:
                row["pack_comp"] = 0
                row["pack_bal"] = 0
                
            if is_root:
                fg_avail = state["pack_comp"] - dispatch_qty_pcs
                row["fg_avail"] = fg_avail if fg_avail > 0 else 0
                
            data.append(row)
                        
        process_branch(so_row.item_code, fg_bom, "", 0, get_qty_pcs(so_row.item_code, so_row.item_code, so_row.so_qty), is_root=True)

    return data
