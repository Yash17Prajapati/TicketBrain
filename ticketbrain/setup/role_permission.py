from ticketbrain.setup.utils import smart_bulk_add_permissions, clear_permissions_cache

def setup_issue_doctype_customer_permissions():
    """Setup Issue doctype permissions for Customer role"""
    permissions = [
    {
        "doctype": "Issue",
        "role": "Customer",
        "permlevel": 0,
        "if_owner": 0,
        "select": 1,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "submit": 0,
        "cancel": 0,
        "amend": 0,
        "print": 0,
        "email": 0,
        "report": 0,
        "import": 0,
        "export": 1,
        "share": 0
    }
    ]
    smart_bulk_add_permissions(permissions, context_name="Issue Doctype Customer Permissions")
    
def setup_all_custom_role_permissions():
    """Setup all custom role permissions"""
    setup_issue_doctype_customer_permissions()