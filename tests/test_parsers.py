"""Unit tests for file parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.parsers.json_parser import parse_json
from src.parsers.csv_parser import parse_csv
from src.parsers.xml_parser import parse_xml
from src.parsers.txt_parser import parse_txt_deterministic, preprocess_ocr
from src.parsers.registry import parse_invoice


class TestJsonParser:
    def test_parse_1004(self, data_dir):
        inv = parse_json(data_dir / "invoice_1004.json")
        assert inv.invoice_number == "INV-1004"
        assert inv.vendor == "Precision Parts Ltd."
        assert inv.total == 1890.0
        assert len(inv.line_items) == 2
        assert inv.currency == "USD"

    def test_parse_1009_missing_data(self, data_dir):
        inv = parse_json(data_dir / "invoice_1009.json")
        assert inv.invoice_number == "INV-1009"
        assert inv.vendor == ""
        assert inv.due_date is None
        assert inv.line_items[0].quantity == -5

    def test_parse_1016_unknown_item(self, data_dir):
        inv = parse_json(data_dir / "invoice_1016.json")
        assert inv.invoice_number == "INV-1016"
        items = [i.item for i in inv.line_items]
        assert "WidgetC" in items

    def test_parse_1004_revised(self, data_dir):
        inv = parse_json(data_dir / "invoice_1004_revised.json")
        assert inv.invoice_number == "INV-1004"
        assert inv.revision == "R1"
        assert len(inv.line_items) == 3


class TestCsvParser:
    def test_field_value_format(self, data_dir):
        inv = parse_csv(data_dir / "invoice_1006.csv")
        assert inv.invoice_number == "INV-1006"
        assert inv.vendor == "Acme Industrial Supplies"
        assert len(inv.line_items) == 2
        assert inv.total == 2750.0

    def test_columnar_format(self, data_dir):
        inv = parse_csv(data_dir / "invoice_1007.csv")
        assert inv.invoice_number == "INV-1007"
        assert len(inv.line_items) == 3
        assert inv.line_items[0].item == "WidgetA"
        assert inv.line_items[0].quantity == 20.0


class TestXmlParser:
    def test_parse_1014(self, data_dir):
        inv = parse_xml(data_dir / "invoice_1014.xml")
        assert inv.invoice_number == "INV-1014"
        assert inv.vendor == "TechParts International"
        assert inv.currency == "EUR"
        assert inv.total == 4125.0
        assert len(inv.line_items) == 2


class TestTxtParser:
    def test_parse_1001(self, data_dir):
        inv = parse_txt_deterministic(data_dir / "invoice_1001.txt")
        assert inv.invoice_number == "INV-1001"
        assert "Widgets" in inv.vendor
        assert inv.total == 5000.0
        assert len(inv.line_items) == 2

    def test_parse_1003_fraud(self, data_dir):
        inv = parse_txt_deterministic(data_dir / "invoice_1003.txt")
        assert inv.invoice_number == "INV-1003"
        assert "Fraudster" in inv.vendor
        assert inv.total == 100000.0

    def test_parse_1002_abbreviations(self, data_dir):
        inv = parse_txt_deterministic(data_dir / "invoice_1002.txt")
        assert "1002" in inv.invoice_number
        assert inv.vendor == "Gadgets Co"
        assert inv.line_items[0].quantity == 20.0

    def test_parse_1010_rush_order(self, data_dir):
        inv = parse_txt_deterministic(data_dir / "invoice_1010.txt")
        assert inv.invoice_number == "INV-1010"
        assert len(inv.line_items) == 4
        rush = [i for i in inv.line_items if "rush" in i.item.lower()]
        assert len(rush) == 1
        assert rush[0].unit_price == 300.0

    def test_parse_1012_ocr(self, data_dir):
        inv = parse_txt_deterministic(data_dir / "invoice_1012.txt")
        assert "1012" in inv.invoice_number
        assert len(inv.line_items) == 3
        assert inv.total == 9975.0

    def test_parse_1008_email(self, data_dir):
        inv = parse_txt_deterministic(data_dir / "invoice_1008.txt")
        assert "1008" in inv.invoice_number
        assert inv.vendor == "NoProd Industries"
        assert len(inv.line_items) == 2


class TestOcrPreprocessing:
    def test_digit_o_replacement(self):
        assert "2026" in preprocess_ocr("2O26")

    def test_dollar_o_replacement(self):
        result = preprocess_ocr("$3,500.O0")
        assert "O" not in result
        assert "3,500.00" in result

    def test_no_false_positives(self):
        text = "INVOICE from Olivia at Office Corp"
        result = preprocess_ocr(text)
        assert "Olivia" in result
        assert "Office" in result


class TestRegistry:
    def test_json_dispatch(self, data_dir):
        inv = parse_invoice(data_dir / "invoice_1004.json")
        assert inv.invoice_number == "INV-1004"

    def test_csv_dispatch(self, data_dir):
        inv = parse_invoice(data_dir / "invoice_1006.csv")
        assert inv.invoice_number == "INV-1006"

    def test_xml_dispatch(self, data_dir):
        inv = parse_invoice(data_dir / "invoice_1014.xml")
        assert inv.invoice_number == "INV-1014"

    def test_unsupported_format(self, tmp_path):
        f = tmp_path / "test.xlsx"
        f.write_text("test")
        with pytest.raises(ValueError, match="Unsupported"):
            parse_invoice(f)
