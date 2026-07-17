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
        
        {"fieldname": "production_plan", "label": _("PP Number"), "fieldtype": "Data", "width": 160},
        {"fieldname": "pp_date", "label": _("PP Date"), "fieldtype": "Data", "width": 110},
        {"fieldname": "pp_status", "label": _("PP Status"), "fieldtype": "Data", "width": 140},
        {"fieldname": "pp_qty", "label": _("PP Qty Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pp_bal", "label": _("PP Pending Pcs"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "wo_qty", "label": _("Work Order Qty Pcs"), "fieldtype": "Float", "width": 190},
        {"fieldname": "wo_qty_kgs", "label": _("Work Order Qty Kgs"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "subcontract_kgs", "label": _("SubCont Qty kgs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "subcontract_pcs", "label": _("SubCont Qty Pcs"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "cut_comp", "label": _("Cut/Bend Qty Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "cut_comp_kgs", "label": _("Cut/Bend Qty Kg"), "fieldtype": "Float", "width": 160},
        {"fieldname": "cut_bal", "label": _("Cut/Bend Pending Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "cut_bal_kgs", "label": _("Cut/Bend Pending Kg"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "vibro_avail", "label": _("Vibro Pending Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "vibro_avail_kgs", "label": _("Vibro Pending Kg"), "fieldtype": "Float", "width": 160},
        {"fieldname": "vibro_comp", "label": _("Vibro Cleaned Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "vibro_comp_kgs", "label": _("Vibro Cleaned Kg"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "plate_avail", "label": _("Plating Pending Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "plate_avail_kgs", "label": _("Plating Pending Kg"), "fieldtype": "Float", "width": 160},
        {"fieldname": "plate_comp", "label": _("Plated Qty Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "plate_comp_kgs", "label": _("Plated Qty kg"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "pack_comp", "label": _("Packed Qty Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pack_comp_kgs", "label": _("Packed Qty Kg"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pack_bal", "label": _("Pack Pending Pcs"), "fieldtype": "Float", "width": 160},
        {"fieldname": "pack_bal_kgs", "label": _("Pack Pending Kgs"), "fieldtype": "Float", "width": 160},
        
        {"fieldname": "fg_avail", "label": _("FG Stock Bal Pcs"), "fieldtype": "Float", "width": 150},
        {"fieldname": "dispatch_qty", "label": _("Disp Qty Pcs"), "fieldtype": "Float", "width": 150},
        {"fieldname": "dispatch_bal", "label": _("Disp Pending Pcs"), "fieldtype": "Float", "width": 150}
    ]

def get_data(filters):
    data = []
    
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

    conversion_weight_cache = {}
    
    def get_kgs_factor(item_code):
        if item_code not in conversion_weight_cache:
            item_doc = frappe.get_cached_doc("Item", item_code)
            stock_uom = item_doc.stock_uom and item_doc.stock_uom.strip().lower()
            
            if stock_uom in ['kg', 'kgs']:
                bom_no = item_doc.default_bom
                if bom_no:
                    bom_qty = frappe.db.get_value("BOM", bom_no, "quantity")
                    if bom_qty:
                        conversion_weight_cache[item_code] = bom_qty
                        return bom_qty
                        
            weight = getattr(item_doc, "weight_per_unit", 0.0)
            if weight:
                conversion_weight_cache[item_code] = weight
                return weight
                
            for uom in item_doc.uoms:
                if uom.uom.strip().lower() in ['kg', 'kgs']:
                    val = 1.0 / (uom.conversion_factor or 1.0)
                    conversion_weight_cache[item_code] = val
                    return val
                    
            conversion_weight_cache[item_code] = 1.0
            
        return conversion_weight_cache[item_code]

    # -------------------------------------------------------------
    # BUCKET 1: Sales Orders
    # -------------------------------------------------------------
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
    if filters.get("pp_status"):
        so_conditions.append("""
            EXISTS (
                SELECT 1 FROM `tabProduction Plan Item` ppi2 
                INNER JOIN `tabProduction Plan` pp2 ON ppi2.parent = pp2.name
                WHERE ppi2.sales_order = so.name AND ppi2.sales_order_item = soi.name 
                AND pp2.status = %(pp_status)s AND pp2.docstatus = 1
            )
        """)
        so_values["pp_status"] = filters.get("pp_status")
    if filters.get("production_plan"):
        so_conditions.append("""
            EXISTS (
                SELECT 1 FROM `tabProduction Plan Item` ppi3 
                WHERE ppi3.sales_order = so.name AND ppi3.sales_order_item = soi.name 
                AND ppi3.parent = %(production_plan)s
            )
        """)
        so_values["production_plan"] = filters.get("production_plan")
        
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

    # -------------------------------------------------------------
    # BUCKET 2: Independent Production Plans
    # -------------------------------------------------------------
    pp_conditions = ["pp.docstatus = 1", "(ppi.sales_order IS NULL OR ppi.sales_order = '')"]
    pp_values = {}
    if filters.get("company"):
        pp_conditions.append("pp.company = %(company)s")
        pp_values["company"] = filters.get("company")
    if filters.get("production_plan"):
        pp_conditions.append("pp.name = %(production_plan)s")
        pp_values["production_plan"] = filters.get("production_plan")
    if filters.get("item_code"):
        pp_conditions.append("ppi.item_code = %(item_code)s")
        pp_values["item_code"] = filters.get("item_code")
    if filters.get("from_date"):
        pp_conditions.append("pp.posting_date >= %(from_date)s")
        pp_values["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        pp_conditions.append("pp.posting_date <= %(to_date)s")
        pp_values["to_date"] = filters.get("to_date")
    if filters.get("pp_status"):
        pp_conditions.append("pp.status = %(pp_status)s")
        pp_values["pp_status"] = filters.get("pp_status")
        
    pp_query = f"""
        SELECT ppi.name as ppi_name, ppi.parent as pp_name, pp.posting_date as pp_date, pp.status as pp_status,
            ppi.item_code, ppi.planned_qty
        FROM `tabProduction Plan Item` ppi
        INNER JOIN `tabProduction Plan` pp ON ppi.parent = pp.name
        WHERE {" AND ".join(pp_conditions)}
        ORDER BY pp.posting_date DESC
    """
    # Only fetch if they didn't explicitly filter by Sales Order or Customer
    independent_pps = []
    if not filters.get("sales_order") and not filters.get("customer"):
        independent_pps = frappe.db.sql(pp_query, pp_values, as_dict=1)

    # -------------------------------------------------------------
    # BUCKET 3: Independent Work Orders
    # -------------------------------------------------------------
    wo_conditions = ["docstatus < 2", "(sales_order IS NULL OR sales_order = '')", "(production_plan IS NULL OR production_plan = '')"]
    wo_values = {}
    if filters.get("company"):
        wo_conditions.append("company = %(company)s")
        wo_values["company"] = filters.get("company")
    if filters.get("item_code"):
        wo_conditions.append("production_item = %(item_code)s")
        wo_values["item_code"] = filters.get("item_code")
    if filters.get("from_date"):
        wo_conditions.append("creation >= %(from_date)s")
        wo_values["from_date"] = filters.get("from_date")
    if filters.get("to_date"):
        wo_conditions.append("creation <= %(to_date)s")
        wo_values["to_date"] = filters.get("to_date")

    indep_wo_query = f"""
        SELECT name as wo_name, production_item as item_code, qty as wo_qty, creation
        FROM `tabWork Order`
        WHERE {" AND ".join(wo_conditions)}
        ORDER BY creation DESC
    """
    independent_wos = []
    if not filters.get("sales_order") and not filters.get("customer") and not filters.get("production_plan"):
        independent_wos = frappe.db.sql(indep_wo_query, wo_values, as_dict=1)

    # -------------------------------------------------------------
    # Build Master List
    # -------------------------------------------------------------
    master_list = []
    for row in so_items:
        master_list.append({"type": "SO", "data": row})
    for row in independent_pps:
        master_list.append({"type": "PP", "data": row})
    for row in independent_wos:
        master_list.append({"type": "WO", "data": row})

    # -------------------------------------------------------------
    # Master Processing Loop
    # -------------------------------------------------------------
    for master_item in master_list:
        root_type = master_item["type"]
        rdata = master_item["data"]
        
        root_item_code = rdata.item_code
        fg_bom = frappe.db.get_value("Item", root_item_code, "default_bom")
        
        dispatch_qty_pcs = 0.0
        root_pp_names = []
        root_pp_items = []
        valid_wos = []
        
        if root_type == "SO":
            # Dispatched Qty
            inv_items = frappe.db.sql("""
                SELECT sum(sii.qty) FROM `tabSales Invoice Item` sii
                INNER JOIN `tabSales Invoice` si ON sii.parent = si.name
                WHERE sii.sales_order = %s AND sii.so_detail = %s AND si.docstatus = 1
            """, (rdata.so_name, rdata.soi_name))
            dispatch_qty = inv_items[0][0] if (inv_items and inv_items[0][0]) else 0.0
            dispatch_qty_pcs = get_qty_pcs(root_item_code, root_item_code, dispatch_qty)
            
            # Linked PPs
            pp_where = "ppi.sales_order = %s AND ppi.sales_order_item = %s AND pp.docstatus = 1"
            pp_args = [rdata.so_name, rdata.soi_name]
            if filters.get("production_plan"):
                pp_where += " AND pp.name = %s"
                pp_args.append(filters.get("production_plan"))
                
            root_pp_items = frappe.db.sql(f"""
                SELECT pp.name as pp_name, pp.posting_date as pp_date, pp.status as pp_status, ppi.planned_qty, ppi.produced_qty as finished_qty
                FROM `tabProduction Plan Item` ppi
                INNER JOIN `tabProduction Plan` pp ON ppi.parent = pp.name
                WHERE {pp_where}
            """, tuple(pp_args), as_dict=1)
            root_pp_names = [p.pp_name for p in root_pp_items]
            
            # Linked WOs
            if root_pp_names:
                valid_wos = frappe.db.sql(f"SELECT name as wo_name, production_item, qty as wo_qty FROM `tabWork Order` WHERE production_plan IN ({', '.join(['%s'] * len(root_pp_names))}) AND docstatus < 2", tuple(root_pp_names), as_dict=1)
            direct_wos = frappe.db.sql("SELECT name as wo_name, production_item, qty as wo_qty FROM `tabWork Order` WHERE sales_order = %s AND docstatus < 2", (rdata.so_name,), as_dict=1)
            wo_map = {wo.wo_name: wo for wo in valid_wos}
            for dwo in direct_wos: wo_map[dwo.wo_name] = dwo
            valid_wos = list(wo_map.values())
            
            root_req_qty = get_qty_pcs(root_item_code, root_item_code, rdata.so_qty)
            
        elif root_type == "PP":
            root_pp_items = [rdata]
            root_pp_names = [rdata.pp_name]
            valid_wos = frappe.db.sql("SELECT name as wo_name, production_item, qty as wo_qty FROM `tabWork Order` WHERE production_plan = %s AND docstatus < 2", (rdata.pp_name,), as_dict=1)
            root_req_qty = get_qty_pcs(root_item_code, root_item_code, rdata.planned_qty)
            
        elif root_type == "WO":
            valid_wos = [rdata]
            root_req_qty = get_qty_pcs(root_item_code, root_item_code, rdata.wo_qty)
            
        # --- Smart Roll-up Engine ---
        def process_branch(branch_item, branch_bom, parent_id, indent, branch_req_qty, is_root=False):
            row_id = frappe.generate_hash(length=8)
            
            state = {
                "max_wo_qty": 0.0,
                "cut_comp": 0.0, "vibro_comp": 0.0, "plate_comp": 0.0, "pack_comp": 0.0,
                "req_ops": set(),
                "has_child": 0,
                "subcontract_kgs": 0.0
            }
            
            def traverse_wip(current_item, bom_no, req_qty):
                # Max WO Qty
                item_wos = [wo for wo in valid_wos if wo.production_item == current_item]
                for wo in item_wos:
                    wo_qty = get_qty_pcs(root_item_code, current_item, wo.wo_qty)
                    if wo_qty > state["max_wo_qty"]:
                        state["max_wo_qty"] = wo_qty
                        
                # Job Cards
                wo_names = [wo.wo_name for wo in item_wos]
                if wo_names:
                    job_cards = frappe.db.sql(f"SELECT operation, total_completed_qty as comp_qty FROM `tabJob Card` WHERE work_order IN ({', '.join(['%s']*len(wo_names))}) AND docstatus = 1", tuple(wo_names), as_dict=1)
                    for jc in job_cards:
                        op = jc.operation or ""
                        comp = get_qty_pcs(root_item_code, current_item, jc.comp_qty)
                        if "Cutting & Bending" in op: state["cut_comp"] += comp
                        elif "Vibro Cleaning" in op: state["vibro_comp"] += comp
                        elif "Plating" in op: state["plate_comp"] += comp
                        elif "Packaging" in op: state["pack_comp"] += comp
                        
                # Check Sub-contracting stock balance for this specific item (in raw Kgs)
                item_doc = frappe.get_cached_doc("Item", current_item)
                if item_doc.stock_uom and item_doc.stock_uom.strip().lower() in ['kg', 'kgs']:
                    bin_qty = frappe.db.sql("""
                        SELECT sum(b.actual_qty) 
                        FROM `tabBin` b
                        INNER JOIN `tabWarehouse` w ON b.warehouse = w.name
                        WHERE b.item_code = %s 
                        AND (w.warehouse_type = 'Subcontracting' OR w.parent_warehouse LIKE '%%Subcontracting%%' OR w.name LIKE '%%Subcontracting%%')
                    """, (current_item,))
                    if bin_qty and bin_qty[0][0]:
                        state["subcontract_kgs"] += bin_qty[0][0]
                        
                # Recurse
                if bom_no:
                    bom_ops = frappe.db.sql("SELECT operation FROM `tabBOM Operation` WHERE parent = %s", bom_no, as_dict=1)
                    state["req_ops"].update([op.operation for op in bom_ops if op.operation])
                    
                    bom_items = frappe.db.sql("SELECT item_code, bom_no, stock_qty FROM `tabBOM Item` WHERE parent = %s", bom_no, as_dict=1)
                    bom_base_qty = frappe.db.get_value("BOM", bom_no, "quantity") or 1.0
                    for child in bom_items:
                        if child.bom_no:
                            child_req_qty = req_qty * (child.stock_qty / bom_base_qty)
                            if child.item_code.startswith("FGD"):
                                state["has_child"] = 1
                                process_branch(child.item_code, child.bom_no, row_id, indent + 1, child_req_qty)
                            else:
                                traverse_wip(child.item_code, child.bom_no, child_req_qty)

            traverse_wip(branch_item, branch_bom, branch_req_qty)
            
            has_cut = any("Cutting & Bending" in o for o in state["req_ops"])
            has_vibro = any("Vibro Cleaning" in o for o in state["req_ops"])
            has_plate = any("Plating" in o for o in state["req_ops"])
            has_pack = any("Packaging" in o for o in state["req_ops"])
            
            total_wo_qty = state["max_wo_qty"]
            prev_comp = total_wo_qty
            
            bin_qty = frappe.db.sql("SELECT sum(actual_qty) FROM `tabBin` WHERE item_code = %s", (branch_item,))
            actual_stock_qty = bin_qty[0][0] if bin_qty and bin_qty[0][0] else 0.0
            
            final_order_qty = branch_req_qty if root_type == "SO" else 0.0
            
            row = {
                "id": row_id,
                "parent_id": parent_id,
                "indent": indent,
                
                "item_code": branch_item,
                "item_name": frappe.db.get_value("Item", branch_item, "item_name") or branch_item,
                "order_qty": final_order_qty,
                "stock_qty": actual_stock_qty,
                "wo_qty": total_wo_qty,
                "subcontract_kgs": state["subcontract_kgs"],
                "has_child": state["has_child"]
            }
            
            if is_root:
                if root_type == "SO":
                    row.update({
                        "sales_order": rdata.so_name,
                        "customer_name": rdata.customer_name,
                        "so_date": rdata.so_date,
                        "production_plan": ", ".join(list(set(root_pp_names))),
                        "pp_date": ", ".join(list(set([str(p.pp_date) for p in root_pp_items]))),
                        "pp_status": ", ".join(list(set([str(p.pp_status) for p in root_pp_items if p.pp_status]))),
                        "pp_qty": sum([get_qty_pcs(root_item_code, root_item_code, p.planned_qty) for p in root_pp_items]),
                        "pp_bal": sum([get_qty_pcs(root_item_code, root_item_code, p.planned_qty - p.get("finished_qty", 0.0)) for p in root_pp_items]),
                        "dispatch_qty": dispatch_qty_pcs,
                        "dispatch_bal": max(0, branch_req_qty - dispatch_qty_pcs)
                    })
                elif root_type == "PP":
                    row.update({
                        "production_plan": rdata.pp_name,
                        "pp_date": rdata.pp_date,
                        "pp_status": rdata.pp_status,
                        "pp_qty": branch_req_qty,
                        "pp_bal": branch_req_qty - get_qty_pcs(root_item_code, root_item_code, rdata.get("finished_qty", 0.0))
                    })
            
            if has_cut:
                row["cut_comp"] = state["cut_comp"]
                row["cut_bal"] = max(0, total_wo_qty - state["cut_comp"])
                prev_comp = state["cut_comp"]
            else:
                row["cut_comp"] = 0; row["cut_bal"] = 0
                
            if has_vibro:
                row["vibro_avail"] = max(0, prev_comp - state["vibro_comp"])
                row["vibro_comp"] = state["vibro_comp"]
                row["vibro_bal"] = max(0, total_wo_qty - state["vibro_comp"])
                prev_comp = state["vibro_comp"]
            else:
                row["vibro_avail"] = 0; row["vibro_comp"] = 0; row["vibro_bal"] = 0
                
            if has_plate:
                row["plate_avail"] = max(0, prev_comp - state["plate_comp"])
                row["plate_comp"] = state["plate_comp"]
                row["plate_bal"] = max(0, total_wo_qty - state["plate_comp"])
                prev_comp = state["plate_comp"]
            else:
                row["plate_avail"] = 0; row["plate_comp"] = 0; row["plate_bal"] = 0
                
            if has_pack:
                row["pack_comp"] = state["pack_comp"]
                row["pack_bal"] = max(0, total_wo_qty - state["pack_comp"])
                prev_comp = state["pack_comp"]
            else:
                row["pack_comp"] = 0; row["pack_bal"] = 0
                
            if is_root and root_type == "SO":
                fg_avail = state["pack_comp"] - dispatch_qty_pcs
                row["fg_avail"] = fg_avail if fg_avail > 0 else 0
            elif is_root:
                row["fg_avail"] = state["pack_comp"]
                
            kgs_factor = get_kgs_factor(root_item_code)
            
            row["wo_qty_kgs"] = row.get("wo_qty", 0.0) * kgs_factor
            
            # Since subcontract_kgs is raw component kgs, subcontract_pcs is the equivalent FG Pcs
            # which is better calculated using get_qty_pcs. But we already have the raw Kgs.
            # To get FG Pcs from raw Component Kgs, we should use get_qty_pcs directly.
            row["subcontract_pcs"] = get_qty_pcs(root_item_code, branch_item, row.get("subcontract_kgs", 0.0))
            
            row["cut_comp_kgs"] = row.get("cut_comp", 0.0) * kgs_factor
            row["cut_bal_kgs"] = row.get("cut_bal", 0.0) * kgs_factor
            
            row["vibro_avail_kgs"] = row.get("vibro_avail", 0.0) * kgs_factor
            row["vibro_comp_kgs"] = row.get("vibro_comp", 0.0) * kgs_factor
            
            row["plate_avail_kgs"] = row.get("plate_avail", 0.0) * kgs_factor
            row["plate_comp_kgs"] = row.get("plate_comp", 0.0) * kgs_factor
            
            row["pack_comp_kgs"] = row.get("pack_comp", 0.0) * kgs_factor
            row["pack_bal_kgs"] = row.get("pack_bal", 0.0) * kgs_factor
                
            data.append(row)
                        
        process_branch(root_item_code, fg_bom, "", 0, root_req_qty, is_root=True)

    if filters.get("has_subcontract_stock"):
        valid_ids = set()
        for row in data:
            if row.get("subcontract_kgs", 0) > 0:
                current_id = row.get("id")
                while current_id:
                    valid_ids.add(current_id)
                    parent_row = next((r for r in data if r.get("id") == current_id), None)
                    if parent_row:
                        current_id = parent_row.get("parent_id")
                    else:
                        break
        data = [row for row in data if row.get("id") in valid_ids]

    if data:
        total_row = {
            "id": frappe.generate_hash(length=8),
            "parent_id": "",
            "indent": 0,
            "item_name": "<b>Totals</b>",
            "order_qty": 0.0,
            "stock_qty": 0.0,
            "pp_qty": 0.0,
            "pp_bal": 0.0,
            "wo_qty": 0.0,
            "wo_qty_kgs": 0.0,
            "subcontract_kgs": 0.0,
            "subcontract_pcs": 0.0,
            "cut_comp": 0.0, "cut_comp_kgs": 0.0, "cut_bal": 0.0, "cut_bal_kgs": 0.0,
            "vibro_avail": 0.0, "vibro_avail_kgs": 0.0, "vibro_comp": 0.0, "vibro_comp_kgs": 0.0, 
            "plate_avail": 0.0, "plate_avail_kgs": 0.0, "plate_comp": 0.0, "plate_comp_kgs": 0.0,
            "pack_comp": 0.0, "pack_comp_kgs": 0.0, "pack_bal": 0.0, "pack_bal_kgs": 0.0,
            "fg_avail": 0.0, "dispatch_qty": 0.0, "dispatch_bal": 0.0
        }
        for d in data:
            if not d.get("parent_id"):  # Only sum root nodes!
                for key in total_row:
                    if key not in ["id", "parent_id", "indent", "item_name"]:
                        total_row[key] += (d.get(key) or 0.0)
        data.append(total_row)

    return data
