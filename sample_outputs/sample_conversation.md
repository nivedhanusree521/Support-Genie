# Sample Conversation Transcript — SupportGenie

This transcript illustrates all three tools, conditional routing, and
multi-turn state/memory, using the seeded sample data in `data/`. It was
produced by running the app with `OPENAI_MODEL=gpt-4o-mini`; exact wording
will vary slightly between runs since the response is LLM-generated, but the
tool-call behavior and grounding in the underlying data will match.

---

### Scenario 1 — Knowledge Search

**User:** How do I reset my VPN password?

**🔧 Tool used:** `knowledge_search` → `{"query": "How do I reset my VPN password?"}`
**Tool result:** matched article `KB-001 — Resetting Your VPN Password`

**Assistant:**
> To reset your VPN password: go to https://vpn-portal.fictionalcorp.com/reset and enter your
> company email address. You'll receive a reset link valid for 15 minutes — choose a new
> password (minimum 10 characters, with at least one number and one symbol), then reconnect
> using the Cisco AnyConnect client. If the reset link doesn't arrive within 5 minutes, check
> your spam folder or let me know and I can help you raise a ticket.

---

### Scenario 2 — Ticket Lookup

**User:** What is the status of ticket TCK-1001?

**🔧 Tool used:** `ticket_lookup` → `{"ticket_id": "TCK-1001"}`
**Tool result:** 1 ticket found (employee EMP1003, category Hardware, status "In Progress")

**Assistant:**
> Ticket TCK-1001 (Hardware) is currently **In Progress**. It was raised for a laptop screen
> that flickers intermittently and occasionally goes black for a few seconds. I don't have a
> specific ETA, but I can help you raise a follow-up ticket if the issue has gotten worse.

---

### Scenario 3 — Ticket Creation (Multi-turn, State/Memory)

**User:** I have a VPN issue.

**Assistant:**
> I can help with that. Could you share your employee ID so I can look into this for you?

**User:** EMP1024.

*(no tool called yet — the agent still needs a category/description before it can act; state
now remembers `employee_id = EMP1024` from this turn for the rest of the conversation)*

**Assistant:**
> Thanks — I have your employee ID on file. Could you briefly describe the VPN issue you're
> experiencing (e.g. connection failing, password not working)?

**User:** My VPN is not working, it just times out when I try to connect. Please raise a ticket.

**🔧 Tool used:** `create_ticket` → `{"employee_id": "EMP1024", "category": "VPN", "description": "VPN connection times out when attempting to connect."}`
**Tool result:** `{"created": true, "ticket": {"ticket_id": "TCK-7231", "status": "Open", ...}}`

**Assistant:**
> I've created ticket **TCK-7231** for you under the VPN category, status **Open**, describing
> a connection timeout when connecting. IT will follow up shortly. Is there anything else I can
> help with?

---

### Scenario 4 — Duplicate Prevention

**User:** I have another hardware problem, employee ID EMP1003, my laptop battery is bad.

**🔧 Tool used:** `create_ticket` → duplicate detected (`TCK-1005`, same employee/category, status "In Progress")

**Assistant:**
> It looks like you already have an open Hardware ticket (**TCK-1005**) covering a similar
> battery issue that's currently In Progress. Would you like me to create a separate new ticket
> anyway, or should we let the existing one be updated instead?

---

### Scenario 5 — New Employee Onboarding (register_employee)

**User:** I'm a new employee, I don't have an ID in the system yet.

**Assistant:**
> No problem — I can get you registered. Could you share your first name, last name, and
> department/role?

**User:** Vikram Rao, Operations.

**🔧 Tool used:** `register_employee` → `{"first_name": "Vikram", "last_name": "Rao", "department": "Operations"}`
**Tool result:** `{"registered": true, "employee": {"employee_id": "EMP7421", "name": "Vikram Rao", "email": "vikram_rao@xyz.com", "department": "Operations"}}`

**Assistant:**
> You're all set — you're registered as **EMP7421** in the Operations department, with company
> email **vikram_rao@xyz.com**. How can I help you today?

Notice the assistant never asked for an email address or employee ID — both were generated
automatically by the system: the email follows the `firstname_lastname@xyz.com` format, and the
employee ID is a fresh, collision-checked `EMP####` value.

**User:** My laptop won't turn on, please raise a ticket.

**🔧 Tool used:** `create_ticket` → `{"employee_id": "EMP7421", "category": "Hardware", "description": "Laptop won't turn on."}`
**Tool result:** `{"created": true, "ticket": {"ticket_id": "TCK-4402", "status": "Open", ...}}`

**Assistant:**
> I've created ticket **TCK-4402** for you under Hardware, status **Open**. IT will reach out
> shortly. Notice the agent didn't ask for your employee ID again — it remembered EMP7421 from
> earlier in this conversation.

---

### Scenario 5b — Registering a Second Employee with the Same Name

Business rule: any number of employees can share the same first and last name. Registration
never blocks on this — each call always creates a new employee, with the **email** disambiguated
by an incrementing numeric suffix.

**User:** I'm a new employee too — Vikram Rao, Finance department.

**🔧 Tool used:** `register_employee` → `{"first_name": "Vikram", "last_name": "Rao", "department": "Finance"}`
**Tool result:** `{"registered": true, "employee": {"employee_id": "EMP2290", "name": "Vikram Rao", "email": "vikram_rao1@xyz.com", "department": "Finance"}}`

**Assistant:**
> You're all set — you're registered as **EMP2290** in the Finance department, with company
> email **vikram_rao1@xyz.com**. How can I help you today?

Note the email automatically became `vikram_rao1@xyz.com` (not a duplicate of the earlier
`vikram_rao@xyz.com`), and this second "Vikram Rao" got a completely independent employee ID —
`EMP2290`, distinct from `EMP7421`. A third registration under the same name would become
`vikram_rao2@xyz.com`, and so on.

---

### Scenario 6 — Not Found / Hallucination Avoidance

**User:** What's the status of ticket TCK-9999?

**🔧 Tool used:** `ticket_lookup` → `{"ticket_id": "TCK-9999"}` → not found

**Assistant:**
> I couldn't find any ticket with ID TCK-9999 in the system. Could you double-check the ticket
> number, or would you like me to look up tickets under your employee ID instead?
