"""Unit tests for validation logic."""

from __future__ import annotations

import pytest

from src.models import Invoice, LineItem
from src.tools.inventory import check_stock, fuzzy_lookup_item, check_price_anomaly


class TestStockCheck:
    def test_item_within_stock(self, db_conn):
        result = check_stock("WidgetA", 5, db_conn)
        assert result["found"]
        assert result["issue"] is None

    def test_stock_exceeded(self, db_conn):
        result = check_stock("GadgetX", 20, db_conn)
        assert result["found"]
        assert result["issue"] == "stock_exceeded"

    def test_zero_stock(self, db_conn):
        result = check_stock("FakeItem", 100, db_conn)
        assert result["found"]
        assert result["issue"] == "zero_stock"

    def test_negative_quantity(self, db_conn):
        result = check_stock("WidgetA", -5, db_conn)
        assert result["found"]
        assert result["issue"] == "negative_qty"

    def test_unknown_item(self, db_conn):
        result = check_stock("SuperGizmo", 1, db_conn)
        assert not result["found"]
        assert result["issue"] == "unknown_item"

    def test_exact_stock(self, db_conn):
        result = check_stock("GadgetX", 5, db_conn)
        assert result["found"]
        assert result["issue"] is None


class TestFuzzyMatching:
    def test_exact_match(self, db_conn):
        row, confidence = fuzzy_lookup_item("WidgetA", db_conn)
        assert row is not None
        assert row["item"] == "WidgetA"
        assert confidence == 1.0

    def test_normalized_match(self, db_conn):
        row, confidence = fuzzy_lookup_item("Widget A", db_conn)
        assert row is not None
        assert row["item"] == "WidgetA"
        assert confidence == 0.95

    def test_gadget_with_space(self, db_conn):
        row, confidence = fuzzy_lookup_item("Gadget X", db_conn)
        assert row is not None
        assert row["item"] == "GadgetX"

    def test_unknown_item_no_match(self, db_conn):
        row, confidence = fuzzy_lookup_item("SuperGizmo", db_conn)
        assert row is None
        assert confidence == 0.0

    def test_widget_c_no_false_match(self, db_conn):
        row, confidence = fuzzy_lookup_item("WidgetC", db_conn)
        assert row is None


class TestPriceAnomaly:
    def test_normal_price(self, db_conn):
        result = check_price_anomaly("WidgetA", 250.0, conn=db_conn)
        assert result is None

    def test_price_over_tolerance(self, db_conn):
        result = check_price_anomaly("WidgetA", 350.0, conn=db_conn)
        assert result is not None
        assert result["deviation"] > 0.2

    def test_price_under_tolerance(self, db_conn):
        result = check_price_anomaly("WidgetA", 180.0, conn=db_conn)
        assert result is not None

    def test_borderline_price(self, db_conn):
        result = check_price_anomaly("WidgetA", 300.0, conn=db_conn)
        assert result is None or result["deviation"] <= 0.20

    def test_currency_conversion(self, db_conn):
        result = check_price_anomaly("WidgetA", 225.0, "EUR", conn=db_conn, exchange_rate=1.08)
        # 225 * 1.08 = 243 USD, ref is 250. Deviation ~2.8%, within 20%
        assert result is None
