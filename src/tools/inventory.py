"""Inventory database tools: stock checks, fuzzy item matching, price reference."""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Tuple

from src.tools.db import get_connection


def normalize_item_name(name: str) -> str:
    """Normalize for exact/space-insensitive matching."""
    cleaned = re.sub(r'\s*\(.*?\)', '', name)
    return re.sub(r'[^a-z0-9]', '', cleaned.lower())


def normalize_item_name_ocr(name: str) -> str:
    """Normalize with OCR corrections for fuzzy matching.
    Treats common OCR swaps: 1↔i/l, 0↔o in product names (e.g. w1dgetb → widgetb).
    """
    norm = normalize_item_name(name)
    # In product names: 1 is often i or l; 0 is often o
    norm = norm.replace("1", "i").replace("0", "o")
    return norm


def lookup_item(item_name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[dict]:
    """Exact lookup by item name."""
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute("SELECT * FROM inventory WHERE item = ?", (item_name,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        if conn is None:
            _conn.close()


def fuzzy_lookup_item(
    item_name: str, conn: Optional[sqlite3.Connection] = None, threshold: float = 0.9
) -> Tuple[Optional[dict], float]:
    """Fuzzy match: normalize first, then SequenceMatcher fallback. Returns (item_row, confidence)."""
    _conn = conn or get_connection()
    try:
        exact = lookup_item(item_name, _conn)
        if exact:
            return exact, 1.0

        cursor = _conn.execute("SELECT item FROM inventory")
        all_items = [row["item"] for row in cursor.fetchall()]

        norm_input = normalize_item_name(item_name)
        norm_input_ocr = normalize_item_name_ocr(item_name)
        for db_item in all_items:
            if normalize_item_name(db_item) == norm_input:
                row = lookup_item(db_item, _conn)
                return row, 0.95
            if normalize_item_name_ocr(db_item) == norm_input_ocr:
                row = lookup_item(db_item, _conn)
                return row, 0.92  # OCR match, slightly lower than exact

        best_match = None
        best_score = 0.0
        for db_item in all_items:
            norm_db = normalize_item_name(db_item)
            norm_db_ocr = normalize_item_name_ocr(db_item)
            score = difflib.SequenceMatcher(None, norm_input, norm_db).ratio()
            score_ocr = difflib.SequenceMatcher(None, norm_input_ocr, norm_db_ocr).ratio()
            score = max(score, score_ocr)
            if score > best_score:
                best_score = score
                best_match = db_item

        if best_match and best_score >= threshold:
            row = lookup_item(best_match, _conn)
            return row, round(best_score, 3)

        return None, 0.0
    finally:
        if conn is None:
            _conn.close()


def check_stock(item_name: str, quantity: float, conn: Optional[sqlite3.Connection] = None) -> dict:
    """Check if requested quantity is available. Uses fuzzy matching."""
    row, confidence = fuzzy_lookup_item(item_name, conn)

    if row is None:
        return {
            "found": False,
            "item": item_name,
            "matched_item": None,
            "confidence": 0.0,
            "issue": "unknown_item",
            "detail": f"Item '{item_name}' not found in inventory",
        }

    result = {
        "found": True,
        "item": item_name,
        "matched_item": row["item"],
        "confidence": confidence,
        "stock": row["stock"],
        "requested": quantity,
        "unit_price": row["unit_price"],
        "price_tolerance": row["price_tolerance"],
    }

    if row["stock"] == 0:
        result["issue"] = "zero_stock"
        result["detail"] = f"Item '{row['item']}' has zero stock"
    elif quantity < 0:
        result["issue"] = "negative_qty"
        result["detail"] = f"Negative quantity ({quantity}) for '{row['item']}'"
    elif quantity > row["stock"]:
        result["issue"] = "stock_exceeded"
        result["detail"] = f"Requested {quantity} of '{row['item']}', only {row['stock']} in stock"
    else:
        result["issue"] = None
        result["detail"] = f"OK: {quantity} of '{row['item']}' available ({row['stock']} in stock)"

    return result


def check_price_anomaly(
    item_name: str, unit_price: float, currency: str = "USD",
    conn: Optional[sqlite3.Connection] = None,
    exchange_rate: float = 1.0,
) -> Optional[dict]:
    """Check if the unit price deviates from reference. Returns flag dict or None."""
    row, _ = fuzzy_lookup_item(item_name, conn)
    if row is None or row["unit_price"] == 0:
        return None

    price_usd = unit_price * exchange_rate
    ref_price = row["unit_price"]
    tolerance = row["price_tolerance"]

    if tolerance <= 0:
        return None

    deviation = abs(price_usd - ref_price) / ref_price
    if deviation > tolerance:
        return {
            "item": row["item"],
            "unit_price": unit_price,
            "unit_price_usd": round(price_usd, 2),
            "reference_price": ref_price,
            "deviation": round(deviation, 3),
            "tolerance": tolerance,
            "detail": f"Price ${price_usd:.2f} deviates {deviation:.0%} from reference ${ref_price:.2f} (tolerance: {tolerance:.0%})",
        }
    return None


def get_all_inventory(conn: Optional[sqlite3.Connection] = None) -> List[dict]:
    _conn = conn or get_connection()
    try:
        cursor = _conn.execute("SELECT * FROM inventory")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        if conn is None:
            _conn.close()
