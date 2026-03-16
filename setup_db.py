"""Initialize the SQLite database with schema and seed data."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Optional, Union

DB_PATH = Path(__file__).resolve().parent / "inventory.db"


def create_tables(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            item TEXT PRIMARY KEY,
            stock INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            category TEXT,
            price_tolerance REAL DEFAULT 0.20
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT NOT NULL,
            revision TEXT,
            file_path TEXT,
            vendor TEXT,
            total_amount REAL,
            currency TEXT DEFAULT 'USD',
            total_amount_usd REAL,
            status TEXT,
            fraud_risk_level TEXT,
            fraud_risk_score INTEGER,
            rejection_reason TEXT,
            processed_at TEXT,
            processing_time_ms INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT,
            stage TEXT,
            action TEXT,
            result TEXT,
            details TEXT,
            timestamp TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rates (
            currency TEXT PRIMARY KEY,
            rate_to_usd REAL NOT NULL,
            updated_at TEXT
        )
    """)

    conn.commit()


def seed_inventory(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM inventory")
    if cursor.fetchone()[0] > 0:
        return

    cursor.executemany(
        "INSERT INTO inventory (item, stock, unit_price, category, price_tolerance) VALUES (?, ?, ?, ?, ?)",
        [
            ("WidgetA", 15, 250.00, "widget", 0.20),
            ("WidgetB", 10, 500.00, "widget", 0.20),
            ("GadgetX", 5, 750.00, "gadget", 0.20),
            ("FakeItem", 0, 0.00, "unknown", 0.00),
        ],
    )
    conn.commit()


def seed_exchange_rates(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM exchange_rates")
    if cursor.fetchone()[0] > 0:
        return

    cursor.executemany(
        "INSERT INTO exchange_rates (currency, rate_to_usd, updated_at) VALUES (?, ?, datetime('now'))",
        [
            ("USD", 1.00),
            ("EUR", 1.08),
            ("GBP", 1.27),
            ("CAD", 0.74),
            ("JPY", 0.0067),
        ],
    )
    conn.commit()


def init_db(db_path: Optional[Union[Path, str]] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    create_tables(conn)
    seed_inventory(conn)
    seed_exchange_rates(conn)
    return conn


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    conn = init_db(db)
    print(f"Database initialized at {db}")

    cursor = conn.cursor()
    for table in ["inventory", "exchange_rates"]:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        print(f"\n{table} ({len(rows)} rows):")
        for row in rows:
            print(f"  {dict(row)}")

    conn.close()
