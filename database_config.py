"""Shared PostgreSQL configuration for the processor and FastAPI service."""

import os
from pathlib import Path


def load_local_environment():
    """Load simple KEY=VALUE entries without replacing deployed env variables."""
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip("\"'")
        if name:
            os.environ.setdefault(name, value)


# Process environment values (for deployment) take precedence over .env.
load_local_environment()


def get_database_config():
    """Return psycopg2 connection settings, failing clearly if any are missing."""
    names = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    values = {name: os.getenv(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing database environment variables: " + ", ".join(missing)
        )

    try:
        port = int(values["DB_PORT"])
    except ValueError as error:
        raise RuntimeError("DB_PORT must be a number") from error

    return {
        "host": values["DB_HOST"],
        "port": port,
        "database": values["DB_NAME"],
        "user": values["DB_USER"],
        "password": values["DB_PASSWORD"],
    }
