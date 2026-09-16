# 🧞 SupportGenie — Agentic AI IT Support Assistant with LangGraph

> SupportGenie is an agentic AI assistant that helps employees resolve common IT
> issues — searching a local knowledge base, checking existing ticket status,
> raising new tickets, and onboarding new employees — all through a single
> LangGraph-orchestrated conversational agent with persistent memory,
> tool-calling, and conditional routing.

> **Final Capstone Project 3** — GenAI Development Program (IIT Patna / USDC)
> Focus: Agents · Tool Calling · LangGraph · State · Conditional Workflows

## 1. Problem Statement

Employees at a fictional organization repeatedly raise the same categories of IT
questions — "How do I reset my VPN password?", "What's the status of my ticket?",
"My VPN isn't working, please log an issue." Today this requires a human IT agent
to manually search a knowledge base, look up a ticketing system, and file new
tickets. This project builds an **agentic AI assistant** that can understand the
employee's request, decide on its own which of several tools it needs, execute
the right one (or ask a clarifying question first), and return a grounded,
human-friendly response — without hallucinating ticket data or acting on
incomplete information.

## 2. Solution Overview

The assistant is built as a **LangGraph** state graph with a single LLM-driven
`agent` node bound to four tools, and a `tools` node that executes whichever
tool the LLM selects. Conditional routing decides, turn by turn, whether the
LLM's response requires a tool call or is already a final answer (e.g. a
clarifying question). A `SqliteSaver` checkpointer (backed by
`data/checkpoints.db`) persists the full conversation state per chat, so the
agent remembers information like the employee ID across multiple turns —
and that memory survives closing and restarting the app, not just page
refreshes.

The four tools operate over **local data only** — no external services and no
paid infrastructure beyond the OpenAI API used for the LLM's reasoning/tool
selection:

| Tool | Purpose | Backing data |
|---|---|---|
| `knowledge_search` | Answer how-to / general IT questions | `data/knowledge_base.json` |
| `ticket_lookup` | Check status of existing tickets | SQLite `tickets` table |
| `create_ticket` | Raise a new ticket (with validation) | SQLite `tickets` / `employees` tables |
| `register_employee` | Onboard a brand-new employee not yet in the system | SQLite `employees` table |

**New: on-the-fly employee registration.** The seeded `employees.json` is only
a *starting* directory, not a fixed limit. If a user says they're new, or a
ticket lookup/creation reports their employee ID isn't found, the agent asks
**only** for their first name, last name, and department/role — never an
email address or employee ID. Both of those are generated automatically:
the email follows the fixed company format `firstname_lastname@xyz.com`
(configurable via `EMAIL_DOMAIN`), and the employee ID is a fresh,
collision-checked `EMP####` value. `register_employee` then inserts a real
row into `it_support.db`. From that point on, the new employee can look up
or create tickets exactly like any pre-seeded one — entirely through the
chat, with no
manual database editing required.

A Streamlit chat UI wraps the graph, showing the conversation, a "Tool
activity" panel with the exact arguments/results of each tool call, a
**persistent, multi-chat sidebar** (create a new chat, switch between past
ones, or permanently delete one — all backed by SQLite so the list survives
an app restart), and a reset button to start a fresh session.

## 3. Architecture

```
                         ┌─────────────────────────────┐
                         │   Streamlit Chat UI (app.py) │
                         └───────────────┬──────────────┘
                                         │ HumanMessage
                                         ▼
                         ┌─────────────────────────────┐
                         │      LangGraph StateGraph     │
                         │                               │
                         │   START                       │
                         │     │                         │
                         │     ▼                         │
                         │  ┌───────┐  tool_calls?        │
                         │  │ agent │───────────┐         │
                         │  └───┬───┘   yes      │no      │
                         │      │                ▼        │
                         │      │              END        │
                         │      ▼ tool_calls present       │
                         │  ┌────────┐                     │
                         │  │ tools  │  ToolNode:           │
                         │  │        │  knowledge_search    │
                         │  │        │  ticket_lookup        │
                         │  │        │  create_ticket        │
                         │  │        │  register_employee    │
                         │  └───┬────┘                     │
                         │      │ loops back                │
                         │      ▼                            │
                         │   agent  (generates final answer)  │
                         │                                    │
                         │  State persisted via SqliteSaver     │
                         │  (per-chat thread_id, survives       │
                         │   app restarts)                      │
                         └─────────────────────────────────────┘
                                         │
                                         ▼
                         ┌───────────────────────────────────┐
                         │  Local Data                         │
                         │  - data/knowledge_base.json          │
                         │  - data/it_support.db (SQLite)       │
                         │    (employees, tickets, chat history)│
                         │  - data/checkpoints.db (SQLite)      │
                         │    (LangGraph conversation state)    │
                         └───────────────────────────────────┘
```

## 4. Technology Stack

- **Python 3.11+**
- **LangGraph** — agent orchestration (state, nodes, conditional edges, tool execution)
- **LangGraph SqliteSaver** (`langgraph-checkpoint-sqlite`) — persists conversation state to disk so chats survive an app restart
- **LangChain Core / langchain-openai** — `@tool` definitions, `ChatOpenAI` LLM binding
- **OpenAI API** (`gpt-4o-mini` by default) — reasoning / tool selection / response generation
- **SQLite** — employees, tickets, and saved chat history (relational, supports lookups + inserts)
- **JSON** — knowledge base articles, seed data for employees/tickets
- **Pydantic** — structured, validated tool input schemas
- **Streamlit** — chat interface
- **python-dotenv** — environment variable / API key management

## 5. Project Structure

```
Final Capstone Project/
├── app.py                       # Streamlit entrypoint
├── requirements.txt
├── .env.example                 # template for required environment variables
├── .gitignore
├── README.md
├── data/
│   ├── employees.json           # seed employee directory
│   ├── knowledge_base.json      # IT knowledge base articles
│   ├── seed_tickets.json        # sample pre-existing tickets
│   ├── it_support.db            # auto-generated SQLite DB (gitignored, seeded on first run)
│   │                             #   -- also stores saved chat history/titles
│   └── checkpoints.db           # auto-generated LangGraph conversation state (gitignored)
├── src/
│   ├── config.py                 # env/config loading
│   ├── db.py                     # SQLite init/seed + CRUD helpers
│   ├── tools.py                  # the 4 agent tools (Pydantic schemas + logic)
│   ├── state.py                  # LangGraph AgentState definition
│   ├── graph.py                  # LangGraph graph: nodes, conditional edges, system prompt
│   └── logging_config.py         # basic logging setup
├── sample_outputs/
│   └── sample_conversation.md    # example transcript covering all 3 tools + memory
└── tests/
    └── test_tools.py             # smoke tests for all 4 tools (no API key required)
```

## 6. Setup Instructions

```bash
# 1. Clone/enter the project directory
cd "Final Capstone Project"

# 2. (Recommended) create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows (Command Prompt)
# venv\Scripts\Activate.ps1  # Windows (PowerShell)
# source venv/Scripts/activate  # Windows (Git Bash)
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API key
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
# then edit .env and paste your OPENAI_API_KEY
```

### Environment Variables (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ Yes | — | Your OpenAI API key. The app will not run without this. |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Any OpenAI chat model that supports tool calling. |
| `LLM_TEMPERATURE` | No | `0.2` | Lower = more deterministic tool selection. |
| `EMAIL_DOMAIN` | No | `xyz.com` | Domain used to auto-generate new employee emails as `firstname_lastname@<EMAIL_DOMAIN>`. |

The local SQLite database and knowledge base require **no API key** — only the
LLM reasoning step calls OpenAI.

## 7. How to Run

```bash
streamlit run app.py
```

This opens the chat UI in your browser (default: http://localhost:8501). On
first launch, `data/it_support.db` is automatically created and seeded from
`data/employees.json` and `data/seed_tickets.json` — no manual setup needed.

To run the tool-level smoke tests independently of the UI (no API key needed):

```bash
python -m tests.test_tools
```

## 8. Sample Inputs / Outputs

Sample data ships in `data/` (6 employees, 8 knowledge base articles, 5 seeded
tickets across Open/In Progress/Resolved statuses) — but this is a *starting
point*, not a hard limit: new employees registered through the chat are
inserted into the real SQLite database and persist for the rest of the
session. A full sample transcript covering all four tools, conditional
routing, duplicate-ticket prevention, employee onboarding, and multi-turn
memory is in [`sample_outputs/sample_conversation.md`](sample_outputs/sample_conversation.md).
Try, for example:

- *"How do I reset my VPN password?"* → knowledge search
- *"What is the status of ticket TCK-1001?"* → ticket lookup
- *"I have a VPN issue."* → *"EMP1024"* → *"it keeps timing out, please raise a ticket"* → ticket creation, demonstrating state carried across turns
- *"My laptop battery is bad, employee ID EMP1003"* → duplicate-ticket warning (EMP1003 already has an open Hardware ticket)
- *"I'm a new employee, I don't have an ID yet."* → agent asks only for first name/last name/department → `register_employee` auto-generates the email (`firstname_lastname@xyz.com`) and creates a real row in `it_support.db` with a fresh `EMP####` ID → *"My laptop won't turn on, please raise a ticket"* → `create_ticket` self-classifies the category as Hardware and succeeds immediately using that new ID, with no restart or manual setup needed

## 9. Key Design Decisions

- **LangGraph over a single LLM call:** the agent/tools/agent loop with
  conditional edges (`tools_condition`) makes tool selection and multi-step
  workflows explicit and inspectable, rather than hiding everything inside one
  giant prompt.
- **SqliteSaver checkpointer keyed by `thread_id`, persisted to disk:** gives
  the agent real conversation memory (e.g. remembering an employee ID given
  two turns ago) without a custom memory implementation, and — unlike an
  in-memory checkpointer — that memory survives closing and restarting the
  app, not just page refreshes.
- **Multi-chat sidebar backed by SQLite, not `st.session_state` alone:**
  each chat's title and rendered message history live in a `chats` table
  (`src/db.py`), separate from the LangGraph conversation state itself. This
  is what lets chats appear in the sidebar, be switched between, and be
  permanently deleted (`🗑️` button, which also cleans up that chat's
  LangGraph state via `delete_thread_state`) across app restarts.
- **SQLite for tickets/employees, JSON for the knowledge base:** tickets and
  employees are naturally relational (lookups, foreign keys, inserts), while
  the knowledge base is a static, read-only reference collection better suited
  to plain JSON.
- **Validation before action:** `create_ticket` refuses to run unless
  `employee_id` and `description` are present, verifies the employee
  actually exists, and checks for a likely duplicate open ticket before
  creating a new one — the agent is instructed to ask the user rather than
  silently proceed when data is missing or ambiguous.
- **The agent classifies the ticket category itself:** the system prompt
  embeds the exact `VALID_CATEGORIES` allow-list from `tools.py` and
  instructs the LLM to silently infer the best-fitting category from the
  user's description (e.g. "monitor and keyboard not working" → `Hardware`)
  rather than asking the user to pick one — `create_ticket` still normalizes
  anything unrecognized to `"Other"` as a safety net.
- **Employee registration as a first-class tool, not a database hack:**
  onboarding a new employee goes through the same tool-calling, validation,
  and logging path as every other action — `register_employee` only ever
  asks the user for first name, last name, and department/role. The email
  (`firstname_lastname@xyz.com`) and the `employee_id` are always generated
  server-side (in `tools.py`/`db.py`) rather than left to the LLM, so both
  stay consistent, collision-free, and impossible to invent.
- **Multiple employees can share a name — registration always succeeds:**
  rather than rejecting a name that's already in use, `register_employee`
  always creates a new employee and guarantees a unique email by appending
  an incrementing number (`jane_doe@xyz.com`, then `jane_doe1@xyz.com`, then
  `jane_doe2@xyz.com`, ...), computed by counting existing employees whose
  email already matches that pattern (`db.generate_unique_employee_email`).
  Each still gets its own independent, collision-checked `EMP####` ID.
- **Every tool returns a structured dict, never a raw exception:** this keeps
  the graph from crashing on unexpected input and lets the LLM communicate
  failures to the user in natural language.
- **Tool activity panel in the UI:** exposes exactly which tool ran, with what
  arguments and what result, for transparency and easier grading/demoing.

## 10. Limitations

- Chat history and conversation memory are now persisted to local SQLite
  (`data/it_support.db` for titles/rendered history, `data/checkpoints.db`
  for LangGraph's own state) and survive an app restart — but they are still
  single-machine, single-user files with no authentication; anyone with
  access to the machine can open them, and there's no multi-user isolation.
- Deleting a chat is permanent and immediate (no undo/confirmation dialog
  beyond the click itself) — this was a deliberate simplicity trade-off for
  the scope of this project.
- The knowledge base search uses simple keyword/keyword-overlap scoring rather
  than semantic embeddings, which is intentionally lightweight for this scope
  (Project 2 in this program covers full RAG/embeddings).
- Ticket category classification is done by the LLM itself, limited to a
  fixed set of categories (VPN, Hardware, Software, Network, Account, Email,
  Other); anything else falls back to "Other", and an ambiguous description
  could occasionally be classified differently than a human would.
- Employees sharing an identical first and last name are supported (each
  registration always succeeds, with emails disambiguated as
  `firstname_lastname@xyz.com`, `firstname_lastname1@xyz.com`,
  `firstname_lastname2@xyz.com`, ...), but the system has no way to tell
  whether two people with the same name *and* the same suffix-assignment
  order are actually the same physical person re-registering vs. genuinely
  different people — it always treats each `register_employee` call as a
  new hire, by design, per the business rule the assignment scenario calls
  for.
- No real enterprise system integration — all data is local JSON/SQLite,
  per the assignment's scope ("no real enterprise system integration is
  required").
- Requires an OpenAI API key with tool-calling support; it does not run fully
  offline (this can be swapped for a local model via `langchain-ollama` with
  minor changes to `src/graph.py` if needed).
