"""Database tools: processed invoices, audit log, exchange rates."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from src.config import DB_PATH, EXCHANGE_RATES_FALLBACK
from src.models import ProcessingLogEntry


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path or DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_exchange_rate(currency: str, conn: Optional[sqlite3.Connection] = None) -> float:
    """Get exchange rate to USD. Falls back to config if not in DB."""
    if currency == "USD":
        return 1.0
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute(
            "SELECT rate_to_usd FROM exchange_rates WHERE currency = ?", (currency,)
        )
        row = cursor.fetchone()
        if row:
            return row["rate_to_usd"]
        return EXCHANGE_RATES_FALLBACK.get(currency, 1.0)
    finally:
        if conn is None:
            _conn.close()


def get_known_currencies(conn: Optional[sqlite3.Connection] = None) -> set:
    """Return set of currency codes we have a rate for (DB + config fallback)."""
    known = set(EXCHANGE_RATES_FALLBACK.keys())
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute("SELECT currency FROM exchange_rates")
        for row in cursor.fetchall():
            known.add(row["currency"])
        return known
    finally:
        if conn is None:
            _conn.close()


def convert_to_usd(amount: float, currency: str, conn: Optional[sqlite3.Connection] = None) -> float:
    rate = get_exchange_rate(currency, conn)
    return round(amount * rate, 2)


def record_processed_invoice(
    invoice_number: str,
    vendor: str,
    total_amount: float,
    currency: str,
    total_amount_usd: float,
    status: str,
    fraud_risk_level: str,
    fraud_risk_score: int,
    file_path: str = "",
    revision: Optional[str] = None,
    rejection_reason: Optional[str] = None,
    processing_time_ms: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute(
            """INSERT INTO processed_invoices
            (invoice_number, revision, file_path, vendor, total_amount, currency,
             total_amount_usd, status, fraud_risk_level, fraud_risk_score,
             rejection_reason, processed_at, processing_time_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                invoice_number, revision, file_path, vendor, total_amount, currency,
                total_amount_usd, status, fraud_risk_level, fraud_risk_score,
                rejection_reason, datetime.now().isoformat(), processing_time_ms,
            ),
        )
        _conn.commit()
        return cursor.lastrowid
    finally:
        if conn is None:
            _conn.close()


def check_duplicate_invoice(
    invoice_number: str, conn: Optional[sqlite3.Connection] = None
) -> Optional[dict]:
    """Check if invoice was already processed. Returns the previous record or None."""
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute(
            "SELECT * FROM processed_invoices WHERE invoice_number = ? ORDER BY processed_at DESC LIMIT 1",
            (invoice_number,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if conn is None:
            _conn.close()


def is_first_time_vendor(vendor: str, conn: Optional[sqlite3.Connection] = None) -> bool:
    """Check if we've seen this vendor before in processed invoices."""
    if not vendor:
        return True
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute(
            "SELECT COUNT(*) as cnt FROM processed_invoices WHERE vendor = ?", (vendor,)
        )
        return cursor.fetchone()["cnt"] == 0
    finally:
        if conn is None:
            _conn.close()


def write_log_entry(entry: ProcessingLogEntry, conn: Optional[sqlite3.Connection] = None) -> None:
    _conn = conn or get_connection()
    try:
        _conn.execute(
            """INSERT INTO processing_log (invoice_number, stage, action, result, details, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (entry.invoice_number, entry.stage, entry.action, entry.result,
             entry.details, entry.timestamp),
        )
        _conn.commit()
    finally:
        if conn is None:
            _conn.close()


def get_processing_log(
    invoice_number: Optional[str] = None, conn: Optional[sqlite3.Connection] = None
) -> List[dict]:
    _conn = conn or get_connection()
    try:
        if invoice_number:
            cursor = _conn.execute(
                "SELECT * FROM processing_log WHERE invoice_number = ? ORDER BY timestamp",
                (invoice_number,),
            )
        else:
            cursor = _conn.execute("SELECT * FROM processing_log ORDER BY timestamp")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if conn is None:
            _conn.close()


def get_all_processed_invoices(conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute("SELECT * FROM processed_invoices ORDER BY processed_at DESC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if conn is None:
            _conn.close()


def get_batch_analytics(conn: Optional[sqlite3.Connection] = None) -> dict:
    _conn = conn or get_connection()
    try:
        all_inv = get_all_processed_invoices(_conn)
        total = len(all_inv)
        if total == 0:
            return {"total": 0}

        approved = sum(1 for i in all_inv if i["status"] == "approved")
        rejected = sum(1 for i in all_inv if i["status"] == "rejected")
        flagged = sum(1 for i in all_inv if i["status"] == "flagged")
        total_value = sum(i["total_amount_usd"] or 0 for i in all_inv)

        fraud_levels = {}
        for i in all_inv:
            level = i.get("fraud_risk_level", "unknown")
            fraud_levels[level] = fraud_levels.get(level, 0) + 1

        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "flagged": flagged,
            "total_value_usd": round(total_value, 2),
            "fraud_levels": fraud_levels,
            "invoices": all_inv,
        }
    finally:
        if conn is None:
            _conn.close()
