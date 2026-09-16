"""The four tools available to the IT Support Agent.

Each tool is decorated with LangChain's @tool so it can be bound directly
to the LLM and executed by a LangGraph ToolNode. Every tool:
  - Has a Pydantic input schema (structured, validated arguments).
  - Wraps its logic in try/except so a failure returns a structured
    error dict instead of raising (the graph should never crash on a
    bad tool call).
  - Returns plain, LLM-readable dict/string output only -- no exceptions
    leak to the caller.
"""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

import re

from src import db
from src.config import EMAIL_DOMAIN, KNOWLEDGE_BASE_JSON
from src.logging_config import logger


# --- Tool 1: Knowledge Search -------------------------------------------------

class KnowledgeSearchInput(BaseModel):
    query: str = Field(description="The employee's question or issue, in natural language.")


def _load_knowledge_base() -> list[dict]:
    with open(KNOWLEDGE_BASE_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def _score_article(article: dict, query_terms: set[str]) -> int:
    haystack = set(article["keywords"]) | set(article["title"].lower().split())
    return len(query_terms & {h.lower() for h in haystack})


@tool("knowledge_search", args_schema=KnowledgeSearchInput)
def knowledge_search(query: str) -> dict:
    """Search the local IT knowledge base for an article relevant to the user's question.

    Use this when the employee is asking how to do something or reporting a
    general issue (e.g. VPN password reset, printer setup, Wi-Fi problems)
    rather than asking about a specific existing ticket.
    """
    try:
        articles = _load_knowledge_base()
        query_terms = {w.strip(".,?!").lower() for w in query.split()}

        scored = [
            (a, _score_article(a, query_terms))
            for a in articles
        ]
        scored = [pair for pair in scored if pair[1] > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)

        if not scored:
            logger.info("Knowledge search for %r found no match", query)
            return {
                "found": False,
                "message": "No matching knowledge base article was found for this query.",
            }

        best_article, score = scored[0]
        logger.info("Knowledge search for %r matched %s (score=%d)", query, best_article["id"], score)
        return {
            "found": True,
            "article_id": best_article["id"],
            "title": best_article["title"],
            "category": best_article["category"],
            "content": best_article["content"],
        }
    except Exception as exc:  # noqa: BLE001 - deliberately broad, tool must not crash the graph
        logger.exception("knowledge_search failed")
        return {"found": False, "error": f"Knowledge search failed: {exc}"}


# --- Tool 2: Ticket Lookup -----------------------------------------------------

class TicketLookupInput(BaseModel):
    employee_id: Optional[str] = Field(
        default=None, description="The employee ID to filter tickets by, e.g. 'EMP1024'."
    )
    ticket_id: Optional[str] = Field(
        default=None, description="A specific ticket ID to look up, e.g. 'TCK-1001'."
    )
    keyword: Optional[str] = Field(
        default=None,
        description="A keyword describing the issue (e.g. 'laptop', 'vpn') to filter tickets by.",
    )


@tool("ticket_lookup", args_schema=TicketLookupInput)
def ticket_lookup(
    employee_id: Optional[str] = None,
    ticket_id: Optional[str] = None,
    keyword: Optional[str] = None,
) -> dict:
    """Look up existing support tickets by employee ID, ticket ID, and/or keyword.

    Use this when the employee is asking about the status of an existing
    issue or ticket. At least one of employee_id, ticket_id or keyword
    should be provided; if the employee ID is unknown, ask the user for it
    before calling this tool with only a keyword, as results could be
    ambiguous otherwise.
    """
    try:
        if not any([employee_id, ticket_id, keyword]):
            return {
                "found": False,
                "message": "No search criteria provided. Please supply an employee ID, ticket ID, or keyword.",
            }

        results = db.find_tickets(employee_id=employee_id, ticket_id=ticket_id, keyword=keyword)
        logger.info(
            "Ticket lookup (employee_id=%s, ticket_id=%s, keyword=%s) -> %d result(s)",
            employee_id, ticket_id, keyword, len(results),
        )

        if not results:
            return {"found": False, "message": "No tickets matched the given criteria."}

        return {"found": True, "count": len(results), "tickets": results}
    except Exception as exc:  # noqa: BLE001
        logger.exception("ticket_lookup failed")
        return {"found": False, "error": f"Ticket lookup failed: {exc}"}


# --- Tool 3: Ticket Creation ---------------------------------------------------

VALID_CATEGORIES = {"VPN", "Hardware", "Software", "Network", "Account", "Email", "Other"}

# Case-insensitive lookup so normalization matches regardless of how the LLM
# capitalized the category (e.g. "vpn", "Vpn", "VPN" all resolve to "VPN").
# A plain `.title()` comparison would silently mis-normalize "VPN" to "Vpn",
# which isn't in VALID_CATEGORIES, and fall back to "Other" incorrectly.
_VALID_CATEGORIES_BY_UPPER = {c.upper(): c for c in VALID_CATEGORIES}


def _normalize_category(category: str) -> str:
    return _VALID_CATEGORIES_BY_UPPER.get(category.strip().upper(), "Other")


class CreateTicketInput(BaseModel):
    employee_id: str = Field(description="The employee ID raising the ticket, e.g. 'EMP1024'.")
    category: str = Field(
        description=(
            "The issue category. Must be one of: VPN, Hardware, Software, Network, Account, "
            "Email, Other."
        )
    )
    description: str = Field(
        description="A clear description of the issue, based only on what the employee actually said."
    )


@tool("create_ticket", args_schema=CreateTicketInput)
def create_ticket(employee_id: str, category: str, description: str) -> dict:
    """Create a new IT support ticket.

    Only call this once employee_id, category and a concrete description
    are all known -- do not guess or invent any of these fields. This tool
    validates the employee exists and checks for a likely duplicate open
    ticket in the same category before creating a new one.
    """
    try:
        employee_id = employee_id.strip().upper()
        category = _normalize_category(category)

        if not description or not description.strip():
            return {"created": False, "error": "A ticket description is required."}

        employee = db.get_employee(employee_id)
        if not employee:
            logger.info("create_ticket rejected: unknown employee_id %s", employee_id)
            return {
                "created": False,
                "error": f"Employee ID '{employee_id}' was not found in the employee directory.",
            }

        duplicate = db.find_open_ticket_for_duplicate_check(employee_id, category)
        if duplicate:
            logger.info("create_ticket found likely duplicate %s", duplicate["ticket_id"])
            return {
                "created": False,
                "duplicate": True,
                "existing_ticket": duplicate,
                "message": (
                    f"An existing open ticket ({duplicate['ticket_id']}) for the same category "
                    "already exists. Confirm with the user before creating a new one."
                ),
            }

        ticket = db.create_ticket(employee_id, category, description.strip())
        return {"created": True, "ticket": ticket}
    except Exception as exc:  # noqa: BLE001
        logger.exception("create_ticket failed")
        return {"created": False, "error": f"Ticket creation failed: {exc}"}


# --- Tool 4: Employee Registration --------------------------------------------

class RegisterEmployeeInput(BaseModel):
    first_name: str = Field(description="The employee's first name, exactly as given by the user.")
    last_name: str = Field(description="The employee's last name, exactly as given by the user.")
    department: str = Field(
        description=(
            "The employee's department/role (e.g. Engineering, Sales, Finance, HR, Operations)."
        )
    )


def _slugify_name_part(part: str) -> str:
    """Lowercase and strip anything that isn't a letter/digit, for email generation."""
    return re.sub(r"[^a-z0-9]", "", part.strip().lower())


def _build_email_local_prefix(first_name: str, last_name: str) -> str:
    """Build the 'firstname_lastname' portion of the company email (no domain, no suffix)."""
    first = _slugify_name_part(first_name) or "user"
    last = _slugify_name_part(last_name) or "employee"
    return f"{first}_{last}"


@tool("register_employee", args_schema=RegisterEmployeeInput)
def register_employee(first_name: str, last_name: str, department: str) -> dict:
    """Register a brand-new employee. Always creates a new employee record.

    Use this when the user identifies themselves as a new/unknown employee
    (e.g. ticket_lookup or create_ticket reported that their employee_id
    was not found, or they explicitly say they are new). Only call this
    once you have all three of first_name, last_name and department/role --
    do not guess or invent any of them; ask the user directly for whichever
    is missing. Do NOT ask the user for an email address or employee ID --
    both are generated automatically by the system.

    Multiple employees are allowed to share the same first and last name --
    this is expected and NOT an error. Each call to this tool always creates
    a brand-new employee record with its own fresh EMP#### employee_id. The
    email follows the company format firstname_lastname@company-domain for
    the first person with that name; if that name is already used, the
    system automatically appends the next number (firstname_lastname1@...,
    firstname_lastname2@..., and so on) so every employee still gets a
    unique email -- you never need to check for this or ask the user
    anything about it. After this tool succeeds, use the returned
    employee_id for any subsequent ticket_lookup or create_ticket calls in
    this conversation.
    """
    try:
        if not first_name or not first_name.strip():
            return {"registered": False, "error": "Employee first name is required."}
        if not last_name or not last_name.strip():
            return {"registered": False, "error": "Employee last name is required."}
        if not department or not department.strip():
            return {"registered": False, "error": "Department/role is required."}

        full_name = f"{first_name.strip().title()} {last_name.strip().title()}"
        local_prefix = _build_email_local_prefix(first_name, last_name)
        email = db.generate_unique_employee_email(local_prefix)

        employee = db.create_employee(full_name, email, department)
        return {"registered": True, "employee": employee}
    except Exception as exc:  # noqa: BLE001
        logger.exception("register_employee failed")
        return {"registered": False, "error": f"Employee registration failed: {exc}"}


ALL_TOOLS = [knowledge_search, ticket_lookup, create_ticket, register_employee]
