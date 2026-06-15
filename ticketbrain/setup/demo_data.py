"""
TicketBrain Demo Data Setup

Creates realistic demo data for testing the full ticket workflow:
  - 3 HD Teams (IT Support, Network & Infrastructure, Security)
  - 3 HD Agents with user accounts
  - 4 Customers with Contact + email + portal System User
  - 4 Employees using existing Frappe departments and designations

Run via bench console or as a one-off script:
  cd /home/yash/TicketBrain
  bench --site ticketbrain.local execute ticketbrain.setup.demo_data.create_all
"""

import frappe

COMPANY = "TicketBrain"

# ── Teams ──────────────────────────────────────────────────────────────────────

TEAMS = [
    "IT Support",
    "Network & Infrastructure",
    "Security",
]

# ── Agents ─────────────────────────────────────────────────────────────────────

AGENTS = [
    {
        "email":      "rahul.sharma@ticketbrain.local",
        "first_name": "Rahul",
        "last_name":  "Sharma",
        "team":       "IT Support",
        "department": "Management - T",
        "designation": "Manager",
    },
    {
        "email":      "priya.patel@ticketbrain.local",
        "first_name": "Priya",
        "last_name":  "Patel",
        "team":       "Network & Infrastructure",
        "department": "Management - T",
        "designation": "Analyst",
    },
    {
        "email":      "amit.kumar@ticketbrain.local",
        "first_name": "Amit",
        "last_name":  "Kumar",
        "team":       "Security",
        "department": "Management - T",
        "designation": "Engineer",
    },
]

# ── Customers + Contacts + Portal Users ───────────────────────────────────────

CUSTOMERS = [
    {
        "customer_name": "Acme Corporation",
        "customer_type": "Company",
        "contact": {
            "first_name": "John",
            "last_name":  "Smith",
            "email":      "john.smith@acme.com",
        },
    },
    {
        "customer_name": "TechVentures India",
        "customer_type": "Company",
        "contact": {
            "first_name": "Sarah",
            "last_name":  "Johnson",
            "email":      "sarah.j@techventures.com",
        },
    },
    {
        "customer_name": "GlobalSoft Solutions",
        "customer_type": "Company",
        "contact": {
            "first_name": "Mike",
            "last_name":  "Chen",
            "email":      "mike.chen@globalsoft.com",
        },
    },
    {
        "customer_name": "DigitalEdge Pvt Ltd",
        "customer_type": "Company",
        "contact": {
            "first_name": "Anita",
            "last_name":  "Rao",
            "email":      "anita.rao@digitaledge.com",
        },
    },
]

# ── Employees ──────────────────────────────────────────────────────────────────

EMPLOYEES = [
    {
        "first_name":      "Rahul",
        "last_name":       "Sharma",
        "gender":          "Male",
        "date_of_birth":   "1990-04-12",
        "date_of_joining": "2022-01-15",
        "department":      "Management - T",
        "designation":     "Manager",
        "company":         COMPANY,
    },
    {
        "first_name":      "Priya",
        "last_name":       "Patel",
        "gender":          "Female",
        "date_of_birth":   "1993-08-25",
        "date_of_joining": "2022-06-01",
        "department":      "Management - T",
        "designation":     "Analyst",
        "company":         COMPANY,
    },
    {
        "first_name":      "Amit",
        "last_name":       "Kumar",
        "gender":          "Male",
        "date_of_birth":   "1991-11-03",
        "date_of_joining": "2023-03-10",
        "department":      "Management - T",
        "designation":     "Engineer",
        "company":         COMPANY,
    },
    {
        "first_name":      "Sneha",
        "last_name":       "Desai",
        "gender":          "Female",
        "date_of_birth":   "1988-02-17",
        "date_of_joining": "2021-09-01",
        "department":      "Accounts - T",
        "designation":     "Finance Manager",
        "company":         COMPANY,
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _log(msg):
    print(f"  ✓ {msg}")


def _err(msg):
    print(f"  ✗ {msg}")


# ── Team creation ──────────────────────────────────────────────────────────────

def create_teams():
    print("\n[Teams]")
    for team_name in TEAMS:
        if frappe.db.exists("HD Team", {"team_name": team_name}):
            _log(f"Team already exists: {team_name}")
            continue
        try:
            frappe.get_doc({
                "doctype":   "HD Team",
                "team_name": team_name,
            }).insert(ignore_permissions=True)
            _log(f"Created team: {team_name}")
        except Exception as e:
            _err(f"Failed to create team {team_name}: {e}")
    frappe.db.commit()


# ── Agent creation ─────────────────────────────────────────────────────────────

def create_agents():
    print("\n[Agents]")
    for a in AGENTS:
        email = a["email"]

        # Create or update User
        if not frappe.db.exists("User", email):
            try:
                user = frappe.get_doc({
                    "doctype":            "User",
                    "email":              email,
                    "first_name":         a["first_name"],
                    "last_name":          a["last_name"],
                    "full_name":          f"{a['first_name']} {a['last_name']}",
                    "user_type":          "System User",
                    "enabled":            1,
                    "send_welcome_email": 0,
                    "new_password":       "TicketBrain@123",
                    "roles": [{"role": "Helpdesk Contact"}],
                })
                user.insert(ignore_permissions=True)
                _log(f"Created user: {email}")
            except Exception as e:
                _err(f"Failed to create user {email}: {e}")
                continue
        else:
            _log(f"User exists: {email}")

        # Create HD Agent record
        if not frappe.db.exists("HD Agent", {"user": email}):
            try:
                agent = frappe.get_doc({
                    "doctype":    "HD Agent",
                    "user":       email,
                    "agent_name": f"{a['first_name']} {a['last_name']}",
                    "is_active":  1,
                })
                agent.insert(ignore_permissions=True)
                _log(f"Created HD Agent: {email}")
            except Exception as e:
                _err(f"Failed to create HD Agent {email}: {e}")
                continue
        else:
            _log(f"HD Agent exists: {email}")

        # Add agent to team via direct SQL (bypasses ORM child-table validation)
        team_name = a["team"]
        team_doc  = frappe.db.get_value("HD Team", {"team_name": team_name}, "name")
        if team_doc:
            already_member = frappe.db.sql(
                "SELECT name FROM `tabHD Team Member` WHERE parent=%s AND user=%s LIMIT 1",
                (team_doc, email),
            )
            if not already_member:
                try:
                    import random, time
                    unique_id = int(time.time() * 1000) + random.randint(0, 9999)
                    frappe.db.sql(
                        """INSERT INTO `tabHD Team Member`
                           (name,creation,modified,modified_by,owner,docstatus,idx,user,parent,parentfield,parenttype)
                           VALUES (%s,NOW(),NOW(),'Administrator','Administrator',0,1,%s,%s,'members','HD Team')""",
                        (unique_id, email, team_doc),
                    )
                    _log(f"Added {email} to team {team_name}")
                except Exception as e:
                    _err(f"Failed to add {email} to team {team_name}: {e}")
            else:
                _log(f"{email} already in team {team_name}")

    frappe.db.commit()


# ── Customer + Contact + Portal User creation ──────────────────────────────────

def create_customers():
    print("\n[Customers]")
    for c in CUSTOMERS:
        customer_name = c["customer_name"]
        contact       = c["contact"]
        email         = contact["email"]

        # Create Customer
        if not frappe.db.exists("Customer", customer_name):
            try:
                frappe.get_doc({
                    "doctype":       "Customer",
                    "customer_name": customer_name,
                    "customer_type": c["customer_type"],
                    "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "All Customer Groups",
                    "territory":     frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories",
                }).insert(ignore_permissions=True)
                _log(f"Created customer: {customer_name}")
            except Exception as e:
                _err(f"Failed to create customer {customer_name}: {e}")
                continue
        else:
            _log(f"Customer exists: {customer_name}")

        # Create Contact linked to Customer
        contact_exists = frappe.db.get_value(
            "Contact Email",
            {"email_id": email, "parenttype": "Contact"},
            "parent",
        )
        if not contact_exists:
            try:
                contact_doc = frappe.get_doc({
                    "doctype":    "Contact",
                    "first_name": contact["first_name"],
                    "last_name":  contact["last_name"],
                    "email_ids": [{"email_id": email, "is_primary": 1}],
                    "links": [{"link_doctype": "Customer", "link_name": customer_name}],
                })
                contact_doc.insert(ignore_permissions=True)
                _log(f"Created contact: {contact['first_name']} {contact['last_name']} ({email})")
            except Exception as e:
                _err(f"Failed to create contact {email}: {e}")
        else:
            _log(f"Contact exists for: {email}")

        # Create portal System User for the customer contact
        if not frappe.db.exists("User", email):
            try:
                user = frappe.get_doc({
                    "doctype":            "User",
                    "email":              email,
                    "first_name":         contact["first_name"],
                    "last_name":          contact["last_name"],
                    "full_name":          f"{contact['first_name']} {contact['last_name']}",
                    "user_type":          "System User",
                    "enabled":            1,
                    "send_welcome_email": 0,
                    "new_password":       "Customer@123",
                    "roles": [{"role": "Customer"}],
                })
                user.insert(ignore_permissions=True)
                _log(f"Created portal user: {email} (password: Customer@123)")
            except Exception as e:
                _err(f"Failed to create portal user {email}: {e}")
        else:
            _log(f"Portal user exists: {email}")

    frappe.db.commit()


# ── Employee creation ──────────────────────────────────────────────────────────

def create_employees():
    print("\n[Employees]")
    for e in EMPLOYEES:
        full_name = f"{e['first_name']} {e['last_name']}"
        exists = frappe.db.sql(
            "SELECT name FROM `tabEmployee` WHERE employee_name=%s LIMIT 1", full_name
        )
        if exists:
            _log(f"Employee exists: {full_name}")
            continue
        try:
            emp = frappe.new_doc("Employee")
            emp.first_name      = e["first_name"]
            emp.last_name       = e["last_name"]
            emp.employee_name   = full_name
            emp.gender          = e["gender"]
            emp.date_of_birth   = e["date_of_birth"]
            emp.date_of_joining = e["date_of_joining"]
            emp.department      = e["department"]
            emp.designation     = e["designation"]
            emp.company         = e["company"]
            emp.status          = "Active"
            emp.flags.ignore_mandatory = True
            emp.insert(ignore_permissions=True)
            _log(f"Created employee: {full_name} ({e['designation']}, {e['department']})")
        except Exception as ex:
            _err(f"Failed to create employee {full_name}: {ex}")
    frappe.db.commit()


# ── Main entry point ───────────────────────────────────────────────────────────

def create_all():
    """Run all demo data creation steps."""
    print("\n=== TicketBrain Demo Data Setup ===")
    create_teams()
    create_agents()
    create_customers()
    create_employees()
    print("\n=== Done! ===")
    print("\nCustomer portal users (login to Helpdesk portal to raise tickets):")
    for c in CUSTOMERS:
        print(f"  {c['contact']['email']}  |  password: Customer@123")
    print("\nAgent accounts (login to Frappe desk to review tickets):")
    for a in AGENTS:
        print(f"  {a['email']}  |  password: TicketBrain@123")
