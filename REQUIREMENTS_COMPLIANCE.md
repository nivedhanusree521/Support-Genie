# Requirements Compliance Report — SupportGenie

**Purpose:** a line-by-line walkthrough of the official "Project 3 – AI Operations
Assistant Using Agentic AI" brief, matched against the actual implementation,
with file/line evidence for every claim. Use this to answer evaluator questions
confidently — every checkmark below points to real, running code, not just a
plan.

**How to verify anything in this document yourself, live, in under a minute:**
```powershell
python -m tests.test_tools     # 11 automated tests, all tool behavior proven
streamlit run app.py           # the actual running application
```

---

## 1. Project Objective

> "Build a basic Agentic AI assistant that can understand a user's request,
> decide which tool is required, execute the appropriate tool and return the
> final response."
>
> "Tool Calling → Agent → State → Routing → Multi-Step Workflow"

**Status: ✅ Fully met.**

| Phrase | Where it lives in the code |
|---|---|
| Tool Calling | `src/tools.py` — 4 tools, each a `@tool`-decorated function with a Pydantic input schema, bound to the LLM via `ChatOpenAI(...).bind_tools(ALL_TOOLS)` (`src/graph.py:127-132`) |
| Agent | `agent_node()` (`src/graph.py:135-143`) — the LLM reasoning step that decides what to do next |
| State | `AgentState` TypedDict (`src/state.py:10-21`) + `SqliteSaver` checkpointer (`src/graph.py:167-174`) |
| Routing | `graph.add_conditional_edges("agent", tools_condition, {...})` (`src/graph.py:153`) |
| Multi-Step Workflow | The `agent → tools → agent → ... → END` loop (`src/graph.py:152-154`); a single user message can pass through the agent node multiple times before a final answer is produced |

**How to demonstrate live:** open the "🔧 Tool activity" expander under any assistant reply — it shows exactly which tool was called, with what arguments, and what it returned, proving the decision → execution → response pipeline for that specific turn.

---

## 2. "Intentionally realistic and achievable on a local machine"

**Status: ✅ Met.**

- No cloud infrastructure, no message queues, no external databases — everything is either a local file (`data/*.json`) or a local SQLite database (`data/it_support.db`, `data/checkpoints.db`).
- The only network call in the entire system is the OpenAI chat-completion API call inside `ChatOpenAI` — everything else (knowledge search, ticket lookup/creation, employee lookup/registration) is 100% local computation.
- Runs with a single command: `streamlit run app.py`.

---

## 3. Suggested Business Scenario — "AI IT Support Assistant"

> "The system will have access to a few local tools/data sources... Employee
> information, IT issue/ticket database, Knowledge base, System status
> information, Ticket creation functionality... The data can be represented
> using simple JSON, CSV or SQLite files. No real enterprise system
> integration is required."

**Status: ✅ Met** (System status information is the one item from the
"for example" list not implemented — see the honest note below).

| Data source required | Implementation | Evidence |
|---|---|---|
| Employee information | SQLite `employees` table | `src/db.py:23-28` (schema), seeded from `data/employees.json` (6 employees) |
| IT issue/ticket database | SQLite `tickets` table | `src/db.py:30-38` (schema), seeded from `data/seed_tickets.json` (5 tickets, mixed Open/In Progress/Resolved statuses) |
| Knowledge base | `data/knowledge_base.json` | 8 articles covering VPN, Hardware, Software, Network, Account, Email topics |
| Ticket creation functionality | `create_ticket` tool + `db.create_ticket()` | `src/tools.py:163-204`, `src/db.py:234-253` |
| System status information | *Not implemented* | The brief lists this as one example among several ("for example: ... System status information...") for the *business scenario*, not as one of the *three required tools* (see §4 below, which explicitly names only three). It was consciously left out to keep the tool set focused and avoid scope creep beyond the three required tools — see the Limitations section of `README.md`. If asked, this is the one honest gap to acknowledge. |

**No real enterprise integration:** confirmed — no calls to any ticketing system, LDAP/AD, ServiceNow, etc. Everything is local JSON + SQLite, exactly as scoped.

---

## 4. Required Tools (minimum 3) — ✅ 4 tools implemented (exceeds requirement)

### Tool 1 — Knowledge Search ✅

> Example: *"How do I reset my VPN password?" → Knowledge Search Tool → Finds relevant article → Generates answer"*

- **Implementation:** `knowledge_search` tool, `src/tools.py:44-81`.
- **Mechanism:** loads `data/knowledge_base.json`, scores every article by keyword/title overlap with the query (`_score_article`, `src/tools.py:39-41`), returns the best match or `found: False` if nothing scores above zero — it never fabricates an answer when no article matches.
- **Live proof:** `tests/test_tools.py:22-25` — asserts the exact query from the brief's own example ("How do I reset my VPN password?") correctly matches article `KB-001`.
- **Demonstration in the UI:** ask exactly this question; the "🔧 Tool activity" panel shows the `knowledge_search` call and its matched article.

### Tool 2 — Ticket Lookup ✅

> Example: *"What is the status of my laptop issue?" → Ticket Lookup Tool → Searches ticket data → Returns ticket status"*

- **Implementation:** `ticket_lookup` tool, `src/tools.py:99-132`.
- **Mechanism:** searches the `tickets` table by any combination of `employee_id`, `ticket_id`, and/or `keyword` (`db.find_tickets`, `src/db.py:196-219`). Requires at least one criterion; returns `found: False` with a clear message otherwise, never guesses.
- **Live proof:** `tests/test_tools.py:33-47` — three tests covering lookup by ticket ID, by employee ID, and the "no match" path.
- **Demonstration in the UI:** ask "What is the status of ticket TCK-1001?" or "What's the status of my laptop issue, employee ID EMP1003?" — matches the brief's own phrasing almost verbatim.

### Tool 3 — Ticket Creation ✅

> Example: *"My VPN is not working. Please raise a ticket." → Collect required information → Create Ticket Tool → Generate ticket ID → Confirm creation"*

- **Implementation:** `create_ticket` tool, `src/tools.py:163-204`.
- **Mechanism, matching each step in the brief's example exactly:**
  1. **Collect required information** — the agent's system prompt (`src/graph.py:96-98`) instructs it to ask for whatever is missing (employee ID, description) before calling the tool; category is classified automatically (see §7).
  2. **Create Ticket Tool** — validates the employee exists (`src/tools.py:179-185`) and checks for a likely duplicate open ticket in the same category first (`src/tools.py:187-198`, using `db.find_open_ticket_for_duplicate_check`).
  3. **Generate ticket ID** — `db.create_ticket()` calls `_generate_ticket_id()` (`src/db.py:256-266`), producing a collision-checked `TCK-XXXX` ID.
  4. **Confirm creation** — the tool returns `{"created": True, "ticket": {...}}`, and the agent reports it back to the user in a structured, labeled format (system prompt formatting rule, `src/graph.py:105-118`).
- **Live proof:** `tests/test_tools.py:50-84` — covers unknown-employee rejection, duplicate detection, and the full success path (create → verify retrievable via lookup).

### Tool 4 — Employee Registration ✅ (beyond the minimum requirement)

- Added because the seeded 6 employees are only a *starting* directory — any real evaluator/demo user needs to be able to onboard themselves as a genuine employee and then use tools 2 and 3 under their own identity, exactly as requested in this conversation.
- `register_employee` tool, `src/tools.py:231-271`. Auto-generates both the `employee_id` (`db._generate_employee_id`, `src/db.py:182-191`) and the company email (`db.generate_unique_employee_email`, `src/db.py:129-155`) — never asks the user for either, and correctly handles multiple employees sharing an identical name (see §8 Safety/Validation for the exact business rule and proof).
- This demonstrates that the "at least three tools" requirement isn't just met at the minimum — the architecture generalizes cleanly to a fourth tool with the same schema/validation/error-handling pattern.

---

## 5. Agent Requirements

> "The agent should be able to: Understand the user's request. Decide whether
> a tool is required. Select the appropriate tool. Pass appropriate
> parameters to the tool. Process the tool response. Generate a final
> user-friendly response."

**Status: ✅ Fully met — this is literally what the LangGraph loop does.**

| Requirement | Mechanism | Evidence |
|---|---|---|
| Understand the request | The LLM reads the full message history + system prompt on every turn | `agent_node()`, `src/graph.py:135-143` |
| Decide whether a tool is required | `tools_condition` inspects whether the LLM's response contains `tool_calls`; if not, the agent can respond directly (e.g. a clarifying question) with no tool at all | `src/graph.py:153` |
| Select the appropriate tool | The LLM chooses from the 4 bound tools based on their docstrings (which double as tool-selection instructions) | `src/tools.py` docstrings, e.g. lines 46-50, 105-111, 165-170, 233-253 |
| Pass appropriate parameters | Each tool has a strict Pydantic schema (`KnowledgeSearchInput`, `TicketLookupInput`, `CreateTicketInput`, `RegisterEmployeeInput`) — the LLM must supply exactly the typed fields, nothing free-form | `src/tools.py:30-31, 86-96, 150-160, 209-216` |
| Process the tool response | `ToolNode` executes the call and appends a `ToolMessage`; the loop-back edge (`tools → agent`) sends control back to the LLM specifically so it can read that result | `src/graph.py:150, 154` |
| Generate a final user-friendly response | The agent node's second pass (after seeing the tool result) produces the natural-language reply — never raw JSON | Demonstrated by the "FORMATTING RULE" in the system prompt, `src/graph.py:105-118`, which turns raw tool JSON into a readable bulleted summary |

---

## 6. LangGraph Requirement

> "Learners should use LangGraph for workflow orchestration. The workflow
> should demonstrate: State, Nodes, Edges, Conditional routing, Tool
> execution, Final response generation."

**Status: ✅ Fully met — LangGraph is used exactly as specified (not CrewAI).**

| Concept | Evidence |
|---|---|
| **State** | `AgentState(TypedDict)` — `src/state.py:10-21` |
| **Nodes** | `graph.add_node("agent", agent_node)` and `graph.add_node("tools", ToolNode(ALL_TOOLS))` — `src/graph.py:149-150` |
| **Edges** | `graph.add_edge(START, "agent")` and `graph.add_edge("tools", "agent")` — `src/graph.py:152, 154` |
| **Conditional routing** | `graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})` — `src/graph.py:153` |
| **Tool execution** | `ToolNode(ALL_TOOLS)` — LangGraph's own prebuilt tool-executor node, `src/graph.py:150` |
| **Final response generation** | The agent node's output once no more tool calls are needed — routed to `END` | `src/graph.py:153` (the `END: END` branch) |

**The brief's suggested architecture diagram, mapped 1:1 to this code:**

```
User Query                              →  st.chat_input() in app.py:153
    ↓
Intent / Decision Node                  →  agent_node() in graph.py:135
    ↓
Conditional Routing                     →  tools_condition, graph.py:153
    ├── Knowledge Search                →  knowledge_search tool
    ├── Ticket Lookup                   →  ticket_lookup tool
    └── Ticket Creation                 →  create_ticket tool
             ↓
        Tool Result                     →  ToolMessage appended by ToolNode
             ↓
      Response Generation               →  agent_node() runs again, reads the ToolMessage
             ↓
        Final Answer                    →  routed to END, rendered in app.py:196
```

**Why LangGraph specifically (not a single LLM call or a manual if/else chain):** the conditional edge genuinely branches at runtime based on the LLM's own decision (tool call vs. no tool call), and the loop-back edge means the same node (`agent`) is visited twice per turn when a tool is used — once to decide, once to summarize. This is a real graph execution, not a linear script.

---

## 7. Memory / State

> Example:
> ```
> User: I have a VPN issue.
> Agent: What is your employee ID?
> User: EMP1024.
> Agent: I found your profile. Would you like me to check existing tickets?
> User: Yes.
> ```
> "The workflow should retain the required information across these interactions."

**Status: ✅ Met, and strengthened further than the brief requires.**

- **Mechanism:** LangGraph's `SqliteSaver` checkpointer persists the entire `AgentState` (the full message history) keyed by a `thread_id`, so every subsequent `graph.invoke()` call for that thread sees everything said before — `src/graph.py:167-174`, wired into the compiled graph at `src/graph.py:180`.
- **How the employee ID example above actually plays out:** the LLM sees the full prior conversation on every turn (`llm_input = [SystemMessage(...), *messages]`, `src/graph.py:141`), so once the user says "EMP1024" it's simply part of the message history the LLM reads back on the next turn — it doesn't need a special-cased memory slot, because the whole transcript is state.
- **Beyond the brief's requirement:** this project's checkpointer is **disk-backed** (`data/checkpoints.db`), not in-memory — so state survives not just "across these interactions" within one session, but across closing and reopening the entire application. This was a deliberate upgrade made during development (see conversation history) specifically because in-memory state alone (the initial `MemorySaver` implementation) was judged insufficient for a realistic deployment.
- **Multi-chat isolation:** each chat in the Streamlit sidebar has its own `thread_id`, so state from one conversation never leaks into another (`app.py:39-42`).

**Live proof of the exact scenario from the brief:** type "I have a VPN issue" → the agent (per the system prompt's rules, `src/graph.py:70-71, 96-98`) asks for your employee ID → give it → say "please raise a ticket" — the agent now has both employee_id (from 2 turns ago) and issue description (from turn 1) and can proceed directly to `create_ticket` without re-asking either.

> **One nuance worth knowing if asked directly:** `AgentState` declares an `employee_id: Optional[str]` field (`src/state.py:21`), but the current nodes never explicitly write to it — state persistence works entirely through the accumulated `messages` list (via LangGraph's `add_messages` reducer), which the LLM re-reads on every turn. The field is a placeholder for a possible future refinement (e.g. extracting `employee_id` into structured state explicitly rather than relying on the LLM to re-find it in the transcript) but isn't currently required, since the message-history approach already satisfies the brief's memory requirement end-to-end.

---

## 8. Safety / Validation Requirements

> "The agent should not blindly execute every action."

**Status: ✅ Every listed bullet is met, with specific code + prompt evidence.**

| Requirement | Implementation | Evidence |
|---|---|---|
| **Validate required information before creating a ticket** | `create_ticket` requires `employee_id` + `description`; rejects if the employee doesn't exist in the DB | `src/tools.py:176-185`; system prompt tells the LLM to ask rather than guess: `src/graph.py:96-98` |
| **Do not create duplicate tickets unnecessarily** | Before inserting, checks for an existing *non-Resolved* ticket in the same category for that employee, and refuses (returning `duplicate: True`) rather than creating a second one silently | `src/tools.py:187-198`, `db.find_open_ticket_for_duplicate_check` (`src/db.py:222-231`); proven in `tests/test_tools.py:58-68` |
| **Clearly communicate when information is missing** | System prompt: *"ask the user a short, direct question for exactly the missing piece instead of guessing or calling the tool"* | `src/graph.py:96-98` |
| **Handle tool failures gracefully** | Every tool wraps its logic in `try/except`, returning a structured `{"error": ...}` dict instead of raising — the graph never crashes on a bad call | e.g. `src/tools.py:79-81, 130-132, 202-204, 269-271`; the whole `app.py` invocation is also wrapped in `try/except` so even an unexpected failure shows a friendly message instead of a stack trace (`app.py:168-215`) |
| **Do not invent ticket information** | System prompt: *"Never invent information. Only state facts that came from a tool result or from what the user explicitly told you."* + the FORMATTING RULE forces the agent to report exact tool-returned fields (Ticket ID, Category, Description, Status) rather than paraphrasing | `src/graph.py:66-69, 105-118` |
| **Clearly distinguish retrieved information from generated recommendations** | System prompt: *"If you are recommending something rather than stating a fact, say so clearly (e.g. 'I'd recommend...')"* | `src/graph.py:68-69` |

**An additional, unrequested safety property implemented during development:** when registering an employee whose name already exists, the agent is explicitly forbidden from silently retrying with altered/padded field values to force a different result — a bug pattern that was caught and fixed during this project's development (see conversation history: the agent once mangled a name to bypass a duplicate check, corrupting a record). The final design instead makes name reuse a *supported, non-error case* — see `db.generate_unique_employee_email` (`src/db.py:129-155`) and the corresponding system prompt rule (`src/graph.py:81-88`) — proven by `tests/test_tools.py:105-126`, which registers "Dup Person" three times and asserts three independent employee IDs and an incrementing email sequence (`dup_person@`, `dup_person1@`, `dup_person2@`).

---

## 9. User Interface

> "A simple Streamlit interface is recommended. The application should
> provide: Chat interface, Conversation history, Clear/reset option,
> Tool/action result visibility where appropriate, Error handling."

**Status: ✅ Fully met, and extended beyond the minimum.**

| Requirement | Implementation | Evidence |
|---|---|---|
| Chat interface | `st.chat_input(...)` / `st.chat_message(...)` | `app.py:153, 138-147, 160-161, 166` |
| Conversation history | Each chat's full turn-by-turn history is rendered on every rerun from persisted storage | `app.py:138-147` |
| Clear/reset option | **Upgraded to a full multi-chat system**: "➕ New Chat" starts a fresh conversation; each saved chat also has a "🗑️" delete button | `app.py:78-80` (new chat), `app.py:100-103` (delete) |
| Tool/action result visibility | "🔧 Tool activity" expander shows the exact tool name, arguments, and raw result for every tool call in a turn | `app.py:141-147, 197-203` |
| Error handling | `st.error(...)` with a friendly message on any exception, both for missing API key and for runtime failures | `app.py:129-135` (missing key), `app.py:208-215` (runtime failure) |

**Beyond the brief's minimum:** a persistent, multi-chat sidebar (chat list survives an app restart, backed by SQLite — `src/db.py:275-326`), sample employee IDs and example prompts in the sidebar to make the UI self-documenting for an evaluator (`app.py:114-124`).

---

## 10. Expected Technical Skills Demonstrated

| Skill | Where demonstrated |
|---|---|
| Python | Entire codebase; `from __future__ import annotations`, type hints throughout |
| LangGraph | `src/graph.py` — full StateGraph usage (§6) |
| Agentic AI | The agent decides its own actions rather than following a fixed script — §1, §5 |
| Tool Calling | 4 `@tool`-decorated functions bound via `bind_tools()` — `src/tools.py`, `src/graph.py:132` |
| Function Calling | Same mechanism — OpenAI's native function-calling API under the hood via `langchain-openai` |
| State Management | `AgentState` + `SqliteSaver` — §7 |
| Conditional Routing | `tools_condition` — §6 |
| Local Data/Database Integration | SQLite (`employees`, `tickets`, `chats` tables) + JSON (`knowledge_base.json`) — `src/db.py` |
| Prompt Engineering | The system prompt in `src/graph.py:38-124` is extensively engineered: explicit tool descriptions, a "CRITICAL RULE" block, category self-classification instructions, and a structured output FORMATTING RULE — each addition made in response to a specific observed failure mode during development (see conversation history) |
| Streamlit | `app.py` — §9 |
| Error Handling | try/except at both the tool layer and the UI layer — §8 |
| Modular Architecture | Clean separation: `app.py` (UI) / `src/graph.py` (orchestration) / `src/state.py` (state shape) / `src/tools.py` (capabilities) / `src/db.py` (persistence) / `src/config.py` (configuration) / `src/logging_config.py` (observability) — see `ARCHITECTURE.md` §3 and §4 for the full breakdown |

**On CrewAI:** the brief allows CrewAI as an alternative to LangGraph. This project uses **LangGraph**, as it more directly and explicitly demonstrates State/Nodes/Edges/Conditional Routing as named, first-class constructs (`StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`) rather than CrewAI's higher-level agent/task/crew abstractions — a more literal match to the brief's own itemized list.

---

## 11. Common Submission Requirements (cross-check)

| Requirement | Status | Where |
|---|---|---|
| Complete Python source code, proper structure, modular, no unnecessary hard-coding, clear names | ✅ | `src/` package; all config in `src/config.py` (API key, model, email domain, all file paths) |
| README.md with architecture, setup, approach, how to run | ✅ | `README.md` — 10 numbered sections covering exactly this |
| Architecture diagram | ✅ | ASCII diagram in `README.md` §3; Mermaid + SVG diagrams in `ARCHITECTURE.md` / `ARCHITECTURE.html` |
| Technology stack | ✅ | `README.md` §4 |
| Sample data | ✅ | `data/employees.json` (6), `data/knowledge_base.json` (8 articles), `data/seed_tickets.json` (5 tickets) — auto-seeded on first run, no manual setup needed |
| Sample outputs | ✅ | `sample_outputs/sample_conversation.md` — full transcripts covering all 4 tools, multi-turn memory, duplicate detection, and same-name registration |
| Environment variable requirements | ✅ | `.env.example` (`OPENAI_API_KEY`, `OPENAI_MODEL`, `LLM_TEMPERATURE`, `EMAIL_DOMAIN`); `.env` gitignored |
| requirements.txt | ✅ | Present, pinned minimum versions including `langgraph-checkpoint-sqlite` |
| No hardcoded secrets committed | ✅ | `.gitignore` excludes `.env` and both generated `.db` files |

---

## 12. Summary Table — Everything at a Glance

| # | Requirement | Status |
|---|---|---|
| 1 | Agentic AI: understand → decide → execute → respond | ✅ |
| 2 | Runs locally, realistic scope | ✅ |
| 3 | Business scenario: employee info, tickets, KB, ticket creation | ✅ (system status omitted by design, see §3) |
| 4 | At least 3 tools | ✅ (4 implemented) |
| 5 | Agent can understand/decide/select/pass params/process/respond | ✅ |
| 6 | LangGraph: State, Nodes, Edges, Conditional Routing, Tool Execution, Response Generation | ✅ |
| 7 | Memory/state retained across turns | ✅ (persisted to disk, exceeding the requirement) |
| 8 | Safety: validation, no duplicates, missing-info handling, error handling, no invented data, facts vs. recommendations | ✅ (all 6 sub-points) |
| 9 | Streamlit UI: chat, history, reset, tool visibility, error handling | ✅ (reset upgraded to full multi-chat + delete) |
| 10 | All 12 listed technical skills | ✅ |
| 11 | Common submission requirements (code, README, sample data, env vars, etc.) | ✅ |

**Overall: every explicit requirement in the brief is met, with the sole honest gap being "System status information," which the brief lists only as one example data source among several for the business scenario — not as one of the three named required tools.**
