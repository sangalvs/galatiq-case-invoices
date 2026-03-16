"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from setup_db import init_db


@pytest.fixture
def db_conn():
    """In-memory database with standard seed data."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def data_dir():
    return Path(__file__).parent.parent / "data" / "invoices"
