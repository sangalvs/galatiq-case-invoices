"""Parse PDF invoices by extracting text with pdfplumber, then using the txt parser."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from src.models import Invoice
from src.parsers.txt_parser import parse_txt_deterministic, preprocess_ocr


def parse_pdf(file_path: Path) -> Invoice:
    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    full_text = "\n".join(text_parts)
    if not full_text.strip():
        return Invoice(
            invoice_number="UNKNOWN",
            vendor="",
            raw_text="[PDF contained no extractable text]",
        )

    temp_path = file_path.with_suffix(".pdf.tmp.txt")
    try:
        temp_path.write_text(full_text)
        invoice = parse_txt_deterministic(temp_path)
        invoice.raw_text = full_text
    finally:
        temp_path.unlink(missing_ok=True)

    return invoice
