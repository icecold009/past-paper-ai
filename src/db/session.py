from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine


def get_database_url(database_url: str | None = None) -> str:
    load_dotenv()
    value = (database_url or os.getenv("DATABASE_URL", "")).strip()
    if not value:
        raise RuntimeError("DATABASE_URL is missing. Add it to .env before using the database.")
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    return value


def create_db_engine(database_url: str | None = None, **kwargs: object) -> Engine:
    return create_engine(get_database_url(database_url), **kwargs)
