"""Ingestion agent: parse invoice files with LLM-primary extraction for unstructured formats."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from src.config import INGESTION_REFINE_RETRIES, PARSER_FIRST_FOR_UNSTRUCTURED
from src.llm import INVOICE_EXTRACTION_PROMPT, get_llm
from src.models import Invoice, LineItem, ProcessingLogEntry
from src.parsers.registry import parse_invoice
from src.parsers.txt_parser import preprocess_ocr

UNSTRUCTURED_FORMATS = {".txt", ".pdf"}
STRUCTURED_FORMATS = {".json", ".csv", ".xml"}


def _log(state: Dict[str, Any], action: str, result: str, details: str = "") -> None:
    inv_num = "UNKNOWN"
    if state.get("invoice"):
        inv_num = state["invoice"].get("invoice_number", "UNKNOWN")
    entry = ProcessingLogEntry(
        invoice_number=inv_num, stage="ingestion", action=action, result=result, details=details
    )
    state.setdefault("processing_log", []).append(entry.model_dump())


def _validate_extraction(invoice: Invoice) -> List[str]:
    issues = []
    if not invoice.invoice_number or invoice.invoice_number == "UNKNOWN":
        issues.append("Missing invoice number")
    if not invoice.vendor:
        issues.append("Missing vendor name")
    if not invoice.line_items:
        issues.append("No line items extracted")
    if invoice.total is None:
        issues.append("Missing total amount")
    return issues


def _llm_extract(raw_text: str) -> Invoice:
    """Use LLM as primary extractor for unstructured text."""
    llm = get_llm()
    cleaned = preprocess_ocr(raw_text)
    prompt = INVOICE_EXTRACTION_PROMPT.format(text=cleaned[:4000])

    try:
        response = llm.invoke([{"role": "user", "content": prompt}])
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        raise RuntimeError(
            f"LLM extraction failed ({type(e).__name__}): invoice could not be processed. "
            "Please try again shortly."
        ) from e

    return _parse_llm_json(content, raw_text)


def _parse_llm_json(content: str, raw_text: str) -> Invoice:
    """Parse LLM JSON response into an Invoice model."""
    try:
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            raise ValueError("No JSON found in LLM response")

        data = json.loads(json_match.group())
        items = []
        for item_data in data.get("line_items") or []:
            try:
                items.append(LineItem(
                    item=str(item_data.get("item", "")),
                    quantity=float(item_data.get("quantity", 0)),
                    unit_price=float(item_data.get("unit_price", 0.0)),
                ))
            except (TypeError, ValueError):
                continue

        def _f(val: Any) -> Any:
            if val is None:
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None

        return Invoice(
            invoice_number=str(data.get("invoice_number") or "UNKNOWN"),
            vendor=str(data.get("vendor") or ""),
            date=data.get("date"),
            due_date=data.get("due_date"),
            currency=str(data.get("currency") or "USD"),
            line_items=items,
            subtotal=_f(data.get("subtotal")),
            tax_rate=_f(data.get("tax_rate")),
            tax_amount=_f(data.get("tax_amount")),
            total=_f(data.get("total")),
            payment_terms=data.get("payment_terms"),
            notes=data.get("notes"),
            raw_text=raw_text,
        )
    except Exception:
        return Invoice(invoice_number="UNKNOWN", vendor="", raw_text=raw_text)


def _llm_refine(invoice: Invoice, issues: List[str], raw_text: str) -> Invoice:
    """Use LLM to correct specific extraction issues."""
    llm = get_llm()
    issues_str = "\n".join(f"- {i}" for i in issues)
    items_str = "\n".join(
        f"  - {item.item}: qty={item.quantity} @ ${item.unit_price}"
        for item in invoice.line_items
    )

    prompt = f"""You are an invoice extraction expert. A partial extraction has issues. Fix them.

Raw invoice text:
---
{raw_text[:3000]}
---

Current extraction:
- Invoice Number: {invoice.invoice_number}
- Vendor: {invoice.vendor}
- Total: {invoice.total}
- Line Items ({len(invoice.line_items)}):
{items_str}

Issues to fix:
{issues_str}

Fix OCR errors (O→0, l→1). Return corrected JSON with fields:
invoice_number, vendor, date, due_date, currency, line_items (item/quantity/unit_price), subtotal, tax_rate, tax_amount, total, payment_terms, notes."""

    try:
        response = llm.invoke([{"role": "user", "content": prompt}])
        content = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        raise RuntimeError(
            f"LLM refinement failed ({type(e).__name__}): invoice could not be fully extracted. "
            "Please try again shortly."
        ) from e
    refined = _parse_llm_json(content, raw_text)

    if refined.invoice_number and refined.invoice_number != "UNKNOWN":
        invoice.invoice_number = refined.invoice_number
    if refined.vendor:
        invoice.vendor = refined.vendor
    if refined.total is not None:
        invoice.total = refined.total
    if refined.subtotal is not None:
        invoice.subtotal = refined.subtotal
    if refined.line_items and not invoice.line_items:
        invoice.line_items = refined.line_items
    if refined.payment_terms:
        invoice.payment_terms = refined.payment_terms
    if refined.date:
        invoice.date = refined.date
    if refined.due_date:
        invoice.due_date = refined.due_date
    if refined.tax_rate is not None:
        invoice.tax_rate = refined.tax_rate
    if refined.tax_amount is not None:
        invoice.tax_amount = refined.tax_amount

    return invoice


def ingestion_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    file_path = state.get("file_path", "")
    ext = Path(file_path).suffix.lower()
    _log(state, "start", "info", f"Processing {file_path} ({ext})")

    # --- Structured formats: deterministic parsing is reliable ---
    if ext in STRUCTURED_FORMATS:
        try:
            invoice = parse_invoice(file_path)
            _log(state, "deterministic_parse", "success",
                 f"Parsed {invoice.invoice_number}: {len(invoice.line_items)} items, total={invoice.total}")
        except Exception as e:
            _log(state, "parse_error", "error", str(e))
            state.setdefault("errors", []).append(f"Parse error: {e}")
            state["invoice"] = Invoice(invoice_number="UNKNOWN", vendor="", raw_text=str(e)).model_dump()
            return state

    # --- Unstructured formats: parser-first, LLM fallback ---
    else:
        try:
            raw_text = _read_raw_text(file_path, ext)
        except Exception as e:
            _log(state, "read_error", "error", str(e))
            state["invoice"] = Invoice(invoice_number="UNKNOWN", vendor="", raw_text=str(e)).model_dump()
            return state

        invoice = None
        if PARSER_FIRST_FOR_UNSTRUCTURED:
            try:
                parser_invoice = parse_invoice(file_path)
                parser_invoice.raw_text = raw_text
                issues = _validate_extraction(parser_invoice)
                if not issues:
                    invoice = parser_invoice
                    _log(state, "parser_first", "success",
                         f"Parser extracted: {invoice.invoice_number} | {invoice.vendor} | {len(invoice.line_items)} items (0 LLM calls)")
            except Exception as e:
                _log(state, "parser_first", "info", f"Parser failed: {e} — falling back to LLM")

        if invoice is None:
            _log(state, "llm_extraction", "info",
                 f"Sending {len(raw_text)} chars to LLM for structured extraction")
            try:
                invoice = _llm_extract(raw_text)
            except RuntimeError as e:
                _log(state, "llm_extraction", "error", str(e))
                state.setdefault("errors", []).append(str(e))
                state["invoice_parse_error"] = str(e)
                state["invoice"] = Invoice(invoice_number="UNKNOWN", vendor="", raw_text=raw_text).model_dump()
                return state
            invoice.raw_text = raw_text
            _log(state, "llm_extraction_complete", "success",
                 f"LLM extracted: {invoice.invoice_number} | {invoice.vendor} | {len(invoice.line_items)} items")

    # --- Self-correction loop (both paths) ---
    issues = _validate_extraction(invoice)
    max_retries = max(0, INGESTION_REFINE_RETRIES)
    retry = 0

    while issues and retry < max_retries:
        retry += 1
        _log(state, f"self_correction_{retry}", "info",
             f"Issues: {', '.join(issues)} — refining with LLM")
        try:
            invoice = _llm_refine(invoice, issues, invoice.raw_text or "")
        except RuntimeError as e:
            _log(state, f"self_correction_{retry}", "error", str(e))
            break  # keep the partial extraction rather than crashing
        issues = _validate_extraction(invoice)

    if issues:
        _log(state, "extraction_warnings", "warning",
             f"Remaining after {max_retries} retries: {', '.join(issues)}")

    state["raw_text"] = invoice.raw_text or ""
    state["invoice"] = invoice.model_dump()
    _log(state, "complete", "success",
         f"Final: {invoice.invoice_number} | {invoice.vendor} | ${invoice.total} | {len(invoice.line_items)} items")

    return state


def _read_raw_text(file_path: str, ext: str) -> str:
    """Extract raw text from a file, using pdfplumber for PDFs."""
    if ext == ".pdf":
        import pdfplumber
        parts = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parts.append(text)
        return "\n".join(parts) or "[PDF contained no extractable text]"
    else:
        return Path(file_path).read_text(errors="replace")
