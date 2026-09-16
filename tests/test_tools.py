"""Smoke tests for the three agent tools, run directly against the seeded
local data (no LLM/API key required). Run with:

    python -m tests.test_tools

or, if pytest is installed:

    pytest tests/test_tools.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import db
from src.tools import create_ticket, knowledge_search, register_employee, ticket_lookup


def test_knowledge_search_found():
    result = knowledge_search.invoke({"query": "How do I reset my VPN password?"})
    assert result["found"] is True
    assert result["article_id"] == "KB-001"


def test_knowledge_search_not_found():
    result = knowledge_search.invoke({"query": "asdkjqwoieuqweqwe nonsense query"})
    assert result["found"] is False


def test_ticket_lookup_by_ticket_id():
    result = ticket_lookup.invoke({"ticket_id": "TCK-1001"})
    assert result["found"] is True
    assert result["tickets"][0]["employee_id"] == "EMP1003"


def test_ticket_lookup_by_employee():
    result = ticket_lookup.invoke({"employee_id": "EMP1003"})
    assert result["found"] is True
    assert result["count"] >= 2


def test_ticket_lookup_no_match():
    result = ticket_lookup.invoke({"ticket_id": "TCK-9999"})
    assert result["found"] is False


def test_create_ticket_unknown_employee():
    result = create_ticket.invoke(
        {"employee_id": "EMP9999", "category": "VPN", "description": "test"}
    )
    assert result["created"] is False
    assert "error" in result


def test_create_ticket_duplicate_detection():
    # EMP1003 already has open Hardware tickets seeded.
    result = create_ticket.invoke(
        {
            "employee_id": "EMP1003",
            "category": "Hardware",
            "description": "Another hardware complaint",
        }
    )
    assert result["created"] is False
    assert result.get("duplicate") is True


def test_create_ticket_success():
    result = create_ticket.invoke(
        {
            "employee_id": "EMP1004",
            "category": "Software",
            "description": "Need MS Project installed for a new initiative.",
        }
    )
    assert result["created"] is True
    assert result["ticket"]["ticket_id"].startswith("TCK-")

    # Verify it is retrievable via lookup.
    lookup = ticket_lookup.invoke({"ticket_id": result["ticket"]["ticket_id"]})
    assert lookup["found"] is True


def test_register_employee_success():
    result = register_employee.invoke(
        {"first_name": "Test", "last_name": "Newperson", "department": "Engineering"}
    )
    assert result["registered"] is True
    employee = result["employee"]
    new_id = employee["employee_id"]
    assert new_id.startswith("EMP")
    # Email must be auto-generated as firstname_lastname@<domain>, never supplied by the caller.
    assert employee["email"] == "test_newperson@xyz.com"

    # The new employee should now be usable for ticket creation.
    ticket = create_ticket.invoke(
        {"employee_id": new_id, "category": "Software", "description": "Need IDE license activated."}
    )
    assert ticket["created"] is True


def test_register_employee_same_name_gets_incrementing_email():
    # Business rule: multiple employees can share the same first + last name.
    # Each registration must still succeed, with a unique, incrementing email.
    first = register_employee.invoke(
        {"first_name": "Dup", "last_name": "Person", "department": "Sales"}
    )
    assert first["registered"] is True
    assert first["employee"]["email"] == "dup_person@xyz.com"

    second = register_employee.invoke(
        {"first_name": "Dup", "last_name": "Person", "department": "Marketing"}
    )
    assert second["registered"] is True
    assert second["employee"]["email"] == "dup_person1@xyz.com"
    # Distinct employee_id even though the name is identical.
    assert second["employee"]["employee_id"] != first["employee"]["employee_id"]

    third = register_employee.invoke(
        {"first_name": "Dup", "last_name": "Person", "department": "Engineering"}
    )
    assert third["registered"] is True
    assert third["employee"]["email"] == "dup_person2@xyz.com"


def test_register_employee_missing_fields():
    result = register_employee.invoke({"first_name": "", "last_name": "", "department": ""})
    assert result["registered"] is False


if __name__ == "__main__":
    db.init_db()
    tests = [
        test_knowledge_search_found,
        test_knowledge_search_not_found,
        test_ticket_lookup_by_ticket_id,
        test_ticket_lookup_by_employee,
        test_ticket_lookup_no_match,
        test_create_ticket_unknown_employee,
        test_create_ticket_duplicate_detection,
        test_create_ticket_success,
        test_register_employee_success,
        test_register_employee_same_name_gets_incrementing_email,
        test_register_employee_missing_fields,
    ]
    for t in tests:
        t()
        print(f"PASSED: {t.__name__}")
    print("\nAll smoke tests passed.")
