from __future__ import annotations

import os

from dotenv import load_dotenv


# A local .env keeps development credentials available across terminal sessions.
# Explicit process environment variables take precedence over .env values.
load_dotenv()


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/character_companion"
)


def get_database_url() -> str:
    """Return the configured SQLAlchemy database URL."""

    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
