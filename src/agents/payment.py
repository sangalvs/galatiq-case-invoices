"""Payment agent: process payment or log rejection."""

from __future__ import annotations

from typing import Any, Dict

from src.models import (
    ApprovalDecision,
    Invoice,
    PaymentResult,
    PaymentStatus,
    ProcessingLogEntry,
)
from src.tools.db import convert_to_usd, record_processed_invoice
from src.tools.payment import mock_payment


def _log(state: Dict[str, Any], action: str, result: str, details: str = "") -> None:
    inv_num = state.get("invoice", {}).get("invoice_number", "UNKNOWN")
    entry = ProcessingLogEntry(
        invoice_number=inv_num, stage="payment", action=action, result=result, details=details
    )
    state.setdefault("processing_log", []).append(entry.model_dump())


def payment_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("invoice_parse_error"):
        inv_data = state.get("invoice") or {}
        inv_num = inv_data.get("invoice_number", "UNKNOWN")
        _log(state, "start", "warning", "Skipping payment: invalid invoice structure")
        payment_result = PaymentResult(
            status=PaymentStatus.REJECTED,
            vendor=inv_data.get("vendor", ""),
            amount=inv_data.get("total") or 0,
            currency=inv_data.get("currency", "USD"),
            detail="Invalid invoice structure.",
        )
        state["payment_result"] = payment_result.model_dump()
        try:
            record_processed_invoice(
                invoice_number=inv_num,
                vendor=inv_data.get("vendor", ""),
                total_amount=float(inv_data.get("total") or 0),
                currency=inv_data.get("currency", "USD"),
                total_amount_usd=float(inv_data.get("total") or 0),
                status="rejected",
                fraud_risk_level="critical",
                fraud_risk_score=100,
                file_path=state.get("file_path", ""),
                revision=None,
                rejection_reason="Invalid invoice structure.",
            )
        except Exception as e:
            _log(state, "db_error", "warning", f"Failed to record: {e}")
        _log(state, "complete", "success", "Rejected: invalid invoice structure")
        return state

    invoice_data = state.get("invoice", {})
    invoice = Invoice(**invoice_data)
    approval = state.get("approval_result", {})
    fraud = state.get("fraud_result", {})

    decision = approval.get("decision", "rejected")
    _log(state, "start", "info", f"Payment processing for {invoice.invoice_number} (decision: {decision})")

    total_usd = convert_to_usd(invoice.total or 0, invoice.currency)

    if decision == ApprovalDecision.APPROVED.value:
        payment_result = mock_payment(invoice.vendor, invoice.total or 0, invoice.currency)
        _log(state, "payment_executed", "success", payment_result.detail)

        status = "approved"
        rejection_reason = None
    elif decision == ApprovalDecision.FLAGGED.value:
        payment_result = PaymentResult(
            status=PaymentStatus.REJECTED,
            vendor=invoice.vendor,
            amount=invoice.total or 0,
            currency=invoice.currency,
            detail=f"Flagged for review: {approval.get('reasoning', 'N/A')[:400]}",
        )
        _log(state, "flagged", "warning",
             f"Invoice flagged for review. Reason: {approval.get('reasoning', 'N/A')[:400]}")

        status = "flagged"
        rejection_reason = approval.get("reasoning", "")
    else:
        payment_result = PaymentResult(
            status=PaymentStatus.REJECTED,
            vendor=invoice.vendor,
            amount=invoice.total or 0,
            currency=invoice.currency,
            detail=f"Rejected: {approval.get('reasoning', 'N/A')[:400]}",
        )
        _log(state, "rejected", "info",
             f"Invoice rejected. Reason: {approval.get('reasoning', 'N/A')[:400]}")

        status = "rejected"
        rejection_reason = approval.get("reasoning", "")

    state["payment_result"] = payment_result.model_dump()

    if state.get("is_duplicate"):
        _log(state, "skip_record", "info", "Duplicate invoice — not recording again (already in DB)")
    else:
        try:
            record_processed_invoice(
                invoice_number=invoice.invoice_number,
                vendor=invoice.vendor,
                total_amount=invoice.total or 0,
                currency=invoice.currency,
                total_amount_usd=total_usd,
                status=status,
                fraud_risk_level=fraud.get("risk_level", "low"),
                fraud_risk_score=fraud.get("risk_score", 0),
                file_path=state.get("file_path", ""),
                revision=invoice.revision,
                rejection_reason=rejection_reason,
            )
        except Exception as e:
            _log(state, "db_error", "warning", f"Failed to record to DB: {e}")

    _log(state, "complete", "success", f"Final status: {status}")
    return state
