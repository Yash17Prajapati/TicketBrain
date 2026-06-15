"""
Synthetic training data generator — no API required.
Generates 1800 IT support tickets covering all model training use cases.
Run: python generate_data.py
"""

import csv
import random
from pathlib import Path

random.seed(42)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = DATA_DIR / "training_data.csv"

CSV_FIELDS = [
	"ticket_id",
	"subject",
	"description",
	"category",
	"priority",
	"department",
	"resolution_type",
	"resolution",
	"resolved_in_steps",
	"confidence_score",
	"feedback",
	"was_escalated",
	"is_repeated_issue",
	"is_ambiguous",
	"source",
]

# Category prefix for ticket ID
CATEGORY_PREFIX = {
	"Hardware & Infrastructure": "HW",
	"Software & Applications": "APP",
	"Security & Threats": "SEC",
	"Data & Reports": "DAT",
	"Network & Connectivity": "NET",
	"Account & Access": "ACC",
}

DEPARTMENTS = ["HR", "Finance", "Sales", "IT", "Operations", "Marketing"]

STYLE_WRAPPERS = [
	lambda d: d,
	lambda d: f"Hi team, {d[0].lower()}{d[1:]}",
	lambda d: f"Urgent - {d}",
	lambda d: f"Hi, {d}",
	lambda d: f"Hello, {d} Please help.",
	lambda d: f"This is really frustrating. {d}",
	lambda d: f"Not sure if this is the right place but {d[0].lower()}{d[1:]}",
	lambda d: f"Following up on this issue — {d[0].lower()}{d[1:]}",
	lambda d: f"I have been dealing with this for days. {d}",
	lambda d: f"Quick question — {d[0].lower()}{d[1:]}",
]

# --------------------------------------------------------------------------
# TICKET TEMPLATES
# (subject, description, resolution_type, resolution,
#  resolved_in_steps, base_priority, is_repeated, is_ambiguous, source)
# --------------------------------------------------------------------------

TEMPLATES = {

	"Hardware & Infrastructure": [
		# ---------- GENERAL ----------
		("Laptop won't turn on",
		 "My laptop stopped turning on this morning. I pressed the power button multiple times but nothing happens. The charging LED is also not lighting up.",
		 "step_by_step",
		 "Step 1: Hold the power button for 30 seconds to drain residual charge. Step 2: Remove battery if removable and reconnect. Step 3: Connect directly to power adapter and try again. Step 4: If still unresponsive escalate to hardware team for inspection.",
		 4, "High", True, False, "general"),

		("Computer running extremely slow",
		 "My desktop has been very slow for the past two days. Opening any application takes several minutes and even typing is laggy.",
		 "step_by_step",
		 "Step 1: Open Task Manager and check for high CPU or memory usage. Step 2: Restart the computer. Step 3: Run disk cleanup to free up space. Step 4: Check if antivirus is running a full scan and pause it temporarily. Step 5: If issue persists IT will assess RAM and storage health.",
		 5, "Medium", True, False, "general"),

		("Monitor not displaying anything",
		 "I came back from lunch and my monitor is completely black. The computer seems to be on but nothing shows on screen.",
		 "step_by_step",
		 "Step 1: Check that the monitor power cable is securely plugged in. Step 2: Check the display cable connection on both ends. Step 3: Press the monitor input select button to cycle through inputs. Step 4: Connect a different monitor to isolate whether issue is the monitor or the GPU.",
		 4, "Medium", True, False, "general"),

		("Printer not printing",
		 "The office printer is not printing. I sent a document 20 minutes ago and it is stuck in the queue. Other colleagues are also affected.",
		 "step_by_step",
		 "Step 1: Open print queue and cancel all pending jobs. Step 2: Restart the printer. Step 3: Restart the print spooler service on your computer. Step 4: Reinstall the printer driver if the issue continues.",
		 4, "Medium", True, False, "general"),

		("Keyboard keys not working",
		 "Several keys on my keyboard have stopped responding — the number keys and some letters. My keyboard is wired USB.",
		 "step_by_step",
		 "Step 1: Unplug the keyboard and plug into a different USB port. Step 2: Test the keyboard on another computer. Step 3: If confirmed faulty submit a hardware replacement request.",
		 3, "Low", False, False, "general"),

		("Office phone not receiving calls",
		 "My desk phone stopped receiving incoming calls since yesterday afternoon. I can make outgoing calls fine.",
		 "step_by_step",
		 "Step 1: Check if Do Not Disturb mode is enabled. Step 2: Unplug the phone and reconnect after 30 seconds. Step 3: Contact the telephony team with your extension number if issue persists.",
		 3, "Medium", False, False, "general"),

		("Projector not connecting to laptop",
		 "I have a presentation in 30 minutes and the conference room projector will not connect to my laptop via HDMI.",
		 "quick_fix",
		 "Press Windows + P to open the display projection menu and select Duplicate or Extend. If still not detected try a different HDMI cable from the cabinet.",
		 1, "High", True, False, "general"),

		("Hard drive making clicking noise",
		 "My computer hard drive has started making a clicking noise when I open files. I am worried I might lose data.",
		 "step_by_step",
		 "Step 1: Immediately back up all important files to the shared network drive. Step 2: Stop using the machine for heavy tasks. Step 3: Escalate to IT immediately — clicking noise indicates imminent drive failure.",
		 3, "Critical", False, False, "general"),

		("New laptop setup required",
		 "I received a new laptop but it has not been set up yet. It needs company software installed and connected to the domain.",
		 "information",
		 "Raise a new device onboarding request through the IT portal. The setup team will schedule a session within 24 hours to configure the device, install required software, and join it to the company domain.",
		 1, "Medium", False, False, "general"),

		("USB drive not recognised",
		 "When I plug in my USB drive the computer does not detect it. I need the files urgently for a client meeting.",
		 "step_by_step",
		 "Step 1: Try a different USB port. Step 2: Test the USB drive on another computer. Step 3: Open Disk Management to check if drive appears without a letter assigned. Step 4: If not detected anywhere the drive may be faulty.",
		 4, "Medium", False, True, "general"),

		# ---------- ERP ----------
		("ERPNext application server is down",
		 "The ERPNext application is completely inaccessible. All users are getting a 502 Bad Gateway error.",
		 "step_by_step",
		 "Step 1: SSH into the server and run bench status to check services. Step 2: Run sudo supervisorctl restart all to restart bench workers. Step 3: Run bench restart as the bench user. Step 4: Check nginx error log for further errors. Step 5: If still down restart the server.",
		 5, "Critical", False, False, "erp"),

		("ERPNext loading very slowly",
		 "ERPNext has been extremely slow since this morning. Pages take 30-40 seconds to load. All departments are affected.",
		 "step_by_step",
		 "Step 1: Check server resource usage with htop. Step 2: Check for long-running background jobs in ERPNext scheduler. Step 3: Run bench clear-cache. Step 4: Check MariaDB slow query log for expensive queries.",
		 4, "High", True, False, "erp"),

		("Cannot access ERPNext from home",
		 "I am working from home and cannot access ERPNext. I get a connection timeout error.",
		 "step_by_step",
		 "Step 1: Connect to the company VPN first. Step 2: Once VPN is connected try accessing ERPNext again. Step 3: If still failing clear browser cache and try incognito mode.",
		 3, "Medium", True, False, "erp"),

		("Frappe worker not processing background jobs",
		 "Background jobs in ERPNext are stuck. Scheduled tasks are not running and email notifications are not being sent.",
		 "step_by_step",
		 "Step 1: Run bench status to check if workers are running. Step 2: Run sudo supervisorctl status to check worker processes. Step 3: Restart workers with sudo supervisorctl restart frappe-bench-worker. Step 4: Monitor the queue using bench doctor.",
		 4, "High", False, False, "erp"),

		("ERPNext database backup failed",
		 "I received an alert that last night scheduled database backup did not complete. We need to ensure data is protected.",
		 "step_by_step",
		 "Step 1: Check ERPNext backup log in Setup > Backups. Step 2: Verify disk space on the server. Step 3: Manually trigger a backup with bench --site sitename backup. Step 4: Configure backup alerts to notify IT team on failure.",
		 4, "High", False, False, "erp"),
	],

	"Software & Applications": [
		# ---------- GENERAL ----------
		("Microsoft Word keeps crashing",
		 "Word crashes every time I try to open a specific document. It was working fine yesterday. I need this document urgently.",
		 "step_by_step",
		 "Step 1: Try opening Word in safe mode by holding Ctrl while launching. Step 2: If it opens disable add-ins one by one. Step 3: Run Office Quick Repair from Control Panel. Step 4: If file-specific try opening on a different computer.",
		 4, "Medium", True, False, "general"),

		("Outlook not syncing emails",
		 "My Outlook has not received any new emails since this morning. Send/receive is trying but failing.",
		 "step_by_step",
		 "Step 1: Check internet connection and VPN. Step 2: Go to Send/Receive tab and click Send/Receive All Folders. Step 3: Check if Outlook is set to Work Offline and toggle it off. Step 4: Remove and re-add the email account if issue persists.",
		 4, "Medium", True, False, "general"),

		("Cannot install required software",
		 "I need to install Tableau for a data project but do not have admin rights on my machine.",
		 "information",
		 "Software installations require admin privileges. Raise a software installation request through the IT portal with business justification. IT will install within one business day.",
		 1, "Low", True, False, "general"),

		("Zoom camera not working during meetings",
		 "My camera stopped working in Zoom. Other participants cannot see me. The camera works in Windows camera app but not Zoom.",
		 "step_by_step",
		 "Step 1: In Zoom settings go to Video and check the correct camera is selected. Step 2: Close other apps that might be using the camera. Step 3: Uninstall and reinstall Zoom. Step 4: Update camera drivers from Device Manager.",
		 4, "Medium", True, False, "general"),

		("Excel file showing corrupted data",
		 "I opened an Excel file a colleague sent and all numbers look wrong. The file was fine yesterday.",
		 "step_by_step",
		 "Step 1: Try opening on another computer to confirm corruption. Step 2: Use File > Open > Open and Repair in Excel. Step 3: Ask sender to resend the original file. Step 4: Restore from backup if available.",
		 4, "High", False, False, "general"),

		("Browser homepage hijacked",
		 "My Chrome browser is opening a different homepage I did not set and keeps redirecting to unknown websites.",
		 "step_by_step",
		 "Step 1: Run a malware scan using company antivirus. Step 2: Go to Chrome Settings and reset the homepage. Step 3: Check installed extensions and remove unfamiliar ones. Step 4: Reset Chrome to default settings if redirects continue.",
		 4, "High", False, True, "general"),

		("Teams calls dropping frequently",
		 "My Microsoft Teams calls keep dropping after about 5 minutes. My internet seems fine for everything else.",
		 "step_by_step",
		 "Step 1: Check network bandwidth — Teams requires at least 1.5 Mbps for HD video. Step 2: Turn off video during calls to reduce bandwidth. Step 3: Clear Teams cache by deleting AppData/Microsoft/Teams cache folders. Step 4: Update Teams to the latest version.",
		 4, "Medium", True, False, "general"),

		("Which software does the company have licences for",
		 "I want to install some design tools but not sure which ones the company has licences for.",
		 "information",
		 "The licensed software list is on the IT portal under Software Catalogue. For design tools contact your department head for budget approval first then raise a software request through IT.",
		 1, "Low", False, False, "general"),

		("Antivirus blocking a legitimate file",
		 "The company antivirus is blocking a file I downloaded from our official vendor portal. The file is definitely safe.",
		 "quick_fix",
		 "Submit a file whitelist request through the IT security portal attaching the vendor download confirmation email. IT security will review and whitelist within 4 hours.",
		 1, "Medium", False, True, "general"),

		# ---------- ERP ----------
		("ERPNext Purchase Order form not saving",
		 "When I try to save a Purchase Order in ERPNext it shows a validation error but does not say what is wrong.",
		 "step_by_step",
		 "Step 1: Check the browser console (F12) for specific error messages. Step 2: Ensure all mandatory fields including Delivery Date and Supplier are filled. Step 3: Check item rates have correct UOM. Step 4: Try in a different browser to rule out cache issues.",
		 4, "Medium", True, False, "erp"),

		("Sales Invoice not generating automatically",
		 "Sales invoices are not being auto-generated from Sales Orders. This was working last week. Finance is waiting.",
		 "step_by_step",
		 "Step 1: Check Sales Order status is Submitted — auto-invoicing only works on submitted orders. Step 2: Verify customer payment terms allow automatic invoicing. Step 3: Check ERPNext scheduler is running with bench doctor. Step 4: Manually trigger from Sales Order if urgent.",
		 4, "High", False, False, "erp"),

		("HR Payroll processing throwing errors",
		 "ERPNext is throwing a component calculation error when running payroll for this month. We need to process by end of day.",
		 "step_by_step",
		 "Step 1: Identify employee records causing error from the error log. Step 2: Check salary structures are correctly assigned to all employees. Step 3: Verify all attendance records for the period are marked. Step 4: Re-run payroll after fixing employee-specific issues.",
		 4, "Critical", False, False, "erp"),

		("Stock ledger showing negative stock",
		 "ERPNext is showing negative stock for several items in our main warehouse. This should not be possible.",
		 "step_by_step",
		 "Step 1: Run Stock Ledger report filtered by affected items. Step 2: Identify transactions that caused negative stock — usually backdated entries. Step 3: Make a stock reconciliation entry to correct balances. Step 4: Enable Raise Error for Negative Stock setting.",
		 4, "High", False, False, "erp"),

		("ERPNext custom report not loading",
		 "A custom report we use every week is giving a script error and not loading. We need it for Monday morning review.",
		 "step_by_step",
		 "Step 1: Check the report script in Report Builder for syntax errors. Step 2: Run report in debug mode to identify the failing line. Step 3: Check if any linked DocType fields have been renamed. Step 4: Restore previous version from version history.",
		 4, "High", False, False, "erp"),
	],

	"Security & Threats": [
		# ---------- GENERAL ----------
		("Received suspicious phishing email",
		 "I received an email claiming to be from our CEO asking me to urgently purchase gift cards and send the codes.",
		 "step_by_step",
		 "Step 1: Do NOT click any links or reply. Step 2: Forward the email as an attachment to security@company.com. Step 3: Delete the email from inbox. Step 4: IT Security will investigate and send a company-wide alert if needed.",
		 4, "High", True, False, "general"),

		("Laptop stolen from office",
		 "My laptop was stolen from my desk while I stepped out for lunch. It contains client data and company files.",
		 "step_by_step",
		 "Step 1: Report theft to building security and file a police report immediately. Step 2: Contact IT Security to remotely wipe the device. Step 3: Change all passwords from a different device immediately. Step 4: IT will revoke access credentials and notify the data protection team.",
		 4, "Critical", False, False, "general"),

		("Suspected malware on my computer",
		 "My computer is behaving strangely — pop-ups appearing and browser redirecting. I think I clicked a bad link.",
		 "step_by_step",
		 "Step 1: Disconnect from the network immediately — unplug ethernet and disable WiFi. Step 2: Do NOT attempt to fix it yourself. Step 3: Call IT Security for emergency response. Step 4: IT will isolate the machine and run forensic analysis.",
		 4, "Critical", False, False, "general"),

		("USB device policy blocking my work drive",
		 "The security policy is blocking my USB drive which I use for legitimate work purposes.",
		 "quick_fix",
		 "Submit a USB device exception request through the IT Security portal with your device serial number and business justification. Approved exceptions are processed within one business day.",
		 1, "Medium", True, False, "general"),

		("Colleague accessed my computer without permission",
		 "I noticed someone logged into my computer while I was away. My session was not locked.",
		 "step_by_step",
		 "Step 1: Change your password immediately from a different device. Step 2: Report the incident to IT Security with time and details. Step 3: IT will check access logs. Step 4: Enable auto-lock screen timeout if not already set.",
		 4, "High", False, False, "general"),

		("Received email with suspicious attachment",
		 "I received an invoice email from an unknown sender with a ZIP attachment. I did not open it but wanted to report it.",
		 "quick_fix",
		 "Forward the email as an attachment to security@company.com and then delete it. Do not open the attachment under any circumstances.",
		 1, "Medium", True, False, "general"),

		("Account showing logins from unknown location",
		 "I received an alert that my account was logged into from a foreign country at 3am. I did not do this.",
		 "step_by_step",
		 "Step 1: Change your password immediately. Step 2: Enable multi-factor authentication. Step 3: Report to IT Security with alert details. Step 4: IT will investigate and terminate all active sessions.",
		 4, "Critical", False, False, "general"),

		("What is the company data classification policy",
		 "I am creating a document with client data and not sure what sensitivity label to apply.",
		 "information",
		 "The company data classification policy is on the intranet under IT Policies > Data Governance. Client data is typically classified as Confidential. Contact the Data Protection team for specific guidance.",
		 1, "Low", False, False, "general"),

		# ---------- ERP ----------
		("Unauthorised user accessing ERPNext financial data",
		 "A user from Sales can view Accounts and financial reports in ERPNext which they should not have access to.",
		 "step_by_step",
		 "Step 1: Go to ERPNext > User and check the user roles. Step 2: Remove any accounting roles that should not be assigned. Step 3: Review the role profile for excessive permissions. Step 4: Enable audit logging for this user to review past activity.",
		 4, "High", False, True, "erp"),

		("ERPNext admin credentials may be compromised",
		 "Someone may have the ERPNext administrator password. There are config changes I did not make.",
		 "step_by_step",
		 "Step 1: Change the Administrator password immediately. Step 2: Check ERPNext activity log for recent system changes. Step 3: Revoke all active admin sessions. Step 4: Enable two-factor authentication for admin accounts. Step 5: Escalate to IT Security for a full audit.",
		 5, "Critical", False, False, "erp"),
	],

	"Data & Reports": [
		# ---------- GENERAL ----------
		("Monthly sales report not generating",
		 "The automated monthly sales report that usually arrives on the first of the month has not been received. Finance is waiting.",
		 "step_by_step",
		 "Step 1: Check the report scheduler to see if the job ran. Step 2: Check email delivery logs for failures. Step 3: Manually trigger the report run. Step 4: Investigate why the scheduled run failed and fix the schedule.",
		 4, "High", True, False, "general"),

		("Excel file too large to open",
		 "A shared Excel file has grown to over 200MB and now takes forever to open or crashes. Multiple people edit it daily.",
		 "step_by_step",
		 "Step 1: Remove unused worksheets and named ranges. Step 2: Convert formulas to values where possible. Step 3: Split into smaller period-specific files. Step 4: Consider migrating to a database or BI tool.",
		 4, "Medium", False, False, "general"),

		("Cannot export data to CSV",
		 "When I try to export data from our reporting system to CSV it downloads an empty file. The data is there on screen.",
		 "step_by_step",
		 "Step 1: Try exporting a smaller dataset. Step 2: Try a different browser. Step 3: Clear browser cache and retry. Step 4: Check if a pop-up blocker is preventing the download.",
		 4, "Medium", True, False, "general"),

		("Database query taking too long",
		 "A query I run every day is suddenly taking 45 minutes instead of 2 minutes. Nothing has changed in my query.",
		 "step_by_step",
		 "Step 1: Check if database server is under unusual load. Step 2: Run EXPLAIN on your query to check for missing indexes. Step 3: Check if a large data import happened recently. Step 4: Contact the database admin team to review and optimise.",
		 4, "High", False, True, "general"),

		("How do I access the data warehouse",
		 "I have been asked to pull historical sales data from last year. How do I access the data warehouse?",
		 "information",
		 "Data warehouse access is available through the Business Intelligence portal. Request access through your manager first. Once approved you will receive credentials and a link to the BI training guide.",
		 1, "Low", False, False, "general"),

		("Report showing incorrect figures",
		 "The weekly stock report is showing figures that do not match what our team manually counted. The discrepancy is significant.",
		 "step_by_step",
		 "Step 1: Check date range and filters applied to the report. Step 2: Identify specific items with discrepancies. Step 3: Compare report data with source transaction records. Step 4: Escalate to the data team with specific examples.",
		 4, "High", True, False, "general"),

		("Need historical data for audit",
		 "Our auditors need transaction data from 3 years ago. How do I access archived data?",
		 "information",
		 "Historical data older than 2 years is in the archive database. Submit a data retrieval request through the IT portal with specific date range and data type. The Data team will provide a formal export within 2 business days.",
		 1, "Medium", False, False, "general"),

		# ---------- ERP ----------
		("ERPNext balance sheet showing wrong figures",
		 "The Balance Sheet in ERPNext is showing figures that do not match our manually maintained records. End of quarter is approaching.",
		 "step_by_step",
		 "Step 1: Run the General Ledger report for the same period to identify discrepancies. Step 2: Check for unposted journal entries affecting balances. Step 3: Verify opening balances were correctly entered. Step 4: Run the Recalculate Balance utility if available.",
		 4, "Critical", False, False, "erp"),

		("ERPNext inventory valuation report incorrect",
		 "The stock valuation report shows a value significantly different from last month with no major purchases.",
		 "step_by_step",
		 "Step 1: Check for backdated stock entries in the current period. Step 2: Run Stock Ledger for affected items to trace valuation changes. Step 3: Verify valuation method is consistent (FIFO/Moving Average). Step 4: Contact ERPNext admin to review recent system changes.",
		 4, "High", False, False, "erp"),

		("Custom ERPNext dashboard not updating",
		 "Our management dashboard in ERPNext has been showing yesterday data since this morning. It should refresh every hour.",
		 "step_by_step",
		 "Step 1: Check if background workers are running with bench doctor. Step 2: Manually refresh the dashboard from dashboard settings. Step 3: Check cache duration set on each dashboard chart. Step 4: Restart workers if stuck.",
		 4, "Medium", True, False, "erp"),
	],

	"Network & Connectivity": [
		# ---------- GENERAL ----------
		("Cannot connect to office WiFi",
		 "My laptop is not connecting to the office WiFi. It shows the network but says unable to connect. My phone connects fine.",
		 "step_by_step",
		 "Step 1: Forget the WiFi network and reconnect with credentials. Step 2: Restart the network adapter from Device Manager. Step 3: Flush DNS by running ipconfig /flushdns. Step 4: Contact IT to check if device MAC address needs to be registered.",
		 4, "Medium", True, False, "general"),

		("VPN not connecting from home",
		 "I am working from home and the company VPN keeps disconnecting every few minutes.",
		 "step_by_step",
		 "Step 1: Check home internet stability with a speed test. Step 2: Try connecting to a different VPN server if available. Step 3: Uninstall and reinstall the VPN client. Step 4: Switch from WiFi to wired ethernet at home.",
		 4, "High", True, False, "general"),

		("Internet connection very slow",
		 "The internet has been extremely slow at my workstation since this morning. Websites take forever to load.",
		 "step_by_step",
		 "Step 1: Restart your computer. Step 2: Try ethernet instead of WiFi. Step 3: Check if a large download or backup is running in background. Step 4: Contact IT to check your network port.",
		 4, "Medium", True, False, "general"),

		("Network printer not accessible",
		 "I cannot print to the floor printer. It was working yesterday. My colleagues on the same floor can still print.",
		 "step_by_step",
		 "Step 1: Remove and re-add the printer on your computer. Step 2: Restart the print spooler service. Step 3: Check if your computer is on the correct network segment. Step 4: Restart your network adapter.",
		 4, "Medium", True, True, "general"),

		("File server not accessible from my machine",
		 "I cannot access the shared file server drive. It shows a network path not found error. It worked yesterday.",
		 "step_by_step",
		 "Step 1: Check you are connected to office network or VPN. Step 2: Try accessing the server by IP address instead of hostname. Step 3: Run net use * /delete and remap the drive. Step 4: Contact IT if others can access it but you cannot.",
		 4, "Medium", False, False, "general"),

		("What is the guest WiFi password",
		 "I have a client visiting tomorrow and need the guest WiFi password for our meeting rooms.",
		 "information",
		 "Guest WiFi credentials are posted inside each meeting room near the door. If not found reception can provide the current password. Guest WiFi credentials rotate monthly for security.",
		 1, "Low", True, False, "general"),

		("Remote desktop connection failing",
		 "I am trying to remote desktop into my office machine from home but it keeps saying connection refused.",
		 "step_by_step",
		 "Step 1: Ensure you are connected to company VPN first. Step 2: Verify Remote Desktop is enabled on the office machine. Step 3: Confirm the office machine is not in sleep mode. Step 4: Check firewall rules are not blocking port 3389.",
		 4, "Medium", True, False, "general"),

		# ---------- ERP ----------
		("ERPNext not accessible from branch office",
		 "Our branch office team cannot access ERPNext today. Head office users are fine and branch has internet access.",
		 "step_by_step",
		 "Step 1: Check if branch can reach the server by pinging its IP. Step 2: Verify VPN or MPLS link between branch and datacenter is active. Step 3: Check firewall rules for the branch IP range. Step 4: Escalate to network team with branch IP details.",
		 4, "High", False, False, "erp"),

		("ERPNext sessions timing out too quickly",
		 "My ERPNext session keeps expiring every 10 minutes forcing me to log in repeatedly.",
		 "quick_fix",
		 "Go to ERPNext System Settings and increase the session expiry duration. Your system administrator can adjust this in Setup > System Settings > Session Expiry.",
		 1, "Low", True, False, "erp"),
	],

	"Account & Access": [
		# ---------- GENERAL ----------
		("Password expired and cannot log in",
		 "My Windows password expired and I cannot log into my computer. I tried changing it but it says the new password does not meet requirements.",
		 "quick_fix",
		 "Call the IT helpdesk on extension 100 to reset your password. Requirements: minimum 10 characters, uppercase, lowercase, number, and special character, cannot match last 5 passwords.",
		 1, "High", True, False, "general"),

		("Account locked after failed login attempts",
		 "I have been locked out of my account after entering the wrong password too many times. I need access urgently.",
		 "quick_fix",
		 "Account will automatically unlock after 30 minutes. For immediate access call IT helpdesk on extension 100. Have your employee ID ready for verification.",
		 1, "High", True, False, "general"),

		("Need access to Finance shared drive",
		 "I have joined the Finance team and need access to the Finance shared network drive. My manager has approved this.",
		 "step_by_step",
		 "Step 1: Your manager raises an access request through the IT portal. Step 2: IT verifies approval and grants access within 4 business hours. Step 3: You will receive a confirmation email once provisioned.",
		 3, "Medium", True, False, "general"),

		("New employee laptop and account setup",
		 "We have a new team member joining on Monday. They need a laptop, company email, and access to our project management tool.",
		 "step_by_step",
		 "Step 1: Submit a new employee onboarding request through HR portal at least 3 days before joining. Step 2: IT will create the email account and configure the laptop. Step 3: Line manager must approve specific system access. Step 4: New employee receives credentials on first day.",
		 4, "Medium", True, False, "general"),

		("Email account not working after name change",
		 "I recently got married and my name was updated in HR. My old email address is not working and I have not received a new one.",
		 "step_by_step",
		 "Step 1: Contact HR to confirm name change is processed. Step 2: IT will create the new email address and set up forwarding from old address. Step 3: New credentials will be provided within one business day of HR confirmation.",
		 3, "Medium", False, False, "general"),

		("Cannot access project management tool",
		 "I cannot log into Jira. It says my account does not exist. I had access last quarter.",
		 "step_by_step",
		 "Step 1: Check if licence was deactivated due to inactivity. Step 2: Manager raises a licence reactivation request through IT portal. Step 3: IT restores access within 2 business hours.",
		 3, "Medium", True, False, "general"),

		("What permissions does the IT Admin role have",
		 "I am a new IT team member and want to understand what access the IT Admin role provides.",
		 "information",
		 "IT Admin role permissions are documented in the IT Access Control document on the intranet under IT Governance. For system-specific permissions refer to the Access Matrix spreadsheet. Your team lead can walk you through during onboarding.",
		 1, "Low", False, False, "general"),

		("Two-factor authentication not working on new phone",
		 "Since I got a new phone my authenticator app does not work. I cannot log into any company systems.",
		 "step_by_step",
		 "Step 1: Contact IT helpdesk — they will temporarily disable 2FA on your account. Step 2: Log in, go to security settings, and set up 2FA on new phone. Step 3: Save backup codes in a secure location.",
		 3, "High", True, False, "general"),

		# ---------- ERP ----------
		("ERPNext permission denied on Purchase module",
		 "I am getting a permission denied error when trying to create a Purchase Order. I had this access last week.",
		 "step_by_step",
		 "Step 1: Check your ERPNext profile for current roles. Step 2: Verify Purchase User or Purchase Manager role is assigned. Step 3: If role was removed manager must raise an access request. Step 4: Check if role-based permissions for Purchase DocType changed recently.",
		 4, "Medium", True, True, "erp"),

		("Cannot add new user to ERPNext",
		 "I am trying to add a new employee to ERPNext but getting an error saying user limit has been reached.",
		 "step_by_step",
		 "Step 1: Go to ERPNext Settings and check current user count against licence limit. Step 2: Identify inactive users who can be deactivated. Step 3: If additional licences needed contact your ERPNext account manager. Step 4: Deactivate the inactive user then add the new one.",
		 4, "High", False, False, "erp"),

		("ERPNext role not restricting access correctly",
		 "A user with Sales User role can see purchase prices which they should not be able to access.",
		 "step_by_step",
		 "Step 1: Go to Role Permissions Manager and review Sales User role access. Step 2: Check field-level permissions are set correctly for Item Price fields. Step 3: Remove overly broad permissions. Step 4: Test with affected user account to confirm restriction works.",
		 4, "High", False, True, "erp"),
	],
}


def derive_confidence(is_ambiguous: bool, is_repeated: bool, base_priority: str) -> float:
	"""
	Confidence score logic:
	- Ambiguous tickets → low confidence (model uncertain between categories)
	- Critical/novel tickets → lower confidence (complex, unusual)
	- Repeated known issues → high confidence (model has seen these many times)
	- Normal tickets → moderate to high confidence
	"""
	if is_ambiguous:
		return round(random.uniform(0.38, 0.62), 2)
	if is_repeated:
		return round(random.uniform(0.80, 0.98), 2)
	if base_priority == "Critical":
		return round(random.uniform(0.42, 0.68), 2)
	if base_priority == "High":
		return round(random.uniform(0.65, 0.85), 2)
	return round(random.uniform(0.72, 0.96), 2)


def derive_feedback(was_escalated: bool, confidence: float, is_repeated: bool) -> str:
	"""
	Feedback logic:
	- Escalated tickets → feedback is escalated
	- Low confidence + not escalated → likely not_helpful
	- High confidence + repeated → very likely satisfied
	- Others → weighted mix
	"""
	if was_escalated:
		return "escalated"
	if confidence < 0.55:
		return random.choices(["not_helpful", "escalated"], weights=[70, 30])[0]
	if is_repeated and confidence > 0.80:
		return random.choices(["satisfied", "not_helpful"], weights=[90, 10])[0]
	return random.choices(["satisfied", "not_helpful"], weights=[75, 25])[0]


def derive_escalation(priority: str, confidence: float) -> bool:
	if priority == "Critical":
		return True
	if priority == "High" and confidence < 0.60:
		return True
	if confidence < 0.45:
		return True
	return False


def apply_style(description: str) -> str:
	return random.choice(STYLE_WRAPPERS)(description)


def generate_all_data():
	ticket_counters = {cat: {"general": 0, "erp": 0} for cat in TEMPLATES}
	total_written = 0

	print("=" * 60)
	print("TicketBrain — Synthetic Training Data Generator")
	print("=" * 60)
	print(f"Output  : {OUTPUT_FILE}")
	print("=" * 60)

	with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
		writer.writeheader()

		for category, templates in TEMPLATES.items():
			prefix = CATEGORY_PREFIX[category]
			general_templates = [t for t in templates if t[8] == "general"]
			erp_templates = [t for t in templates if t[8] == "erp"]

			print(f"\nCategory: {category}  [{prefix}]")

			# 200 general tickets
			for _ in range(200):
				tmpl = random.choice(general_templates)
				subject, desc, res_type, resolution, steps, base_priority, is_repeated, is_ambiguous, source = tmpl

				priorities = ["Low", "Medium", "High", "Critical"]
				weights_map = {
					"Low": [70, 25, 5, 0],
					"Medium": [10, 60, 25, 5],
					"High": [0, 15, 65, 20],
					"Critical": [0, 0, 0, 100],
				}
				priority = random.choices(priorities, weights=weights_map[base_priority])[0]
				confidence = derive_confidence(is_ambiguous, is_repeated, base_priority)
				was_escalated = derive_escalation(priority, confidence)
				feedback = derive_feedback(was_escalated, confidence, is_repeated)

				ticket_counters[category]["general"] += 1
				seq = ticket_counters[category]["general"]

				writer.writerow({
					"ticket_id": f"{prefix}-G-{seq:04d}",
					"subject": subject,
					"description": apply_style(desc),
					"category": category,
					"priority": priority,
					"department": random.choice(DEPARTMENTS),
					"resolution_type": res_type,
					"resolution": resolution,
					"resolved_in_steps": steps,
					"confidence_score": confidence,
					"feedback": feedback,
					"was_escalated": was_escalated,
					"is_repeated_issue": is_repeated,
					"is_ambiguous": is_ambiguous,
					"source": source,
				})

			# 100 erp tickets
			for _ in range(100):
				tmpl = random.choice(erp_templates)
				subject, desc, res_type, resolution, steps, base_priority, is_repeated, is_ambiguous, source = tmpl

				priority = random.choices(priorities, weights=weights_map[base_priority])[0]
				confidence = derive_confidence(is_ambiguous, is_repeated, base_priority)
				was_escalated = derive_escalation(priority, confidence)
				feedback = derive_feedback(was_escalated, confidence, is_repeated)

				ticket_counters[category]["erp"] += 1
				seq = ticket_counters[category]["erp"]

				writer.writerow({
					"ticket_id": f"{prefix}-E-{seq:04d}",
					"subject": subject,
					"description": apply_style(desc),
					"category": category,
					"priority": priority,
					"department": random.choice(DEPARTMENTS),
					"resolution_type": res_type,
					"resolution": resolution,
					"resolved_in_steps": steps,
					"confidence_score": confidence,
					"feedback": feedback,
					"was_escalated": was_escalated,
					"is_repeated_issue": is_repeated,
					"is_ambiguous": is_ambiguous,
					"source": source,
				})

			total_written += 300
			f.flush()
			print(f"  ✓  300 tickets written  (total: {total_written})")

	print("\n" + "=" * 60)
	print(f"Done — {total_written} tickets saved to {OUTPUT_FILE}")
	print("=" * 60)


if __name__ == "__main__":
	generate_all_data()
