"""Centralized configuration loading for the AI IT Support Assistant.

All environment-dependent values (API keys, model name, file paths) are
resolved here so the rest of the application never hard-codes them.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file in the project root, if present.
load_dotenv()

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

EMPLOYEES_JSON = DATA_DIR / "employees.json"
KNOWLEDGE_BASE_JSON = DATA_DIR / "knowledge_base.json"
SEED_TICKETS_JSON = DATA_DIR / "seed_tickets.json"
DB_PATH = DATA_DIR / "it_support.db"

# Separate SQLite file holding LangGraph's conversation checkpoints (message
# history + agent state per thread_id), so chats survive an app restart.
CHECKPOINT_DB_PATH = DATA_DIR / "checkpoints.db"

# --- LLM configuration -------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# --- Company email domain -----------------------------------------------------
# New employee emails are auto-generated as firstname_lastname@<EMAIL_DOMAIN>
# by the system -- never typed or invented by the user or the LLM.
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "xyz.com")


def require_api_key() -> None:
    """Raise a clear error early if no API key is configured."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your "
            "OpenAI API key before running the application."
        )
