"""Approval agent: rule-based + LLM reflection/critique loop."""

from __future__ import annotations

from typing import Any, Dict

from src.config import APPROVAL_THRESHOLD, AUTO_APPROVE_OVER_THRESHOLD, SKIP_LLM_CRITIQUE_WHEN_OBVIOUS
from src.llm import get_llm
from src.models import (
    ApprovalDecision,
    ApprovalResult,
    FraudRecommendation,
    Invoice,
    ProcessingLogEntry,
    RiskLevel,
)
from src.tools.db import convert_to_usd


def _log(state: Dict[str, Any], action: str, result: str, details: str = "") -> None:
    inv_num = state.get("invoice", {}).get("invoice_number", "UNKNOWN")
    entry = ProcessingLogEntry(
        invoice_number=inv_num, stage="approval", action=action, result=result, details=details
    )
    state.setdefault("processing_log", []).append(entry.model_dump())


def _initial_assessment(
    invoice: Invoice, validation: Dict, fraud: Dict, amount_usd: float
) -> Dict[str, Any]:
    """Rule-based initial assessment."""
    decision = ApprovalDecision.APPROVED
    reasons = []
    requires_scrutiny = False

    val_passed = validation.get("passed", False)
    if not val_passed:
        decision = ApprovalDecision.REJECTED
        item_flags = validation.get("item_flags", [])
        for flag in item_flags:
            if flag.get("severity") == "error":
                reasons.append(f"Validation failure: {flag.get('detail', 'unknown issue')}")

        arithmetic_flags = validation.get("arithmetic_flags", [])
        for af in arithmetic_flags:
            reasons.append(f"Arithmetic issue: {af.get('detail', 'unknown')}")

    fraud_level = fraud.get("risk_level", "low")
    fraud_score = fraud.get("risk_score", 0)
    fraud_rec = fraud.get("recommendation", "proceed")

    if fraud_level in ("critical", "high"):
        decision = ApprovalDecision.REJECTED
        reasons.append(f"Fraud risk: {fraud_level} ({fraud_score}/100)")
        for sig in fraud.get("signals", []):
            if sig.get("score", 0) >= 5:
                reasons.append(f"  - {sig.get('category')}: {sig.get('description', '')[:200]}")
    elif fraud_level == "medium":
        if decision == ApprovalDecision.APPROVED:
            decision = ApprovalDecision.FLAGGED
            reasons.append(f"Medium fraud risk ({fraud_score}/100) - requires review")

    # Invoices over threshold require VP approval; do not auto-approve unless demo mode is on.
    if amount_usd > APPROVAL_THRESHOLD and decision == ApprovalDecision.APPROVED:
        if AUTO_APPROVE_OVER_THRESHOLD:
            requires_scrutiny = True
            reasons.append(f"Amount ${amount_usd:,.2f} exceeds ${APPROVAL_THRESHOLD:,.0f} threshold - additional scrutiny applied")
        else:
            decision = ApprovalDecision.FLAGGED
            reasons.append(f"Amount ${amount_usd:,.2f} exceeds ${APPROVAL_THRESHOLD:,.0f} threshold — requires VP approval before payment")

    if not reasons:
        reasons.append("All validation checks passed; fraud risk is low; amount within normal range")

    return {
        "decision": decision,
        "reasons": reasons,
        "requires_scrutiny": requires_scrutiny,
    }


def _critique(
    invoice: Invoice, initial: Dict, validation: Dict, fraud: Dict, amount_usd: float
) -> str:
    """LLM critique of the initial assessment."""
    llm = get_llm()

    decision = initial["decision"]
    reasons = "\n".join(f"- {r}" for r in initial["reasons"])

    val_summary = validation.get("summary", "N/A")
    fraud_signals = "\n".join(
        f"- {s.get('category')}: score {s.get('score', 0)}/10 - {s.get('description', '')[:150]}"
        for s in fraud.get("signals", [])
    )

    prompt = f"""You are a senior finance VP reviewing an invoice approval decision. Critique the initial assessment.

Invoice: {invoice.invoice_number}
Vendor: {invoice.vendor}
Amount: ${amount_usd:,.2f} USD
Items: {len(invoice.line_items)}
Payment Terms: {invoice.payment_terms}

Validation Summary: {val_summary}

Fraud Signals:
{fraud_signals}

Initial Decision: {decision.value}
Reasoning:
{reasons}

Critique this decision. Consider:
1. Are there missed risks that should block approval?
2. Is the decision overly conservative (rejecting something that should pass)?
3. Any business context that changes the calculus?

Keep your critique to 2-3 sentences."""

    try:
        response = llm.invoke([{"role": "user", "content": prompt}])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        raise RuntimeError(
            f"LLM approval critique failed ({type(e).__name__}). Please try again shortly."
        ) from e


def approval_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    if state.get("invoice_parse_error"):
        _log(state, "start", "warning", "Skipping approval: invalid invoice structure")
        result = ApprovalResult(
            decision=ApprovalDecision.REJECTED,
            reasoning="Invalid invoice structure from extraction.",
            critique="",
            requires_scrutiny=False,
            fraud_considerations="",
        )
        state["approval_result"] = result.model_dump()
        _log(state, "complete", "info", "Rejected due to invalid invoice structure")
        return state

    invoice_data = state.get("invoice", {})
    invoice = Invoice(**invoice_data)
    validation = state.get("validation_result", {})
    fraud = state.get("fraud_result", {})

    _log(state, "start", "info", f"Approval review for {invoice.invoice_number}")

    amount_usd = convert_to_usd(invoice.total or 0, invoice.currency)

    initial = _initial_assessment(invoice, validation, fraud, amount_usd)

    # If fraud LLM check failed, force manual review regardless of rule-based outcome
    if state.get("llm_check_failed") and initial["decision"] == ApprovalDecision.APPROVED:
        initial["decision"] = ApprovalDecision.FLAGGED
        initial["reasons"].append(
            "Fraud analysis incomplete (LLM unavailable) — manual review required before payment"
        )

    _log(state, "initial_assessment", "info",
         f"Initial: {initial['decision'].value} | {'; '.join(initial['reasons'][:2])}")

    obvious_approved = (
        SKIP_LLM_CRITIQUE_WHEN_OBVIOUS
        and initial["decision"] == ApprovalDecision.APPROVED
        and fraud.get("risk_level", "low") == "low"
        and validation.get("passed", False)
        and amount_usd <= APPROVAL_THRESHOLD
    )
    if obvious_approved:
        critique = "Skipped (obvious approval: low fraud, validation passed, under threshold)"
        _log(state, "critique", "info", "Skipped LLM critique (obvious approval)")
    else:
        try:
            critique = _critique(invoice, initial, validation, fraud, amount_usd)
            _log(state, "critique", "info", critique[:500] + ("..." if len(critique) > 500 else ""))
        except RuntimeError as e:
            critique = str(e)
            _log(state, "critique", "warning", str(e))
            # Escalate to manual review — don't auto-approve without the VP critique
            if initial["decision"] == ApprovalDecision.APPROVED:
                initial["decision"] = ApprovalDecision.FLAGGED
                initial["reasons"].append(
                    "Approval critique unavailable (LLM error) — manual review required"
                )

    final_decision = initial["decision"]
    fraud_considerations = ""
    fraud_level = fraud.get("risk_level", "low")
    if fraud_level != "low":
        fraud_considerations = f"Fraud risk level: {fraud_level} ({fraud.get('risk_score', 0)}/100). "
        fraud_considerations += "; ".join(
            s.get("description", "")[:150]
            for s in fraud.get("signals", [])
            if s.get("score", 0) >= 3
        )

    result = ApprovalResult(
        decision=final_decision,
        reasoning="\n".join(initial["reasons"]),
        critique=critique,
        requires_scrutiny=initial["requires_scrutiny"],
        fraud_considerations=fraud_considerations,
    )

    state["approval_result"] = result.model_dump()
    _log(state, "complete", "success",
         f"Final: {final_decision.value} | Scrutiny: {initial['requires_scrutiny']}")

    return state
