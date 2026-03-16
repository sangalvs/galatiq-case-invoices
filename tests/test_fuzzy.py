"""Unit tests for fuzzy item matching."""

from __future__ import annotations

import pytest

from src.tools.inventory import (
    fuzzy_lookup_item,
    normalize_item_name,
    normalize_item_name_ocr,
)


class TestNormalization:
    def test_basic(self):
        assert normalize_item_name("WidgetA") == "widgeta"

    def test_with_spaces(self):
        assert normalize_item_name("Widget A") == "widgeta"

    def test_with_punctuation(self):
        assert normalize_item_name("Widget-A") == "widgeta"

    def test_case_insensitive(self):
        assert normalize_item_name("WIDGETA") == "widgeta"


class TestFuzzyLookup:
    def test_exact_match(self, db_conn):
        row, conf = fuzzy_lookup_item("WidgetA", db_conn)
        assert row is not None
        assert conf == 1.0

    def test_space_variant(self, db_conn):
        row, conf = fuzzy_lookup_item("Widget A", db_conn)
        assert row is not None
        assert row["item"] == "WidgetA"
        assert conf == 0.95

    def test_case_variant(self, db_conn):
        row, conf = fuzzy_lookup_item("widgeta", db_conn)
        assert row is not None
        assert row["item"] == "WidgetA"

    def test_gadget_x_space(self, db_conn):
        row, conf = fuzzy_lookup_item("Gadget X", db_conn)
        assert row is not None
        assert row["item"] == "GadgetX"

    def test_completely_unknown(self, db_conn):
        row, conf = fuzzy_lookup_item("SuperGizmo", db_conn)
        assert row is None

    def test_widget_c_rejected(self, db_conn):
        row, conf = fuzzy_lookup_item("WidgetC", db_conn)
        assert row is None

    def test_mega_sprocket_rejected(self, db_conn):
        row, conf = fuzzy_lookup_item("MegaSprocket", db_conn)
        assert row is None

    def test_ocr_w1dgetb_matches_widgetb(self, db_conn):
        """OCR artifact: 1 in place of i should match WidgetB."""
        row, conf = fuzzy_lookup_item("w1dgetb", db_conn, threshold=0.85)
        assert row is not None
        assert row["item"] == "WidgetB"
        assert conf >= 0.85

    def test_ocr_w1dgeta_matches_widgeta(self, db_conn):
        """OCR artifact: 1 in place of i should match WidgetA."""
        row, conf = fuzzy_lookup_item("W1dgetA", db_conn, threshold=0.85)
        assert row is not None
        assert row["item"] == "WidgetA"


class TestOcrNormalization:
    def test_ocr_normalize_1_to_i(self):
        assert normalize_item_name_ocr("w1dgetb") == "widgetb"
        assert normalize_item_name_ocr("WidgetB") == "widgetb"

    def test_ocr_normalize_0_to_o(self):
        assert normalize_item_name_ocr("GadgetX") == "gadgetx"
        assert normalize_item_name_ocr("Gadget0") == "gadgeto"  # 0 -> o for matching
