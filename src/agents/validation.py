"""Validation agent: check inventory, stock, arithmetic, data integrity."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.models import (
    ArithmeticFlag,
    Invoice,
    ItemFlag,
    LineItem,
    ProcessingLogEntry,
    ValidationResult,
)
from src.tools.db import check_duplicate_invoice, convert_to_usd, get_exchange_rate, get_known_currencies
from src.tools.inventory import check_price_anomaly, check_stock, fuzzy_lookup_item


def _log(state: Dict[str, Any], action: str, result: str, details: str = "") -> None:
    inv_num = state.get("invoice", {}).get("invoice_number", "UNKNOWN")
    entry = ProcessingLogEntry(
        invoice_number=inv_num, stage="validation", action=action, result=result, details=details
    )
    state.setdefault("processing_log", []).append(entry.model_dump())


def _check_items(invoice: Invoice, exchange_rate: float) -> List[ItemFlag]:
    flags = []

    from collections import defaultdict
    aggregate_qty: dict = defaultdict(float)
    for item in invoice.line_items:
        row, conf = fuzzy_lookup_item(item.item)
        canonical = row["item"] if (conf > 0 and row) else item.item
        aggregate_qty[canonical] += item.quantity

    aggregates_checked = set()

    for item in invoice.line_items:
        result = check_stock(item.item, item.quantity)

        if not result["found"]:
            flags.append(ItemFlag(
                item=item.item,
                issue="unknown_item",
                detail=result["detail"],
                severity="error",
            ))
            continue

        if result["issue"] == "zero_stock":
            flags.append(ItemFlag(
                item=item.item,
                issue="zero_stock",
                detail=result["detail"],
                severity="error",
            ))
        elif result["issue"] == "negative_qty":
            flags.append(ItemFlag(
                item=item.item,
                issue="negative_qty",
                detail=result["detail"],
                severity="error",
            ))
        elif result["issue"] == "stock_exceeded":
            flags.append(ItemFlag(
                item=item.item,
                issue="stock_exceeded",
                detail=result["detail"],
                severity="error",
            ))

        price_flag = check_price_anomaly(
            item.item, item.unit_price, invoice.currency, exchange_rate=exchange_rate
        )
        if price_flag:
            flags.append(ItemFlag(
                item=item.item,
                issue="price_anomaly",
                detail=price_flag["detail"],
                severity="warning",
            ))

    for canonical, total_qty in aggregate_qty.items():
        if canonical in aggregates_checked:
            continue
        aggregates_checked.add(canonical)
        agg_result = check_stock(canonical, total_qty)
        if agg_result["found"] and agg_result["issue"] == "stock_exceeded":
            individual_ok = all(
                check_stock(canonical, item.quantity).get("issue") is None
                for item in invoice.line_items
                if (fuzzy_lookup_item(item.item)[0] or {}).get("item") == canonical
            )
            if individual_ok:
                flags.append(ItemFlag(
                    item=canonical,
                    issue="stock_exceeded",
                    detail=f"Aggregate quantity {total_qty} for '{canonical}' exceeds stock ({agg_result['stock']})",
                    severity="error",
                ))

    return flags


def _check_arithmetic(invoice: Invoice) -> List[ArithmeticFlag]:
    flags = []
    tolerance = 0.02

    if not invoice.line_items:
        return flags

    computed_subtotal = sum(
        item.quantity * item.unit_price for item in invoice.line_items
    )
    computed_subtotal = round(computed_subtotal, 2)

    if invoice.subtotal is not None:
        diff = abs(computed_subtotal - invoice.subtotal)
        if diff > tolerance:
            flags.append(ArithmeticFlag(
                field="subtotal",
                expected=computed_subtotal,
                actual=invoice.subtotal,
                detail=f"Computed subtotal ${computed_subtotal:,.2f} != stated ${invoice.subtotal:,.2f} (diff: ${diff:,.2f})",
            ))

    if invoice.tax_rate is not None and invoice.subtotal is not None:
        expected_tax = round(invoice.subtotal * invoice.tax_rate, 2)
        if invoice.tax_amount is not None:
            diff = abs(expected_tax - invoice.tax_amount)
            if diff > tolerance:
                flags.append(ArithmeticFlag(
                    field="tax",
                    expected=expected_tax,
                    actual=invoice.tax_amount,
                    detail=f"Expected tax ${expected_tax:,.2f} != stated ${invoice.tax_amount:,.2f}",
                ))

    if invoice.total is not None:
        base = invoice.subtotal if invoice.subtotal is not None else computed_subtotal
        tax = invoice.tax_amount if invoice.tax_amount is not None else 0
        expected_total = round(base + tax, 2)
        diff = abs(expected_total - invoice.total)
        if diff > tolerance:
            flags.append(ArithmeticFlag(
                field="total",
                expected=expected_total,
                actual=invoice.total,
                detail=f"Expected total ${expected_total:,.2f} != stated ${invoice.total:,.2f} (diff: ${diff:,.2f})",
            ))

    return flags


def _check_data_integrity(invoice: Invoice) -> List[str]:
    warnings = []
    if not invoice.vendor:
        warnings.append("Missing vendor name")
    if not invoice.due_date:
        warnings.append("Missing due date")
    if invoice.total is not None and invoice.total < 0:
        warnings.append(f"Negative total amount: ${invoice.total:,.2f}")
    if not invoice.line_items:
        warnings.append("No line items found")
    for item in invoice.line_items:
        if item.quantity < 0:
            warnings.append(f"Negative quantity for {item.item}: {item.quantity}")
    return warnings


def validation_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    invoice_data = state.get("invoice", {})
    try:
        invoice = Invoice(**invoice_data)
    except Exception as e:
        err_msg = str(e)
        state["invoice_parse_error"] = err_msg
        _log(state, "start", "error", f"Invalid invoice structure: {err_msg[:200]}")
        result = ValidationResult(
            passed=False,
            item_flags=[],
            arithmetic_flags=[],
            warnings=[],
            summary=f"Invalid invoice structure from extraction: {err_msg[:300]}",
        )
        state["validation_result"] = result.model_dump()
        _log(state, "complete", "error", "Pipeline short-circuited due to invalid invoice structure")
        return state

    # Duplicate check: if we've already processed this invoice number, mark state and continue (no double record at payment).
    existing = check_duplicate_invoice(invoice.invoice_number)
    if existing:
        state["is_duplicate"] = True
        state["duplicate_of"] = dict(existing)
        _log(state, "duplicate_check", "info",
             f"Invoice {invoice.invoice_number} already processed on {existing.get('processed_at', '?')} — this run is for audit")

    _log(state, "start", "info", f"Validating {invoice.invoice_number}")

    exchange_rate = get_exchange_rate(invoice.currency)
    item_flags = _check_items(invoice, exchange_rate)
    arithmetic_flags = _check_arithmetic(invoice)
    warnings = _check_data_integrity(invoice)

    # Unknown currency: we still use rate 1.0 but surface a warning.
    known_currencies = get_known_currencies()
    if invoice.currency and invoice.currency.upper() not in {c.upper() for c in known_currencies}:
        warnings.append(
            f"Unknown currency '{invoice.currency}'; rate assumed 1.0 — verify before payment"
        )

    errors = [f for f in item_flags if f.severity == "error"]
    passed = len(errors) == 0 and not any(
        "Missing vendor" in w or "Negative total" in w for w in warnings
    )

    parts = []
    if item_flags:
        parts.append(f"{len(item_flags)} item issue(s)")
    if arithmetic_flags:
        parts.append(f"{len(arithmetic_flags)} arithmetic issue(s)")
    if warnings:
        parts.append(f"{len(warnings)} warning(s)")
    summary = "; ".join(parts) if parts else "All checks passed"

    result = ValidationResult(
        passed=passed,
        item_flags=item_flags,
        arithmetic_flags=arithmetic_flags,
        warnings=warnings,
        summary=summary,
    )

    state["validation_result"] = result.model_dump()
    _log(state, "complete", "success" if passed else "warning",
         f"{'PASSED' if passed else 'FAILED'}: {summary}")

    return state
