"""Dispatch invoice parsing by file extension."""

from __future__ import annotations

from pathlib import Path

from src.models import Invoice
from src.parsers.csv_parser import parse_csv
from src.parsers.json_parser import parse_json
from src.parsers.pdf_parser import parse_pdf
from src.parsers.txt_parser import parse_txt_deterministic
from src.parsers.xml_parser import parse_xml

PARSER_MAP = {
    ".json": parse_json,
    ".csv": parse_csv,
    ".xml": parse_xml,
    ".txt": parse_txt_deterministic,
    ".pdf": parse_pdf,
}


def parse_invoice(file_path: str | Path) -> Invoice:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Invoice file not found: {path}")

    ext = path.suffix.lower()
    parser = PARSER_MAP.get(ext)
    if parser is None:
        raise ValueError(f"Unsupported file format: {ext} (supported: {list(PARSER_MAP.keys())})")

    return parser(path)
