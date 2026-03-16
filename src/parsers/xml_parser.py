from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from src.models import Invoice, LineItem


def parse_xml(file_path: Path) -> Invoice:
    raw_text = file_path.read_text()
    root = ET.fromstring(raw_text)

    def text(parent: ET.Element, tag: str) -> str | None:
        el = parent.find(tag)
        return el.text.strip() if el is not None and el.text else None

    header = root.find("header") or root
    totals = root.find("totals") or root

    invoice_number = text(header, "invoice_number") or text(root, "invoice_number") or "UNKNOWN"
    vendor = text(header, "vendor") or text(root, "vendor") or ""
    date_str = text(header, "date") or text(root, "date")
    due_date = text(header, "due_date") or text(root, "due_date")
    currency = text(header, "currency") or text(root, "currency") or "USD"

    line_items = []
    items_el = root.find("line_items")
    if items_el is not None:
        for item_el in items_el.findall("item"):
            name = text(item_el, "name") or text(item_el, "item") or ""
            qty = _safe_float(text(item_el, "quantity")) or 0
            price = _safe_float(text(item_el, "unit_price")) or 0.0
            amount = _safe_float(text(item_el, "amount"))
            line_items.append(LineItem(item=name, quantity=qty, unit_price=price, amount=amount))

    return Invoice(
        invoice_number=invoice_number,
        vendor=vendor,
        date=date_str,
        due_date=due_date,
        line_items=line_items,
        subtotal=_safe_float(text(totals, "subtotal")),
        tax_rate=_safe_float(text(totals, "tax_rate")),
        tax_amount=_safe_float(text(totals, "tax_amount")),
        total=_safe_float(text(totals, "total")),
        currency=currency,
        payment_terms=text(root, "payment_terms"),
        raw_text=raw_text,
    )


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val.replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None
