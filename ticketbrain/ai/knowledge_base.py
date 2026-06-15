"""
TicketBrain Knowledge Base — structured IT support articles per category.
Each article is a self-contained resolution for a specific sub-problem.
These are embedded at build time and used for RAG retrieval at runtime.
"""

KB_ARTICLES: list[dict] = [

    # ── Hardware & Infrastructure ────────────────────────────────────────────

    {
        "id": "hw-001",
        "category": "Hardware & Infrastructure",
        "title": "Laptop won't turn on or no power",
        "content": (
            "If the laptop shows no signs of power: first confirm the charger is firmly "
            "seated in both the laptop port and the wall socket. Try a different power outlet. "
            "Hold the power button for 30 seconds to drain residual charge, then connect the "
            "charger and try again. If the charging LED does not light, the charger or the "
            "charging port may be faulty. Check the asset tag (sticker on the bottom or back), "
            "note the model, and submit a hardware replacement request via the IT portal with "
            "the asset tag number. Do not attempt to open the device."
        ),
        "keywords": ["no power", "won't turn on", "dead", "not starting", "blank screen", "black screen"],
    },
    {
        "id": "hw-002",
        "category": "Hardware & Infrastructure",
        "title": "Blue screen of death (BSOD) or system crash",
        "content": (
            "A BSOD indicates a hardware or driver-level failure. Note the error code displayed "
            "(e.g. MEMORY_MANAGEMENT, DRIVER_IRQL_NOT_LESS_OR_EQUAL). After the system reboots, "
            "open Event Viewer (search in Start menu) → Windows Logs → System — look for Critical "
            "or Error events near the crash time. Common causes: faulty RAM, overheating, "
            "corrupted driver. Run Windows Memory Diagnostic (search in Start menu) and let it "
            "complete overnight. If crashes continue, boot into Safe Mode and check Device Manager "
            "for yellow-flagged drivers. Provide IT with the error code and Event Viewer log."
        ),
        "keywords": ["blue screen", "bsod", "crash", "system crash", "kernel panic", "error code"],
    },
    {
        "id": "hw-003",
        "category": "Hardware & Infrastructure",
        "title": "Laptop overheating or fan running constantly",
        "content": (
            "Constant fan noise or thermal shutdown means the CPU is running hot. Ensure the "
            "laptop is on a hard flat surface — soft surfaces (beds, cushions) block vents. "
            "Check Task Manager (Ctrl+Shift+Esc) → CPU column for any process using high CPU; "
            "if found, end it. Compressed air can clear vent dust: hold the can upright, "
            "spray short bursts into side vents. If the device is more than 2 years old, "
            "thermal paste may need renewal — submit a hardware maintenance request. "
            "A laptop cooling pad provides immediate relief while the ticket is processed."
        ),
        "keywords": ["overheating", "hot", "fan noise", "loud fan", "thermal", "heat"],
    },
    {
        "id": "hw-004",
        "category": "Hardware & Infrastructure",
        "title": "External monitor not detected or no display",
        "content": (
            "When connecting an external monitor: press Win+P to open the display projection "
            "menu and choose 'Extend' or 'Duplicate'. If the monitor still shows no signal, "
            "try a different cable (HDMI/DisplayPort) and confirm the monitor's input source "
            "matches the cable type. Right-click the desktop → Display settings → Detect to "
            "force Windows to scan for displays. If using a dock or USB-C hub, connect the "
            "monitor directly to the laptop first to isolate the dock. Update graphics drivers "
            "via Device Manager if no other solution works."
        ),
        "keywords": ["monitor", "external display", "no signal", "second screen", "hdmi", "display port", "dock"],
    },
    {
        "id": "hw-005",
        "category": "Hardware & Infrastructure",
        "title": "Keyboard or mouse not working",
        "content": (
            "For USB keyboard/mouse: unplug and replug into a different USB port. Test on "
            "another computer if possible. Check Device Manager for unknown devices or error "
            "flags. For wireless peripherals: replace batteries, move the USB receiver to a "
            "port closer to the device, and re-pair if there is a pairing button. For laptop "
            "keyboard issues, restart first as driver hangs are common. If specific keys are "
            "physically stuck, a keycap puller can free them; if keys are broken, request a "
            "keyboard replacement via the hardware portal."
        ),
        "keywords": ["keyboard", "mouse", "not working", "keys", "wireless", "peripheral", "usb"],
    },
    {
        "id": "hw-006",
        "category": "Hardware & Infrastructure",
        "title": "Printer not printing or offline",
        "content": (
            "Check the printer's display panel for paper jams, low toner, or error codes — "
            "resolve any physical issues first. On the computer: Settings → Printers & scanners "
            "→ select the printer → Open print queue. Cancel all stuck jobs. Right-click the "
            "printer → See what's printing → Printer menu → uncheck 'Use Printer Offline'. "
            "Restart the Print Spooler: open Services (search in Start), find 'Print Spooler', "
            "right-click → Restart. For network printers, confirm you are on the correct VPN "
            "profile; printers on office networks may not be reachable when on remote VPN."
        ),
        "keywords": ["printer", "printing", "offline", "print queue", "stuck job", "toner", "paper jam"],
    },

    # ── Software & Applications ──────────────────────────────────────────────

    {
        "id": "sw-001",
        "category": "Software & Applications",
        "title": "Application crashes on startup or won't open",
        "content": (
            "Close all instances: open Task Manager (Ctrl+Shift+Esc) → find the application "
            "in the list → End Task. Clear the application's temp data: press Win+R → type "
            "%localappdata% → find the application folder → delete the Cache subfolder only. "
            "Run the installer in repair mode: Control Panel → Programs → select the app → "
            "Change → Repair. If the application logs errors, find them in Event Viewer "
            "(Windows Logs → Application) and include the error text in your ticket. "
            "If repair fails, uninstall via the company software portal and reinstall the "
            "latest version from the same portal."
        ),
        "keywords": ["crash", "won't open", "not opening", "startup crash", "application crash", "app not loading"],
    },
    {
        "id": "sw-002",
        "category": "Software & Applications",
        "title": "Microsoft Office application (Word/Excel/Outlook) freezes",
        "content": (
            "Office freezes are often caused by a corrupt add-in or a damaged Normal.dotm "
            "template. Start the frozen app in Safe Mode: hold Ctrl while launching it. If "
            "it works in Safe Mode, an add-in is the culprit — File → Options → Add-ins → "
            "Manage COM Add-ins → disable them one by one. For Outlook specifically, run the "
            "Inbox Repair Tool (scanpst.exe) found in C:\\Program Files\\Microsoft Office\\root\\. "
            "For recurring freezes in Excel, check if the file is stored on a slow network "
            "share — copy it locally before editing."
        ),
        "keywords": ["office", "word", "excel", "outlook", "freeze", "hangs", "slow", "not responding", "microsoft"],
    },
    {
        "id": "sw-003",
        "category": "Software & Applications",
        "title": "Software installation fails or requires admin rights",
        "content": (
            "Standard user accounts cannot install software directly. Submit a software "
            "installation request via the IT portal: include the software name, version, "
            "business justification, and your manager's approval. IT will deploy the software "
            "via the managed software portal (SCCM/Intune) within the agreed SLA. "
            "If you see an approved software tile in the Company Portal app that fails to "
            "install, note the error code shown in the portal and include it in your ticket. "
            "Do not attempt to bypass UAC prompts or use admin credentials that are not yours."
        ),
        "keywords": ["install", "installation", "admin rights", "administrator", "uac", "permissions", "software request"],
    },
    {
        "id": "sw-004",
        "category": "Software & Applications",
        "title": "Browser is slow, crashing, or showing errors",
        "content": (
            "Browser performance degrades with too many extensions or accumulated cache. "
            "Clear cache: Ctrl+Shift+Delete → select Cached images and files + Cookies → "
            "Clear. Disable extensions: browser menu → Extensions → disable all, then "
            "re-enable one by one to find the culprit. If a specific website fails, try it "
            "in an incognito/private window to bypass extensions and cache. For 'Your "
            "connection is not private' SSL errors on internal sites, your system clock may "
            "be wrong — right-click the taskbar clock → Adjust date/time → Sync now."
        ),
        "keywords": ["browser", "chrome", "edge", "firefox", "slow", "crash", "not loading", "ssl", "error", "website"],
    },
    {
        "id": "sw-005",
        "category": "Software & Applications",
        "title": "VPN client not connecting",
        "content": (
            "If the VPN client shows 'Connection failed' or 'Authentication error': "
            "verify you are using your current corporate credentials (password may have changed). "
            "Ensure the correct VPN profile is selected — there are separate profiles for "
            "office and remote workers. Disconnect any other VPN or proxy running simultaneously. "
            "Restart the VPN service: open Services → find the VPN service → Restart. "
            "If MFA (multi-factor) is failing, ensure your authenticator app time is in sync. "
            "Uninstall and reinstall the VPN client as a last resort using the package from "
            "the IT software portal."
        ),
        "keywords": ["vpn", "connection failed", "authentication", "remote access", "tunnel", "cisco", "globalprotect"],
    },
    {
        "id": "sw-006",
        "category": "Software & Applications",
        "title": "Antivirus blocking or quarantining a file",
        "content": (
            "When antivirus quarantines a file you need: open the antivirus console "
            "→ Quarantine/History section → find the file. If you are confident the file "
            "is legitimate (received from a trusted source, known business file), submit "
            "an exclusion request to the IT Security team including: the full file path, "
            "the exact detection name, and the business reason. Do not restore quarantined "
            "files on your own — Security must review first. If antivirus is blocking "
            "a business-critical application from running, submit a ticket with the "
            "application name and detection string for a whitelist addition."
        ),
        "keywords": ["antivirus", "quarantine", "blocked", "malware", "defender", "security scan", "whitelist"],
    },

    # ── Network & Connectivity ────────────────────────────────────────────────

    {
        "id": "net-001",
        "category": "Network & Connectivity",
        "title": "No internet or network connectivity",
        "content": (
            "First confirm whether the issue is total network loss or specific to one "
            "site/application. Test by opening multiple websites and pinging 8.8.8.8 in "
            "Command Prompt (ping 8.8.8.8). If ping fails, right-click the network icon "
            "→ Troubleshoot problems → follow the wizard. Release and renew IP: open "
            "Command Prompt as admin → ipconfig /release → ipconfig /renew. Check if other "
            "devices on the same network have internet; if they do, the issue is your machine. "
            "Reset network stack: netsh int ip reset → netsh winsock reset → restart. "
            "If at the office, check the ethernet cable and switch port light."
        ),
        "keywords": ["no internet", "no network", "cannot browse", "offline", "connectivity", "disconnected"],
    },
    {
        "id": "net-002",
        "category": "Network & Connectivity",
        "title": "Wi-Fi dropping frequently or slow speed",
        "content": (
            "Frequent Wi-Fi drops are usually caused by channel congestion or weak signal. "
            "Move closer to the access point and check if the issue persists. Forget the "
            "network and reconnect: Settings → Network → Wi-Fi → Manage known networks → "
            "forget → reconnect. Update the Wi-Fi adapter driver via Device Manager. "
            "Disable Wi-Fi power saving: Device Manager → Network Adapters → right-click "
            "Wi-Fi adapter → Properties → Power Management → uncheck 'Allow the computer "
            "to turn off this device to save power'. If in the office, report the floor "
            "and room to IT so they can check access point health."
        ),
        "keywords": ["wifi", "wi-fi", "wireless", "dropping", "slow speed", "unstable", "disconnecting"],
    },
    {
        "id": "net-003",
        "category": "Network & Connectivity",
        "title": "Cannot access a specific website or internal resource",
        "content": (
            "If only one site or internal resource is unreachable: try it in a different "
            "browser and in an incognito window. Flush DNS: Command Prompt as admin → "
            "ipconfig /flushdns. Check if the site is down for everyone via a status page. "
            "For internal resources (intranet, SharePoint, internal apps): confirm your "
            "VPN is connected using the correct profile. If using a proxy, check that the "
            "proxy settings are correct in Settings → Proxy. For certificate errors on "
            "internal HTTPS sites, the corporate root CA certificate may need to be "
            "reinstalled — submit a ticket to IT with the site URL and exact error text."
        ),
        "keywords": ["website", "site down", "internal resource", "intranet", "sharepoint", "cannot reach", "blocked site"],
    },
    {
        "id": "net-004",
        "category": "Network & Connectivity",
        "title": "Slow network performance or high latency",
        "content": (
            "Run a speed test (speedtest.net or fast.com) and note the results. High ping "
            "to a VPN server means the VPN profile needs to be changed — select a geographically "
            "closer server. Check Task Manager → Performance → Ethernet/Wi-Fi — high network "
            "utilisation from a background process (Windows Update, OneDrive sync, backup) "
            "can saturate the link. Pause background sync if actively on a call or download. "
            "If the entire office is slow, it is likely a WAN or ISP issue — report to IT "
            "with the speed test result and your floor/location so they can check the uplink."
        ),
        "keywords": ["slow network", "high latency", "ping", "lag", "slow upload", "slow download", "bandwidth"],
    },
    {
        "id": "net-005",
        "category": "Network & Connectivity",
        "title": "Network printer or shared drive not accessible",
        "content": (
            "Network printers and shared drives require you to be on the corporate network "
            "or connected via VPN split-tunnel. Confirm VPN status first. For shared drives: "
            "open File Explorer → type \\\\server-name in the address bar → enter corporate "
            "credentials if prompted. If the path has changed, ask your manager for the "
            "current UNC path. For printers: Settings → Printers → Add printer → 'The "
            "printer that I want isn't listed' → Add by IP address or hostname. IT can "
            "provide the hostname of the printer nearest your desk."
        ),
        "keywords": ["shared drive", "network drive", "mapped drive", "printer", "file share", "unc path", "access denied"],
    },

    # ── Account & Access ──────────────────────────────────────────────────────

    {
        "id": "acc-001",
        "category": "Account & Access",
        "title": "Forgot password or account locked out",
        "content": (
            "Corporate accounts lock automatically after 5 failed login attempts and unlock "
            "after 30 minutes. If you cannot wait: call the IT helpdesk on extension 100 "
            "for an immediate manual unlock — identity verification is required. "
            "To reset your own password without IT: go to the self-service portal at "
            "accounts.company.com → 'Forgot Password' → verify via mobile OTP or security "
            "questions. The new password must meet policy: 12+ characters, upper + lower + "
            "number + symbol. After reset, update the saved password in your VPN client "
            "and any other apps that store it, otherwise they will re-lock the account."
        ),
        "keywords": ["forgot password", "locked out", "account locked", "reset password", "cannot login", "login failed"],
    },
    {
        "id": "acc-002",
        "category": "Account & Access",
        "title": "Multi-factor authentication (MFA) not working",
        "content": (
            "If the authenticator app shows wrong codes: the device clock may be out of "
            "sync. On Android: Settings → Date & time → Use network-provided time. "
            "On iPhone: Settings → General → Date & Time → Set Automatically. "
            "If you have changed phones or lost your device: call the IT helpdesk on "
            "extension 100 — do not attempt to reset MFA yourself, as this requires "
            "identity verification. If MFA push notifications are not arriving: check "
            "that mobile data or Wi-Fi is active and the authenticator app has notification "
            "permissions. Try the 'Use code instead' fallback on the login page."
        ),
        "keywords": ["mfa", "multi-factor", "authenticator", "two factor", "2fa", "otp", "code not working"],
    },
    {
        "id": "acc-003",
        "category": "Account & Access",
        "title": "Need access to a new system, application, or shared mailbox",
        "content": (
            "Access to new systems must be approved by your line manager before IT can "
            "provision it. Process: your manager submits an access request form via the "
            "IT portal, selecting the system and your role-based access level. IT provisions "
            "within 1 business day for standard systems and up to 3 days for sensitive systems "
            "(finance, HR). You will receive an email when access is granted. For shared "
            "mailboxes: your manager must be the mailbox owner or delegate to request access "
            "on your behalf. Do not share accounts or passwords as a workaround."
        ),
        "keywords": ["access request", "new system", "permission", "shared mailbox", "need access", "provisioning", "role"],
    },
    {
        "id": "acc-004",
        "category": "Account & Access",
        "title": "Single Sign-On (SSO) or SAML authentication failing",
        "content": (
            "SSO failures usually show as a redirect loop or 'Authentication failed' after "
            "the login screen. Clear browser cookies for the identity provider domain "
            "(company.okta.com or accounts.company.com): browser settings → Privacy → "
            "Clear browsing data → Cookies → filter by the domain → delete. Try an "
            "incognito window which has no cached SSO tokens. If SSO fails only on your "
            "machine but works on others, your corporate certificate may have expired — "
            "run certmgr.msc and check the certificate expiry under 'Personal'. "
            "Contact IT with the exact error message and the application name."
        ),
        "keywords": ["sso", "single sign on", "saml", "okta", "azure ad", "authentication failed", "redirect loop"],
    },
    {
        "id": "acc-005",
        "category": "Account & Access",
        "title": "Permission denied when accessing a file or folder",
        "content": (
            "Access denied errors on files or folders mean your account does not have the "
            "required permissions. You cannot grant yourself access — the file/folder owner "
            "or your manager must submit a permission change request. To find the owner: "
            "right-click the file → Properties → Security → Advanced → Owner. "
            "Contact the listed owner and ask them to submit an IT access request for you. "
            "For SharePoint or OneDrive: the site owner can grant access directly from the "
            "SharePoint settings menu without involving IT. Include the exact file/folder "
            "path and the error text in your request."
        ),
        "keywords": ["permission denied", "access denied", "file access", "folder", "unauthorized", "sharepoint permission"],
    },

    # ── Security & Threats ────────────────────────────────────────────────────

    {
        "id": "sec-001",
        "category": "Security & Threats",
        "title": "Received a suspicious or phishing email",
        "content": (
            "Do not click any links, open attachments, reply, or forward the email to "
            "colleagues. Forward it as an attachment (not inline) to security@company.com: "
            "in Outlook, create a new email to security@company.com, then drag the "
            "suspicious email into the compose window — this attaches the full headers. "
            "Then permanently delete the original from your inbox and empty your Deleted "
            "Items. If you already clicked a link: disconnect from the network immediately "
            "and call IT Security on the emergency line. Time between click and isolation "
            "determines how much damage can be limited."
        ),
        "keywords": ["phishing", "suspicious email", "spam", "scam email", "fake email", "malicious link"],
    },
    {
        "id": "sec-002",
        "category": "Security & Threats",
        "title": "Clicked a suspicious link or opened a malicious attachment",
        "content": (
            "Act immediately — speed matters. Step 1: disconnect from the network now "
            "(unplug ethernet AND turn off Wi-Fi). Step 2: call IT Security emergency line "
            "— do not wait, do not email. Step 3: do not shut down the computer — "
            "memory forensics needs the machine running. Step 4: document exactly what you "
            "clicked, when, and any pop-ups or behaviour you noticed. "
            "The security team will isolate the device, run forensics, and determine "
            "if credentials were exposed. You will be issued a replacement device while "
            "investigation is underway. Password resets for any potentially exposed "
            "accounts will be initiated by Security."
        ),
        "keywords": ["clicked link", "opened attachment", "malware", "infected", "ransomware", "virus", "compromised"],
    },
    {
        "id": "sec-003",
        "category": "Security & Threats",
        "title": "Suspecting a data breach or unauthorised account access",
        "content": (
            "Signs of unauthorised access: login alerts from unknown locations, sent emails "
            "you did not write, files moved or deleted, unexpected password changes. "
            "Immediate actions: change your corporate password immediately at accounts.company.com, "
            "then review and terminate all active sessions (accounts.company.com → My Sessions → "
            "Sign out all). Report to IT Security with timestamps and any evidence. "
            "If corporate data may have been exfiltrated, this is a potential data breach "
            "and must be reported to your manager and the Data Protection Officer (DPO) "
            "within 24 hours per regulatory requirements."
        ),
        "keywords": ["breach", "unauthorized access", "hacked", "account compromised", "data leak", "suspicious login"],
    },
    {
        "id": "sec-004",
        "category": "Security & Threats",
        "title": "Device lost or stolen",
        "content": (
            "Report immediately: call IT Security (extension 999) within the hour. "
            "IT will remotely wipe the device and invalidate all stored credentials. "
            "Change your corporate password from another device immediately. "
            "File a police report if stolen — the insurance and compliance process "
            "requires a crime reference number. For laptops: provide the asset tag if "
            "you have it (it should be on your equipment record in the IT portal). "
            "IT will issue a temporary replacement device and restore from your last "
            "cloud backup. Do not attempt to remote-wipe yourself if IT has already "
            "been notified, as this can interfere with forensic tracking."
        ),
        "keywords": ["lost device", "stolen", "laptop stolen", "phone lost", "remote wipe", "missing device"],
    },

    # ── Data & Reports ────────────────────────────────────────────────────────

    {
        "id": "data-001",
        "category": "Data & Reports",
        "title": "Report shows wrong or missing data",
        "content": (
            "Before escalating: check the report filters carefully — date range, department, "
            "status filters, and any hierarchy selections. Run the same report with no "
            "filters to see the full dataset. Clear your browser cache (Ctrl+Shift+Delete) "
            "and regenerate — cached report pages often show stale data. If the data is "
            "genuinely wrong: take a screenshot of the report output, note the exact filters "
            "used, and cross-check 3-5 specific records against the source system (the "
            "individual transaction or entry). Provide these example discrepancies in your "
            "ticket — 'data is wrong' without examples cannot be investigated."
        ),
        "keywords": ["wrong data", "missing data", "incorrect report", "data discrepancy", "report error", "blank report"],
    },
    {
        "id": "data-002",
        "category": "Data & Reports",
        "title": "Cannot export report to Excel or CSV",
        "content": (
            "If the Excel export produces a blank file or download error: try exporting "
            "to CSV first (CSV is simpler and bypasses Excel formatting issues). Open the "
            "CSV in Excel via File → Open → Browse. If the CSV itself is blank: check "
            "whether the report has a row limit — large reports may need to be split by "
            "date range. Disable browser pop-up blockers for the reporting site (pop-up "
            "blocking prevents download dialogs). If using Internet Explorer compatibility "
            "mode: switch to Edge in standard mode. For Power BI exports: ensure the "
            "visual has export enabled by the report owner."
        ),
        "keywords": ["export", "download", "excel export", "csv", "report download", "blank file", "power bi"],
    },
    {
        "id": "data-003",
        "category": "Data & Reports",
        "title": "Request to correct incorrect data in source system",
        "content": (
            "Data corrections in production systems require a formal change request — "
            "do not edit records directly even if you have write access. The process: "
            "identify the specific record(s) with the error (record ID, transaction number, "
            "employee ID etc.), document the current wrong value and the correct value, "
            "and get written confirmation from the record owner (the relevant department "
            "head). Submit a data correction request via the IT portal. Changes are "
            "audited and require approval from the data owner and IT before execution. "
            "Corrections to financial data also require sign-off from Finance."
        ),
        "keywords": ["data correction", "wrong entry", "edit record", "fix data", "incorrect data", "data change"],
    },
    {
        "id": "data-004",
        "category": "Data & Reports",
        "title": "Scheduled report not arriving by email",
        "content": (
            "Check your spam/junk folder first — report emails are often mis-flagged. "
            "Add the report sender address to your safe senders list. Log into the "
            "reporting system and check the scheduled report settings: confirm it is "
            "still active, the recipient list includes your current email address, "
            "and the schedule time is correct (check for timezone mismatches). "
            "If the report ran but you did not receive it, check the report system's "
            "delivery log (usually under 'Subscriptions' or 'Scheduled Reports'). "
            "If the report did not run at all, check if there was a system maintenance "
            "window that interrupted the schedule."
        ),
        "keywords": ["scheduled report", "report not arriving", "subscription", "automated report", "email report"],
    },
]
