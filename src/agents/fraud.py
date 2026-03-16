"""Fraud detection agent: multi-signal risk scoring."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from src.config import FRAUD_RISK_THRESHOLDS, SKIP_LLM_FRAUD_WHEN_HIGH, URGENCY_KEYWORDS
from src.llm import get_llm
from src.models import (
    FraudRecommendation,
    FraudResult,
    FraudSignal,
    Invoice,
    ProcessingLogEntry,
    RiskLevel,
)
from src.tools.db import convert_to_usd, get_exchange_rate, is_first_time_vendor


def _log(state: Dict[str, Any], action: str, result: str, details: str = "") -> None:
    inv_num = state.get("invoice", {}).get("invoice_number", "UNKNOWN")
    entry = ProcessingLogEntry(
        invoice_number=inv_num, stage="fraud", action=action, result=result, details=details
    )
    state.setdefault("processing_log", []).append(entry.model_dump())


def _score_urgency(invoice: Invoice, raw_text: str) -> FraudSignal:
    text_lower = (raw_text + " " + (invoice.payment_terms or "") + " " + (invoice.notes or "")).lower()
    hits = [kw for kw in URGENCY_KEYWORDS if kw in text_lower]

    if invoice.due_date and invoice.due_date.lower() in ("yesterday", "today", "immediate"):
        hits.append(f"suspicious due date: {invoice.due_date}")

    if invoice.payment_terms and invoice.payment_terms.lower() in ("immediate", "due on receipt"):
        hits.append("immediate payment terms")

    score = min(10, len(hits) * 3)
    desc = f"Urgency signals: {', '.join(hits)}" if hits else "No urgency signals detected"
    return FraudSignal(category="urgency", description=desc, score=score)


def _score_price_anomaly(invoice: Invoice, validation_result: Dict) -> FraudSignal:
    price_flags = [
        f for f in validation_result.get("item_flags", [])
        if f.get("issue") == "price_anomaly"
    ]

    if not price_flags:
        return FraudSignal(category="price_anomaly", description="No price anomalies detected", score=0)

    details = "; ".join(f.get("detail", "") for f in price_flags)
    score = min(10, len(price_flags) * 3)
    return FraudSignal(category="price_anomaly", description=details, score=score)


def _score_vendor_risk(invoice: Invoice, raw_text: str, conn=None) -> FraudSignal:
    signals = []
    score = 0

    if not invoice.vendor:
        signals.append("Missing vendor name")
        score += 5

    vendor_lower = (invoice.vendor or "").lower()
    for sus_word in ["fraud", "fake", "scam", "test", "dummy"]:
        if sus_word in vendor_lower:
            signals.append(f"Suspicious vendor name contains '{sus_word}'")
            score += 5

    if is_first_time_vendor(invoice.vendor, conn=conn):
        signals.append("First-time vendor (no prior processing history)")
        score += 2

    suspicious_domains = ["noproduct", "fakeco", "scam", "test"]
    for domain in suspicious_domains:
        if domain in raw_text.lower():
            signals.append(f"Suspicious domain pattern: '{domain}'")
            score += 3

    score = min(10, score)
    desc = "; ".join(signals) if signals else "No vendor risk signals detected"
    return FraudSignal(category="vendor_risk", description=desc, score=score)


def _score_data_integrity(invoice: Invoice, validation_result: Dict) -> FraudSignal:
    signals = []
    score = 0

    for item in invoice.line_items:
        if item.quantity < 0:
            signals.append(f"Negative quantity: {item.item} ({item.quantity})")
            score += 4

    if not invoice.vendor:
        signals.append("Empty vendor field")
        score += 3

    if not invoice.due_date:
        signals.append("Missing due date")
        score += 2

    zero_stock_flags = [
        f for f in validation_result.get("item_flags", [])
        if f.get("issue") == "zero_stock"
    ]
    if zero_stock_flags:
        for f in zero_stock_flags:
            signals.append(f"Zero-stock item ordered: {f.get('item', '?')}")
            score += 3

    arithmetic_issues = validation_result.get("arithmetic_flags", [])
    if arithmetic_issues:
        signals.append(f"{len(arithmetic_issues)} arithmetic discrepancy(ies)")
        score += 2

    score = min(10, score)
    desc = "; ".join(signals) if signals else "No data integrity issues"
    return FraudSignal(category="data_integrity", description=desc, score=score)


def _score_llm_pattern(invoice: Invoice, raw_text: str, validation_result: Dict, signals_so_far: List[FraudSignal]) -> FraudSignal:
    llm = get_llm()

    signal_summary = "\n".join(
        f"- {s.category} (score {s.score}/10): {s.description}" for s in signals_so_far
    )
    val_summary = validation_result.get("summary", "N/A")

    prompt = f"""You are a fraud detection expert analyzing an invoice for suspicious patterns.

Invoice: {invoice.invoice_number}
Vendor: {invoice.vendor}
Total: ${invoice.total} {invoice.currency}
Items: {len(invoice.line_items)}
Payment Terms: {invoice.payment_terms}
Notes: {invoice.notes or 'None'}

Raw text excerpt (first 500 chars):
{raw_text[:500]}

Validation summary: {val_summary}

Signals already detected:
{signal_summary}

On a scale of 0-10, how suspicious is this invoice? Consider patterns a rule-based system might miss:
unusual formatting, social engineering tactics, inconsistencies, etc.
Respond with a JSON object: {{"score": <0-10>, "reasoning": "<brief explanation>"}}"""

    try:
        response = llm.invoke([{"role": "user", "content": prompt}])
        content = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        raise RuntimeError(
            f"LLM fraud analysis failed ({type(e).__name__}). "
            "Please try again shortly."
        ) from e

    try:
        json_match = re.search(r'\{[\s\S]*?\}', content)
        if json_match:
            data = json.loads(json_match.group())
            llm_score = max(0, min(10, int(data.get("score", 0))))
            reasoning = data.get("reasoning", content)
        else:
            llm_score = 0
            reasoning = content
    except (ValueError, KeyError):
        llm_score = 0
        reasoning = content

    return FraudSignal(category="pattern_analysis", description=reasoning, score=llm_score)


def _compute_risk(signals: List[FraudSignal]) -> tuple:
    """Compute composite score (0-100) from individual signals (0-10 each).

    Uses weighted scoring: any signal >= 7 is a strong indicator that amplifies the score.
    """
    if not signals:
        return 0, RiskLevel.LOW, FraudRecommendation.PROCEED

    raw_total = sum(s.score for s in signals)
    max_possible = len(signals) * 10

    composite = round((raw_total / max_possible) * 100) if max_possible > 0 else 0

    # Only amplify based on rule-based signals, not LLM opinion alone.
    # LLM scores contribute to the weighted composite but shouldn't single-handedly
    # push a low-rule-signal invoice into HIGH territory.
    rule_signals = [s for s in signals if s.category != "pattern_analysis"]
    high_signals = sum(1 for s in rule_signals if s.score >= 7)
    if high_signals >= 2:
        composite = max(composite, 76)
    elif high_signals == 1:
        composite = max(composite, 51)

    composite = max(0, min(100, composite))

    if composite <= FRAUD_RISK_THRESHOLDS["low"]:
        level = RiskLevel.LOW
        rec = FraudRecommendation.PROCEED
    elif composite <= FRAUD_RISK_THRESHOLDS["medium"]:
        level = RiskLevel.MEDIUM
        rec = FraudRecommendation.FLAG_FOR_REVIEW
    elif composite <= FRAUD_RISK_THRESHOLDS["high"]:
        level = RiskLevel.HIGH
        rec = FraudRecommendation.REJECT
    else:
        level = RiskLevel.CRITICAL
        rec = FraudRecommendation.REJECT

    return composite, level, rec


def fraud_detection_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("invoice_parse_error"):
        _log(state, "start", "warning", "Skipping fraud analysis: invalid invoice structure")
        result = FraudResult(
            risk_score=100,
            risk_level=RiskLevel.CRITICAL,
            signals=[],
            llm_reasoning="Invalid invoice structure from extraction.",
            recommendation=FraudRecommendation.REJECT,
        )
        state["fraud_result"] = result.model_dump()
        _log(state, "complete", "info", "Set reject due to invalid invoice structure")
        return state

    invoice_data = state.get("invoice", {})
    invoice = Invoice(**invoice_data)
    raw_text = state.get("raw_text", "")
    validation_result = state.get("validation_result", {})

    _log(state, "start", "info", f"Fraud analysis for {invoice.invoice_number}")

    signals = [
        _score_urgency(invoice, raw_text),
        _score_price_anomaly(invoice, validation_result),
        _score_vendor_risk(invoice, raw_text),
        _score_data_integrity(invoice, validation_result),
    ]

    llm_check_failed = False
    if SKIP_LLM_FRAUD_WHEN_HIGH:
        composite_pre, level_pre, _ = _compute_risk(signals)
        if level_pre in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            llm_signal = FraudSignal(
                category="pattern_analysis",
                description="Skipped (rule-based signals already high/critical)",
                score=0,
            )
            # Do not append - keeps composite from 4 signals, avoids diluting score
        else:
            try:
                llm_signal = _score_llm_pattern(invoice, raw_text, validation_result, signals)
                signals.append(llm_signal)
            except RuntimeError as e:
                llm_check_failed = True
                llm_signal = FraudSignal(category="pattern_analysis", description=str(e), score=0)
                _log(state, "llm_fraud_error", "warning", str(e))
    else:
        try:
            llm_signal = _score_llm_pattern(invoice, raw_text, validation_result, signals)
            signals.append(llm_signal)
        except RuntimeError as e:
            llm_check_failed = True
            llm_signal = FraudSignal(category="pattern_analysis", description=str(e), score=0)
            _log(state, "llm_fraud_error", "warning", str(e))

    composite, level, recommendation = _compute_risk(signals)

    result = FraudResult(
        risk_score=composite,
        risk_level=level,
        signals=signals,
        llm_reasoning=llm_signal.description,
        recommendation=recommendation,
    )

    state["fraud_result"] = result.model_dump()
    if llm_check_failed:
        state["llm_check_failed"] = True
        _log(state, "complete", "warning",
             f"Risk: {level.value} ({composite}/100) — LLM check incomplete, manual review required")
    else:
        _log(state, "complete", "info",
             f"Risk: {level.value} ({composite}/100) - Recommendation: {recommendation.value}")

    return state
