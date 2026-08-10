from __future__ import annotations

import os


DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/character_companion"
)


def get_database_url() -> str:
    """Return the configured SQLAlchemy database URL."""

    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
