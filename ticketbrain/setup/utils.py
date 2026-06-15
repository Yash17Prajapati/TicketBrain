import frappe
import json
import random
import string
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def update_workspace():
    """
    Sync the TicketBrain workspace with all newly added doctypes.
    Safe to run multiple times — skips items that already exist.
    Run via: bench --site ticketbrain.local execute ticketbrain.setup.utils.update_workspace
    """
    if not frappe.db.exists("Workspace", "TicketBrain"):
        print("TicketBrain workspace not found — skipping.")
        return

    ws = frappe.get_doc("Workspace", "TicketBrain")

    # ── Shortcuts (top tiles) ────────────────────────────────────────────────
    new_shortcuts = [
        {"label": "Knowledge Drafts", "link_to": "TB Knowledge Draft", "type": "DocType", "color": "Grey", "icon": "edit"},
    ]
    existing_sc = {s.link_to for s in ws.shortcuts}
    sc_added = []
    for sc in new_shortcuts:
        if sc["link_to"] not in existing_sc:
            ws.append("shortcuts", sc)
            sc_added.append(sc["label"])

    # ── Card links ───────────────────────────────────────────────────────────
    new_links = [
        {"label": "Knowledge Drafts", "link_to": "TB Knowledge Draft", "link_type": "DocType", "dependencies": ""},
    ]
    existing_lk = {(l.label, l.link_to) for l in ws.links}
    lk_added = []
    for lk in new_links:
        if (lk["label"], lk["link_to"]) not in existing_lk:
            ws.append("links", lk)
            lk_added.append(lk["label"])

    # ── Canvas content JSON (tile positions) ─────────────────────────────────
    content = json.loads(ws.content or "[]")
    existing_ids = {c["id"] for c in content}

    new_tiles = [
        {"id": "tb_s5", "after": "tb_s4", "block": {"id": "tb_s5", "type": "shortcut", "data": {"shortcut_name": "Knowledge Drafts", "col": 3}}},
    ]
    tiles_added = []
    for tile in new_tiles:
        if tile["id"] not in existing_ids:
            inserted = False
            for i, block in enumerate(content):
                if block.get("id") == tile["after"]:
                    content.insert(i + 1, tile["block"])
                    inserted = True
                    break
            if not inserted:
                content.append(tile["block"])
            tiles_added.append(tile["id"])

    ws.content = json.dumps(content)
    ws.save(ignore_permissions=True)
    frappe.db.commit()

    print(f"Workspace updated:")
    print(f"  Shortcuts added : {sc_added or 'none (already exist)'}")
    print(f"  Card links added: {lk_added or 'none (already exist)'}")
    print(f"  Canvas tiles    : {tiles_added or 'none (already exist)'}")


def create_role_if_not_exists(role_data):
    role_name = role_data.get("role_name")

    if frappe.db.exists("Role", role_name):
        print(f"○ UNCHANGED: Role '{role_name}' (already exists)")
        frappe.logger().info(f"Role already exists: {role_name}")
        return "exists"

    try:
        role = frappe.get_doc({
            "doctype": "Role",
            "role_name": role_name,
            "desk_access": role_data.get("desk_access", 1),
            "is_custom": 1,
            "disabled": role_data.get("disabled", 0),
            "two_factor_auth": role_data.get("two_factor_auth", 0)
        })
        role.insert(ignore_permissions=True)
        frappe.db.commit()

        print(f"+ CREATED: Role '{role_name}' (desk_access: {role.desk_access})")
        frappe.logger().info(f"Created role: {role_name}")
        return "created"

    except Exception as e:
        print(f"✗ ERROR: Failed to create role '{role_name}' - {str(e)}")
        frappe.logger().error(f"Error creating role {role_name}: {str(e)}")
        return "error"


def bulk_create_roles(role_configs, context_name="Custom Roles"):
    results = {"created": 0, "exists": 0, "error": 0}

    print(f"\n{'='*60}")
    print(f"Running: {context_name}")
    print(f"{'='*60}")

    for idx, config in enumerate(role_configs, 1):
        role_name = config.get("role_name", "Unknown")
        print(f"\n[{idx}/{len(role_configs)}] Processing Role: {role_name}")
        result = create_role_if_not_exists(config)
        results[result] += 1

    print(f"\n{'='*60}")
    print(f"Summary for '{context_name}':")
    print(f"  + Created:   {results['created']}")
    print(f"  ○ Exists:    {results['exists']}")
    print(f"  ✗ Errors:    {results['error']}")
    print(f"  → Total:     {len(role_configs)}")
    print(f"{'='*60}\n")

    frappe.logger().info(f"{context_name} - Results: {results}")
    return results


def add_permission_if_not_exists(doctype, role, permlevel=0, **permissions):
    # All possible permission fields with default value 0
    all_perm_fields = {
        "read": 0, "write": 0, "create": 0, "delete": 0,
        "submit": 0, "cancel": 0, "amend": 0,
        "report": 0, "export": 0, "import": 0,
        "share": 0, "print": 0, "email": 0,
        "if_owner": 0, "select": 0
    }

    # Merge provided permissions with defaults
    final_permissions = {**all_perm_fields, **permissions}

    # Check if permission already exists
    existing = frappe.db.get_value(
        "Custom DocPerm",
        {
            "parent": doctype,
            "role": role,
            "permlevel": permlevel,
            "if_owner": final_permissions.get("if_owner", 0)
        },
        ["name"] + list(all_perm_fields.keys()),
        as_dict=True
    )

    if existing:
        # Check if any permission needs update
        needs_update = False
        for perm_key, perm_value in final_permissions.items():
            if existing.get(perm_key) != perm_value:
                needs_update = True
                break

        if needs_update:
            perm_doc = frappe.get_doc("Custom DocPerm", existing.name)
            for perm_key, perm_value in final_permissions.items():
                setattr(perm_doc, perm_key, perm_value)
            perm_doc.save(ignore_permissions=True)
            frappe.db.commit()

            perm_summary = ", ".join([k for k, v in final_permissions.items() if v])
            if_owner_text = " [If Owner]" if final_permissions.get("if_owner") else ""
            print(f"✓ UPDATED: {role} on {doctype} [Level {permlevel}]{if_owner_text} - {perm_summary}")
            frappe.logger().info(f"Updated permission: {role} on {doctype} permlevel {permlevel}")
            return "updated"
        else:
            perm_summary = ", ".join([k for k, v in final_permissions.items() if v])
            if_owner_text = " [If Owner]" if final_permissions.get("if_owner") else ""
            print(f"○ UNCHANGED: {role} on {doctype} [Level {permlevel}]{if_owner_text} - {perm_summary}")
            return "unchanged"
    else:
        # Create new permission
        perm_doc = frappe.get_doc({
    "doctype": "Custom DocPerm",
    "parent": doctype,
    "parenttype": "DocType",
    "parentfield": "permissions",
    "role": role,
    "permlevel": permlevel,
    **final_permissions
})                    
        perm_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        perm_summary = ", ".join([k for k, v in final_permissions.items() if v])
        if_owner_text = " [If Owner]" if final_permissions.get("if_owner") else ""
        print(f"+ CREATED: {role} on {doctype} [Level {permlevel}]{if_owner_text} - {perm_summary}")
        frappe.logger().info(f"Created permission: {role} on {doctype} permlevel {permlevel}")
        return "created"


def bulk_add_permissions(permission_configs, context_name="DocType Permissions"):
    results = {"created": 0, "updated": 0, "unchanged": 0}

    print(f"\n{'='*60}")
    print(f"Running: {context_name}")
    print(f"{'='*60}")

    for idx, config in enumerate(permission_configs, 1):
        config_copy = config.copy()
        doctype = config_copy.pop("doctype")
        role = config_copy.pop("role")
        permlevel = config_copy.pop("permlevel", 0)

        print(f"\n[{idx}/{len(permission_configs)}] Processing: {role} → {doctype} (Level {permlevel})")

        result = add_permission_if_not_exists(doctype, role, permlevel, **config_copy)
        results[result] += 1

    print(f"\n{'='*60}")
    print(f"Summary for '{context_name}':")
    print(f"  + Created:   {results['created']}")
    print(f"  ✓ Updated:   {results['updated']}")
    print(f"  ○ Unchanged: {results['unchanged']}")
    print(f"  → Total:     {len(permission_configs)}")
    print(f"{'='*60}\n")

    frappe.logger().info(f"{context_name} - Results: {results}")
    return results


def get_default_permissions_for_doctype(doctype):
    """Get all default DocPerm entries for a doctype"""
    if not frappe.db.exists("DocType", doctype):
        return []

    default_perms = frappe.get_all(
        "DocPerm",
        filters={"parent": doctype},
        fields=[
            "role", "permlevel", "read", "write", "create", "delete",
            "submit", "cancel", "amend", "report", "export", "import",
            "print", "email", "share", "if_owner", "select"
        ]
    )

    return default_perms


def get_roles_being_edited(permission_configs):
    """Extract unique (role, doctype) combinations being edited"""
    edited_roles_per_doctype = {}
    for config in permission_configs:
        doctype = config.get("doctype")
        role = config.get("role")
        if doctype not in edited_roles_per_doctype:
            edited_roles_per_doctype[doctype] = set()
        edited_roles_per_doctype[doctype].add(role)
    return edited_roles_per_doctype


def remove_existing_custom_docperms_for_role(doctype, role):
    """Remove all existing Custom DocPerm entries for a specific doctype and role"""
    existing_perms = frappe.get_all(
        "Custom DocPerm",
        filters={"parent": doctype, "role": role},
        fields=["name", "permlevel"]
    )

    if existing_perms:
        for perm in existing_perms:
            frappe.delete_doc("Custom DocPerm", perm.name, ignore_permissions=True, force=True)
            print(f"  ✗ DELETED: Old Custom DocPerm for {role} on {doctype} [Level {perm.permlevel}]")
        frappe.db.commit()
        return len(existing_perms)
    return 0


def smart_bulk_add_permissions(permission_configs, context_name="DocType Permissions"):
    """
    Smart permission setup that:
        1. Preserves existing permissions for roles NOT being edited
        2. Deletes old permissions for roles being edited
        3. Creates new permissions as specified
        """
        # Get unique doctypes and roles being edited per doctype
    doctypes_to_update = set(config.get("doctype") for config in permission_configs)
    edited_roles_per_doctype = get_roles_being_edited(permission_configs)

    print(f"\n{'='*60}")
    print(f"Smart Permission Setup: {context_name}")
    print(f"{'='*60}")
    for doctype in doctypes_to_update:
        roles = ', '.join(edited_roles_per_doctype.get(doctype, []))
        print(f"  {doctype}: Editing roles → {roles}")
    print(f"{'='*60}\n")

    final_permissions = []
    deletion_summary = {"deleted_roles": 0, "deleted_perms": 0}

            # Step 1: Handle existing permissions and deletions
    for doctype in doctypes_to_update:
        edited_roles = edited_roles_per_doctype.get(doctype, set())

                # Check if any Custom DocPerm exists for this doctype
        existing_custom_perms = frappe.get_all(
                    "Custom DocPerm",
                    filters={"parent": doctype},
                    fields=[
                        "role", "permlevel", "read", "write", "create", "delete",
                        "submit", "cancel", "amend", "report", "export", "import",
                        "print", "email", "share", "if_owner", "select"
                    ]
                )

        if existing_custom_perms:
                    # Custom DocPerm exists
            print(f"📋 Found existing Custom DocPerm for {doctype}")

                    # Delete Custom DocPerm for roles being edited
            for role in edited_roles:
                deleted_count = remove_existing_custom_docperms_for_role(doctype, role)
                if deleted_count > 0:
                    deletion_summary["deleted_roles"] += 1
                    deletion_summary["deleted_perms"] += deleted_count

                            # Preserve Custom DocPerm for roles NOT being edited
            for perm in existing_custom_perms:
                if perm.role not in edited_roles:
                    perm_config = {"doctype": doctype}
                    perm_config.update(perm)
                    final_permissions.append(perm_config)
                    print(f"  ○ PRESERVING Custom: {perm.role} [Level {perm.permlevel}]")

        else:
                                    # No Custom DocPerm exists - copy from default DocPerm
            print(f"📄 No Custom DocPerm found for {doctype}, copying from defaults...")
            default_perms = get_default_permissions_for_doctype(doctype)

            for perm in default_perms:
                if perm.role not in edited_roles:
                    perm_config = {"doctype": doctype}
                    perm_config.update(perm)
                    final_permissions.append(perm_config)
                    print(f"  ○ PRESERVING Default: {perm.role} [Level {perm.permlevel}]")

                                            # Step 2: Add your new/edited permissions
    final_permissions.extend(permission_configs)

    print(f"\n{'='*60}")
    print(f"Deletion Summary:")
    print(f"  Roles with deleted permissions: {deletion_summary['deleted_roles']}")
    print(f"  Total permissions deleted: {deletion_summary['deleted_perms']}")
    print(f"\nTotal permissions to process: {len(final_permissions)}")
    print(f"{'='*60}\n")

                                            # Step 3: Process all permissions (create/update)
    return bulk_add_permissions(final_permissions, context_name=context_name)


def clear_permissions_cache():
    """Clear permissions cache"""
    frappe.clear_cache(doctype="DocType")
    frappe.cache().delete_value("roles")
    print("✓ Cleared permission cache\n")
    frappe.logger().info("Cleared permission cache")


