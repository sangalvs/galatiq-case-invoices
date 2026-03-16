"""Shared state for the LangGraph pipeline."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict

from src.models import (
    ApprovalResult,
    FraudResult,
    Invoice,
    PaymentResult,
    ProcessingLogEntry,
    ValidationResult,
)


class PipelineState(TypedDict, total=False):
    file_path: str
    raw_text: str
    invoice: Optional[Dict[str, Any]]
    invoice_parse_error: Optional[str]
    is_duplicate: Optional[bool]
    duplicate_of: Optional[Dict[str, Any]]
    validation_result: Optional[Dict[str, Any]]
    fraud_result: Optional[Dict[str, Any]]
    approval_result: Optional[Dict[str, Any]]
    payment_result: Optional[Dict[str, Any]]
    processing_log: List[Dict[str, Any]]
    errors: List[str]
