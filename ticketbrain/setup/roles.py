from ticketbrain.setup.utils import bulk_create_roles


def create_custom_roles():
    """Create all custom roles for TicketBrain app"""

    # Note: Employee Self Service role already exists in ERPNext
    # We're just ensuring it exists, but typically you don't need to create it
    # Only include truly custom roles here

    roles = [
        # Add your custom roles here if needed in future
        # {
            #     "role_name": "Your Custom Role",
            #     "desk_access": 1,
            # },
        ]

    if roles:
        bulk_create_roles(roles, context_name= "TicketBrain Custom Roles")
    else:
        print("→ No custom roles to create (using existing ERPNext roles)")