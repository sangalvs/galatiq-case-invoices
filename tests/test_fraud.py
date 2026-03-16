"""Unit tests for fraud detection signals."""

from __future__ import annotations

import pytest

from src.agents.fraud import (
    _score_urgency,
    _score_data_integrity,
    _score_vendor_risk,
    _compute_risk,
)
from src.models import FraudSignal, Invoice, LineItem, RiskLevel


def _make_invoice(**kwargs) -> Invoice:
    defaults = {"invoice_number": "TEST-001", "vendor": "Test Corp"}
    defaults.update(kwargs)
    return Invoice(**defaults)


class TestUrgencyScoring:
    def test_no_urgency(self):
        inv = _make_invoice(payment_terms="Net 30")
        sig = _score_urgency(inv, "Regular invoice text")
        assert sig.score == 0

    def test_urgent_keywords(self):
        inv = _make_invoice(payment_terms="Immediate", notes="URGENT - Pay immediately!")
        sig = _score_urgency(inv, "URGENT - Pay immediately! Wire transfer preferred.")
        assert sig.score >= 7

    def test_yesterday_due_date(self):
        inv = _make_invoice(due_date="yesterday")
        sig = _score_urgency(inv, "Due: yesterday")
        assert sig.score >= 3


class TestDataIntegrity:
    def test_clean_invoice(self):
        inv = _make_invoice(
            due_date="2026-02-01",
            line_items=[LineItem(item="WidgetA", quantity=5, unit_price=250.0)],
        )
        sig = _score_data_integrity(inv, {"item_flags": [], "arithmetic_flags": []})
        assert sig.score == 0

    def test_negative_quantity(self):
        inv = _make_invoice(
            due_date="2026-02-01",
            line_items=[LineItem(item="WidgetA", quantity=-5, unit_price=250.0)],
        )
        sig = _score_data_integrity(inv, {"item_flags": [], "arithmetic_flags": []})
        assert sig.score >= 4

    def test_missing_vendor(self):
        inv = _make_invoice(vendor="", due_date="2026-02-01", line_items=[])
        sig = _score_data_integrity(inv, {"item_flags": [], "arithmetic_flags": []})
        assert sig.score >= 3

    def test_zero_stock_item(self):
        inv = _make_invoice(due_date="2026-02-01", line_items=[])
        val = {"item_flags": [{"issue": "zero_stock", "item": "FakeItem"}], "arithmetic_flags": []}
        sig = _score_data_integrity(inv, val)
        assert sig.score >= 3


class TestVendorRisk:
    def test_known_vendor(self, db_conn):
        inv = _make_invoice(vendor="Widgets Inc.")
        sig = _score_vendor_risk(inv, "Normal invoice text", conn=db_conn)
        assert sig.score <= 3

    def test_suspicious_vendor_name(self, db_conn):
        inv = _make_invoice(vendor="Fraudster LLC")
        sig = _score_vendor_risk(inv, "Invoice from Fraudster LLC", conn=db_conn)
        assert sig.score >= 5

    def test_empty_vendor(self, db_conn):
        inv = _make_invoice(vendor="")
        sig = _score_vendor_risk(inv, "Invoice", conn=db_conn)
        assert sig.score >= 5

    def test_suspicious_domain(self, db_conn):
        inv = _make_invoice(vendor="NoProd Industries")
        sig = _score_vendor_risk(inv, "from billing@noproduct.biz", conn=db_conn)
        assert sig.score >= 3


class TestCompositeRisk:
    def test_all_low(self):
        signals = [
            FraudSignal(category="urgency", description="None", score=0),
            FraudSignal(category="price", description="None", score=0),
            FraudSignal(category="vendor", description="None", score=0),
            FraudSignal(category="integrity", description="None", score=0),
            FraudSignal(category="pattern", description="None", score=0),
        ]
        score, level, rec = _compute_risk(signals)
        assert level == RiskLevel.LOW
        assert score <= 25

    def test_critical_risk(self):
        signals = [
            FraudSignal(category="urgency", description="URGENT", score=10),
            FraudSignal(category="price", description="Anomaly", score=5),
            FraudSignal(category="vendor", description="Fraudster", score=8),
            FraudSignal(category="integrity", description="Zero stock", score=7),
            FraudSignal(category="pattern", description="Suspicious", score=8),
        ]
        score, level, rec = _compute_risk(signals)
        assert level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert score >= 51

    def test_single_high_signal_amplifies(self):
        signals = [
            FraudSignal(category="urgency", description="URGENT", score=9),
            FraudSignal(category="price", description="None", score=0),
            FraudSignal(category="vendor", description="None", score=0),
            FraudSignal(category="integrity", description="None", score=0),
            FraudSignal(category="pattern", description="None", score=0),
        ]
        score, level, rec = _compute_risk(signals)
        assert score >= 51
