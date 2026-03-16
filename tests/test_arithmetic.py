"""Unit tests for arithmetic verification."""

from __future__ import annotations

import pytest

from src.agents.validation import _check_arithmetic
from src.models import Invoice, LineItem


class TestArithmeticVerification:
    def test_correct_arithmetic(self):
        inv = Invoice(
            invoice_number="TEST",
            vendor="Test",
            line_items=[
                LineItem(item="A", quantity=10, unit_price=250.0),
                LineItem(item="B", quantity=5, unit_price=500.0),
            ],
            subtotal=5000.0,
            tax_rate=0.08,
            tax_amount=400.0,
            total=5400.0,
        )
        flags = _check_arithmetic(inv)
        assert len(flags) == 0

    def test_wrong_subtotal(self):
        inv = Invoice(
            invoice_number="TEST",
            vendor="Test",
            line_items=[
                LineItem(item="A", quantity=10, unit_price=250.0),
            ],
            subtotal=3000.0,  # Should be 2500
            total=3000.0,
        )
        flags = _check_arithmetic(inv)
        subtotal_flags = [f for f in flags if f.field == "subtotal"]
        assert len(subtotal_flags) == 1

    def test_wrong_total(self):
        inv = Invoice(
            invoice_number="TEST",
            vendor="Test",
            line_items=[
                LineItem(item="A", quantity=10, unit_price=250.0),
            ],
            subtotal=2500.0,
            tax_amount=200.0,
            total=5000.0,  # Should be 2700
        )
        flags = _check_arithmetic(inv)
        total_flags = [f for f in flags if f.field == "total"]
        assert len(total_flags) == 1

    def test_wrong_tax(self):
        inv = Invoice(
            invoice_number="TEST",
            vendor="Test",
            line_items=[
                LineItem(item="A", quantity=10, unit_price=100.0),
            ],
            subtotal=1000.0,
            tax_rate=0.10,
            tax_amount=200.0,  # Should be 100
            total=1200.0,
        )
        flags = _check_arithmetic(inv)
        tax_flags = [f for f in flags if f.field == "tax"]
        assert len(tax_flags) == 1

    def test_no_line_items(self):
        inv = Invoice(
            invoice_number="TEST",
            vendor="Test",
            line_items=[],
            total=1000.0,
        )
        flags = _check_arithmetic(inv)
        assert len(flags) == 0

    def test_rounding_tolerance(self):
        inv = Invoice(
            invoice_number="TEST",
            vendor="Test",
            line_items=[
                LineItem(item="A", quantity=3, unit_price=33.33),
            ],
            subtotal=99.99,
            total=99.99,
        )
        flags = _check_arithmetic(inv)
        assert len(flags) == 0
