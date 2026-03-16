from __future__ import annotations

import json
from pathlib import Path

from src.models import Invoice, LineItem


def _get(data: dict, *keys, default=None):
    """Get first present key from dict."""
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    return default


def parse_json(file_path: Path) -> Invoice:
    with open(file_path) as f:
        data = json.load(f)

    vendor_raw = _get(data, "vendor", "vendor_name", default="")
    if isinstance(vendor_raw, dict):
        vendor = vendor_raw.get("name", "") or str(vendor_raw.get("legal_name", ""))
    else:
        vendor = str(vendor_raw)

    line_items = []
    for item in data.get("line_items", data.get("lineItems", [])):
        if not isinstance(item, dict):
            continue
        item_name = _get(item, "item", "product", "name", default="")
        qty = _get(item, "quantity", "qty", default=0)
        price = _get(item, "unit_price", "unitPrice", "price", default=0.0)
        line_items.append(
            LineItem(
                item=str(item_name),
                quantity=float(qty) if qty is not None else 0,
                unit_price=float(price) if price is not None else 0.0,
                amount=item.get("amount", item.get("amt")),
                note=item.get("note"),
            )
        )

    return Invoice(
        invoice_number=str(_get(data, "invoice_number", "inv_num", default="")),
        vendor=vendor,
        date=_get(data, "date", "invoice_date"),
        due_date=_get(data, "due_date", "dueDate"),
        line_items=line_items,
        subtotal=_get(data, "subtotal", "sub_total"),
        tax_rate=_get(data, "tax_rate", "taxRate"),
        tax_amount=_get(data, "tax_amount", "taxAmount"),
        total=_get(data, "total", "grand_total"),
        currency=str(_get(data, "currency", default="USD")),
        payment_terms=_get(data, "payment_terms", "paymentTerms"),
        notes=data.get("notes"),
        revision=data.get("revision"),
        raw_text=json.dumps(data, indent=2),
    )
