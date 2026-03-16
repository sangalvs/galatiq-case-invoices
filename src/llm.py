"""LLM integration: xAI Grok with mock fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from src.config import USE_MOCK_LLM, XAI_API_KEY, XAI_BASE_URL, XAI_MODEL

INVOICE_EXTRACTION_PROMPT = """You are an expert invoice data extraction system. Extract all structured data from the following invoice text.

Rules:
- Fix OCR artifacts: letter O as digit 0 (e.g. 2O26 → 2026, $3,5OO → $3,500), letter l as 1
- Normalize invoice numbers to INV-XXXX format
- Extract ALL line items even if the invoice has unusual formatting
- For amounts, strip currency symbols and commas, return as numbers
- If a field is genuinely missing, use null
- For currency, detect from symbols: $ = USD, € = EUR, £ = GBP

Invoice text:
---
{text}
---

Return a JSON object with these exact fields:
{{
  "invoice_number": "string",
  "vendor": "string",
  "date": "YYYY-MM-DD or null",
  "due_date": "YYYY-MM-DD or null",
  "currency": "USD",
  "line_items": [
    {{"item": "string", "quantity": number, "unit_price": number}}
  ],
  "subtotal": number or null,
  "tax_rate": number or null,
  "tax_amount": number or null,
  "total": number or null,
  "payment_terms": "string or null",
  "notes": "string or null"
}}"""


def get_llm():
    """Return a LangChain chat model: real Grok or mock."""
    if USE_MOCK_LLM:
        return MockLLM()

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=XAI_MODEL,
        base_url=XAI_BASE_URL,
        api_key=XAI_API_KEY,
        temperature=0.0,
        timeout=30,
        max_retries=2,
    )


def _extract_message_content(messages: Any) -> str:
    if isinstance(messages, list):
        last_msg = messages[-1]
        if hasattr(last_msg, 'content'):
            return last_msg.content
        elif isinstance(last_msg, dict):
            return last_msg.get('content', '')
        return str(last_msg)
    return str(messages)


class MockLLM:
    """Deterministic mock LLM — fully functional without an API key.

    For invoice extraction it delegates to the actual deterministic parsers,
    so mock mode produces accurate results. For fraud/approval it uses
    signal-aware heuristics.
    """

    def invoke(self, messages: Any) -> "MockResponse":
        content = _extract_message_content(messages)
        return MockResponse(content=self._generate_response(content))

    def with_structured_output(self, schema: Type[BaseModel]):
        return MockStructuredLLM(schema)

    def _generate_response(self, prompt: str) -> str:
        lower = prompt.lower()
        if '"score"' in lower and '"reasoning"' in lower:
            return self._fraud_pattern_response(prompt)
        if 'fraud' in lower or 'risk' in lower:
            return self._fraud_response(prompt)
        if 'approv' in lower or 'critique' in lower:
            return self._approval_response(prompt)
        if 'invoice text' in lower or 'extract' in lower:
            return self._extraction_json_response(prompt)
        return "Analysis complete. No significant issues found."

    def _fraud_pattern_response(self, prompt: str) -> str:
        lower = prompt.lower()
        if 'urgent' in lower or 'immediately' in lower or 'fraudster' in lower or 'wire transfer' in lower:
            return '{"score": 8, "reasoning": "Multiple high-risk fraud indicators: urgency language, suspicious vendor name, and pressure tactics detected."}'
        if 'noproduct' in lower or 'unknown item' in lower or 'supergizmo' in lower:
            return '{"score": 4, "reasoning": "Unknown items and unrecognized vendor domain suggest this invoice warrants additional verification."}'
        if 'negative' in lower or '"vendor": ""' in lower or 'null' in lower:
            return '{"score": 6, "reasoning": "Data integrity issues including negative quantities or missing required fields suggest possible invoice manipulation."}'
        return '{"score": 1, "reasoning": "No significant fraud patterns detected. Invoice appears to be a legitimate business transaction."}'

    def _fraud_response(self, prompt: str) -> str:
        lower = prompt.lower()
        if 'urgent' in lower or 'immediately' in lower or 'fraudster' in lower:
            return "HIGH RISK: Multiple fraud indicators detected including urgency language and suspicious vendor."
        if 'noproduct' in lower or 'unknown item' in lower:
            return "MEDIUM RISK: Unknown vendor or items not in catalog."
        if 'negative' in lower or 'missing vendor' in lower or 'empty vendor' in lower:
            return "HIGH RISK: Data integrity issues suggest this invoice may be invalid."
        return "LOW RISK: No significant fraud indicators detected."

    def _approval_response(self, prompt: str) -> str:
        lower = prompt.lower()
        if 'critical' in lower or 'high risk' in lower:
            return "The rejection decision is well-founded. The fraud signals and validation failures present clear financial risk that cannot be overlooked."
        if 'rejected' in lower or 'fail' in lower:
            return "The rejection is appropriate given the validation failures. No evidence of over-conservatism."
        if 'medium risk' in lower or 'flag' in lower:
            return "Flagging for review is prudent. The medium fraud risk score warrants human verification before proceeding."
        if 'scrutiny' in lower:
            return "Approval with additional scrutiny is appropriate. The amount exceeds threshold but all checks passed — recommend confirming with the vendor directly."
        return "The approval decision is well-supported. Invoice passes all checks and presents no significant risk."

    def _extraction_json_response(self, prompt: str) -> str:
        """Parse the raw invoice text from the prompt using our deterministic parser."""
        import tempfile, os
        from pathlib import Path

        text_match = re.search(r'---\n([\s\S]*?)\n---', prompt)
        if not text_match:
            return '{}'
        raw_text = text_match.group(1)

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(raw_text)
                tmp_path = f.name

            from src.parsers.txt_parser import parse_txt_deterministic
            inv = parse_txt_deterministic(Path(tmp_path))
            os.unlink(tmp_path)

            items = [
                {"item": i.item, "quantity": i.quantity, "unit_price": i.unit_price}
                for i in inv.line_items
            ]
            return json.dumps({
                "invoice_number": inv.invoice_number,
                "vendor": inv.vendor,
                "date": inv.date,
                "due_date": inv.due_date,
                "currency": inv.currency,
                "line_items": items,
                "subtotal": inv.subtotal,
                "tax_rate": inv.tax_rate,
                "tax_amount": inv.tax_amount,
                "total": inv.total,
                "payment_terms": inv.payment_terms,
                "notes": inv.notes,
            })
        except Exception:
            return '{}'


class MockResponse:
    def __init__(self, content: str):
        self.content = content


class MockStructuredLLM:
    """Structured output mock — delegates extraction to the deterministic parser."""

    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema

    def invoke(self, messages: Any) -> BaseModel:
        content = _extract_message_content(messages)
        return self._build_from_prompt(content)

    def _build_from_prompt(self, prompt: str) -> BaseModel:
        from src.models import Invoice
        if self.schema == Invoice:
            return self._extract_invoice(prompt)
        return self.schema()

    def _extract_invoice(self, prompt: str) -> Any:
        from src.models import Invoice
        mock = MockLLM()
        json_str = mock._extraction_json_response(prompt)
        try:
            data = json.loads(json_str)
            from src.models import LineItem
            items = [
                LineItem(item=i["item"], quantity=i["quantity"], unit_price=i["unit_price"])
                for i in data.get("line_items", [])
            ]
            return Invoice(
                invoice_number=data.get("invoice_number") or "UNKNOWN",
                vendor=data.get("vendor") or "",
                date=data.get("date"),
                due_date=data.get("due_date"),
                currency=data.get("currency", "USD"),
                line_items=items,
                subtotal=data.get("subtotal"),
                tax_rate=data.get("tax_rate"),
                tax_amount=data.get("tax_amount"),
                total=data.get("total"),
                payment_terms=data.get("payment_terms"),
                notes=data.get("notes"),
                raw_text=prompt,
            )
        except Exception:
            return Invoice(invoice_number="UNKNOWN", vendor="", raw_text=prompt)
