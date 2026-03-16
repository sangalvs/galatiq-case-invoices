from __future__ import annotations

import csv
from pathlib import Path

from src.models import Invoice, LineItem


def parse_csv(file_path: Path) -> Invoice:
    with open(file_path, newline="") as f:
        raw_text = f.read()

    with open(file_path, newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return Invoice(invoice_number="UNKNOWN", vendor="", raw_text=raw_text)

    header = [h.strip().lower() for h in rows[0]]

    if _is_field_value_format(header):
        return _parse_field_value(rows, raw_text)
    else:
        return _parse_columnar(rows, header, raw_text)


def _is_field_value_format(header: list[str]) -> bool:
    return header == ["field", "value"]


def _parse_field_value(rows: list[list[str]], raw_text: str) -> Invoice:
    fields: dict[str, str] = {}
    items: list[LineItem] = []
    current_item: dict = {}

    for row in rows[1:]:
        if len(row) < 2:
            continue
        key, value = row[0].strip().lower(), row[1].strip()

        if key == "item":
            if current_item.get("item"):
                items.append(_build_line_item(current_item))
            current_item = {"item": value}
        elif key == "quantity":
            current_item["quantity"] = value
        elif key == "unit_price":
            current_item["unit_price"] = value
        else:
            fields[key] = value

    if current_item.get("item"):
        items.append(_build_line_item(current_item))

    return Invoice(
        invoice_number=fields.get("invoice_number", "UNKNOWN"),
        vendor=fields.get("vendor", ""),
        date=fields.get("date"),
        due_date=fields.get("due_date"),
        line_items=items,
        subtotal=_safe_float(fields.get("subtotal")),
        tax_amount=_safe_float(fields.get("tax")),
        total=_safe_float(fields.get("total")),
        payment_terms=fields.get("payment_terms"),
        raw_text=raw_text,
    )


def _parse_columnar(rows: list[list[str]], header: list[str], raw_text: str) -> Invoice:
    invoice_number = ""
    vendor = ""
    date_str = None
    due_date = None
    items: list[LineItem] = []
    subtotal = None
    tax_amount = None
    total = None

    col = {h: i for i, h in enumerate(header)}

    for row in rows[1:]:
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))

        inv_num = _get_col(row, col, "invoice number") or _get_col(row, col, "invoice_number")
        if inv_num:
            invoice_number = inv_num
        v = _get_col(row, col, "vendor")
        if v:
            vendor = v
        d = _get_col(row, col, "date")
        if d:
            date_str = d
        dd = _get_col(row, col, "due date") or _get_col(row, col, "due_date")
        if dd:
            due_date = dd

        item_name = _get_col(row, col, "item")
        qty_str = _get_col(row, col, "qty") or _get_col(row, col, "quantity")
        price_str = _get_col(row, col, "unit price") or _get_col(row, col, "unit_price")
        line_total = _get_col(row, col, "line total") or _get_col(row, col, "line_total")

        if item_name and qty_str:
            items.append(
                LineItem(
                    item=item_name,
                    quantity=_safe_float(qty_str) or 0,
                    unit_price=_safe_float(price_str) or 0.0,
                    amount=_safe_float(line_total),
                )
            )
        else:
            lt = _get_col(row, col, "line total") or _get_col(row, col, "line_total")
            if lt:
                val_str = lt.replace(",", "")
                label = (
                    _get_col(row, col, "unit price")
                    or _get_col(row, col, "unit_price")
                    or ""
                ).lower().strip()
                if "subtotal" in label:
                    subtotal = _safe_float(val_str)
                elif "tax" in label:
                    tax_amount = _safe_float(val_str)
                elif "total" in label:
                    total = _safe_float(val_str)

    return Invoice(
        invoice_number=invoice_number,
        vendor=vendor,
        date=date_str,
        due_date=due_date,
        line_items=items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        raw_text=raw_text,
    )


def _get_col(row: list[str], col_map: dict[str, int], name: str) -> str | None:
    idx = col_map.get(name)
    if idx is not None and idx < len(row):
        val = row[idx].strip()
        return val if val else None
    return None


def _build_line_item(d: dict) -> LineItem:
    return LineItem(
        item=d.get("item", ""),
        quantity=_safe_float(d.get("quantity")) or 0,
        unit_price=_safe_float(d.get("unit_price")) or 0.0,
    )


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        s = val.replace(",", "").replace("$", "").strip()
        # Fix OCR artifacts: O -> 0, l -> 1 in numeric context
        s = s.replace("O", "0").replace("o", "0")
        return float(s)
    except (ValueError, AttributeError):
        return None
