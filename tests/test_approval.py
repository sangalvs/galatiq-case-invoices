"""Unit tests for approval rules."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents import approval
from src.agents.approval import _initial_assessment
from src.models import ApprovalDecision, Invoice, LineItem


def _make_invoice(**kwargs) -> Invoice:
    defaults = {
        "invoice_number": "TEST-001",
        "vendor": "Test Corp",
        "total": 5000.0,
        "line_items": [LineItem(item="WidgetA", quantity=5, unit_price=250.0)],
    }
    defaults.update(kwargs)
    return Invoice(**defaults)


class TestInitialAssessment:
    def test_clean_invoice_under_threshold(self):
        inv = _make_invoice(total=5000.0)
        val = {"passed": True, "item_flags": [], "arithmetic_flags": []}
        fraud = {"risk_level": "low", "risk_score": 5, "recommendation": "proceed", "signals": []}
        result = _initial_assessment(inv, val, fraud, 5000.0)
        assert result["decision"] == ApprovalDecision.APPROVED
        assert not result["requires_scrutiny"]

    def test_clean_invoice_over_threshold(self):
        """Over-threshold invoices are FLAGGED by default (no auto-payment)."""
        inv = _make_invoice(total=15000.0)
        val = {"passed": True, "item_flags": [], "arithmetic_flags": []}
        fraud = {"risk_level": "low", "risk_score": 5, "recommendation": "proceed", "signals": []}
        result = _initial_assessment(inv, val, fraud, 15000.0)
        assert result["decision"] == ApprovalDecision.FLAGGED
        assert any("threshold" in r and "VP approval" in r for r in result["reasons"])

    def test_clean_invoice_over_threshold_demo_mode(self):
        """When AUTO_APPROVE_OVER_THRESHOLD is True, over-threshold is APPROVED with requires_scrutiny."""
        inv = _make_invoice(total=15000.0)
        val = {"passed": True, "item_flags": [], "arithmetic_flags": []}
        fraud = {"risk_level": "low", "risk_score": 5, "recommendation": "proceed", "signals": []}
        with patch.object(approval, "AUTO_APPROVE_OVER_THRESHOLD", True):
            result = _initial_assessment(inv, val, fraud, 15000.0)
        assert result["decision"] == ApprovalDecision.APPROVED
        assert result["requires_scrutiny"]

    def test_validation_failure_rejects(self):
        inv = _make_invoice()
        val = {
            "passed": False,
            "item_flags": [{"severity": "error", "item": "GadgetX", "issue": "stock_exceeded",
                           "detail": "Requested 20, only 5 in stock"}],
            "arithmetic_flags": [],
        }
        fraud = {"risk_level": "low", "risk_score": 5, "recommendation": "proceed", "signals": []}
        result = _initial_assessment(inv, val, fraud, 5000.0)
        assert result["decision"] == ApprovalDecision.REJECTED

    def test_high_fraud_rejects(self):
        inv = _make_invoice()
        val = {"passed": True, "item_flags": [], "arithmetic_flags": []}
        fraud = {
            "risk_level": "high",
            "risk_score": 70,
            "recommendation": "reject",
            "signals": [{"category": "urgency", "score": 9, "description": "URGENT"}],
        }
        result = _initial_assessment(inv, val, fraud, 5000.0)
        assert result["decision"] == ApprovalDecision.REJECTED

    def test_medium_fraud_flags(self):
        inv = _make_invoice()
        val = {"passed": True, "item_flags": [], "arithmetic_flags": []}
        fraud = {
            "risk_level": "medium",
            "risk_score": 40,
            "recommendation": "flag_for_review",
            "signals": [],
        }
        result = _initial_assessment(inv, val, fraud, 5000.0)
        assert result["decision"] == ApprovalDecision.FLAGGED

    def test_critical_fraud_always_rejects(self):
        inv = _make_invoice()
        val = {"passed": True, "item_flags": [], "arithmetic_flags": []}
        fraud = {
            "risk_level": "critical",
            "risk_score": 90,
            "recommendation": "reject",
            "signals": [{"category": "urgency", "score": 10, "description": "URGENT"}],
        }
        result = _initial_assessment(inv, val, fraud, 5000.0)
        assert result["decision"] == ApprovalDecision.REJECTED
