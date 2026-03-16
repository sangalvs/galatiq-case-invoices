"""Parse unstructured text invoices using LLM extraction."""

from __future__ import annotations

import re
from pathlib import Path

from src.models import Invoice, LineItem


def preprocess_ocr(text: str) -> str:
    """Fix common OCR artifacts: letter O in numeric contexts -> digit 0, etc."""
    result = text
    result = re.sub(r'(\d)O(\d)', r'\g<1>0\2', result)
    result = re.sub(r'(\$[\d,]+)O([\d.])', r'\g<1>0\2', result)
    result = re.sub(r'([\d.])O(\d)', r'\g<1>0\2', result)
    result = re.sub(r'(\d{1,2})-(\w{3})-(\d)O(\d{2})', r'\1-\2-\g<3>0\4', result)
    return result


def parse_txt_deterministic(file_path: Path) -> Invoice:
    """Best-effort deterministic extraction from text. Used as fallback or seed for LLM."""
    raw_text = file_path.read_text()
    cleaned = preprocess_ocr(raw_text)

    invoice_number = _extract_pattern(
        cleaned,
        [
            r'(?:Invoice\s*(?:Number|#|No\.?|NO\.?))\s*:?\s*(INV[\s-]*\d+)',
            r'(?:Inv\s*#)\s*:?\s*(\d+)',
            r'(?:INV\s*NO)\s*:?\s*(INV[\s-]*\d+)',
            r'(?:Invoice)\s*:?\s*(INV[\s-]*\d+)',
            r'#\s*(INV[\s-]*\d+)',
            r'INVOICE\s+#(INV[\s-]*\d+)',
        ],
    )
    if invoice_number:
        invoice_number = re.sub(r'\s+', '', invoice_number)
        if not invoice_number.startswith("INV"):
            invoice_number = f"INV-{invoice_number}"
        if re.match(r'^INV\d', invoice_number):
            invoice_number = "INV-" + invoice_number[3:]
        invoice_number = invoice_number.replace("INV--", "INV-")

    vendor = _extract_pattern(
        cleaned,
        [
            r'(?:Vendor|Vndr)\s*:?\s*(.+)',
        ],
    )
    if not vendor:
        vendor = _extract_pattern(cleaned, [r'FROM\s*:?\s*(.+)'])
    if vendor:
        vendor = vendor.strip().rstrip(".")
        vendor = re.sub(r'\s*\(formerly.*?\)', '', vendor)

    date_str = _extract_pattern(
        cleaned,
        [
            r'(?:Date|Dt)\s*:?\s*(\d{4}-\d{2}-\d{2})',
            r'(?:Date|Dt)\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})',
            r'(?:Date|Dt)\s*:?\s*(\d{1,2}-\w{3}-\d{4})',
            r'DATE\s*:?\s*(\d{2}-\w{3}-\d{4})',
        ],
    )

    due_date = _extract_pattern(
        cleaned,
        [
            r'(?:Due\s*(?:Date|Dt)?)\s*:?\s*(\d{4}-\d{2}-\d{2})',
            r'(?:Due\s*(?:Date|Dt)?)\s*:?\s*(\w+\s+\d{1,2},?\s+\d{4})',
            r'DUE\s*:?\s*(\d{2}-\w{3}-\d{4})',
            r'(?:Due\s*(?:Date|Dt)?)\s*:?\s*(.+)',
        ],
    )

    subtotal = _extract_amount(cleaned, [
        r'Subtotal\s*:?\s*\$?([\d,]+\.?\d*)',
        r'SUBTOTAL\s*:?\s*\$?([\d,]+\.?\d*)',
    ])

    total = _extract_amount(cleaned, [
        r'(?<!sub)TOTAL\s*:?\s*\$?([\d,]+\.?\d*)',
        r'(?:Total\s*Amount)\s*:?\s*\$?([\d,]+\.?\d*)',
    ])

    tax_amount = _extract_amount(cleaned, [
        r'(?:Tax|Sales Tax)\s*\([^)]*\)\s*:?\s*\$?([\d,]+\.?\d*)',
        r'TAX\s*\([^)]*\)\s*:?\s*\$?([\d,]+\.?\d*)',
    ])

    payment_terms = _extract_pattern(cleaned, [
        r'(?:Payment\s*Terms|Pymnt\s*Terms|Terms)\s*:?\s*(.+)',
    ])

    notes = _extract_pattern(cleaned, [
        r'Notes?\s*:?\s*(.+)',
    ])

    line_items = _extract_line_items(cleaned)

    amount_match = _extract_pattern(cleaned, [r'Amt\s*:?\s*\$?([\d,]+\.?\d*)'])
    if amount_match and total is None:
        total = _safe_float(amount_match)

    return Invoice(
        invoice_number=invoice_number or "UNKNOWN",
        vendor=vendor or "",
        date=date_str,
        due_date=due_date,
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        total=total,
        payment_terms=payment_terms,
        notes=notes,
        raw_text=raw_text,
    )


def _extract_line_items(text: str) -> list[LineItem]:
    items = []
    skip_words = {"subtotal", "tax", "total", "shipping", "sales tax", ""}

    patterns = [
        # "WidgetA    qty: 10    unit price: $250.00"
        r'([\w][\w\s()]*?)\s+(?:qty:?\s*|x)(\d+)\s+(?:(?:unit\s*price|@)\s*:?\s*)\$?([\d,]+\.?\d*)',
        # "- SuperGizmo       x12     $400.00 each"
        r'-\s+([\w][\w\s]*?)\s+x(\d+)\s+\$?([\d,]+\.?\d*)',
        # "Widget A       12    $250     $3,000.00" (tabular with 4 cols)
        r'^[ \t]*([\w][\w\s()]*?)\s{2,}(\d+)\s+\$?([\d,]+\.?\d*)\s+\$?([\d,]+\.?\d*)\s*$',
    ]

    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE | re.MULTILINE):
            groups = m.groups()
            name = groups[0].strip()
            if name.lower() in skip_words:
                continue
            if re.match(r'^-+$', name):
                continue
            qty = _safe_float(groups[1]) or 0
            price = _safe_float(groups[2]) or 0.0
            amount = _safe_float(groups[3]) if len(groups) > 3 else None
            items.append(LineItem(item=name, quantity=qty, unit_price=price, amount=amount))

        if items:
            break

    return items


def _extract_pattern(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_amount(text: str, patterns: list[str]) -> float | None:
    val = _extract_pattern(text, patterns)
    return _safe_float(val)


def _safe_float(val: str | None) -> float | None:
    if val is None:
        return None
    try:
        return float(val.replace(",", "").replace("$", "").strip())
    except (ValueError, AttributeError):
        return None
